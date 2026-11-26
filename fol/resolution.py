"""A small resolution theorem prover built on top of the unification module.

Inference rules (Robinson, 1965) - both complete for refutation together:

* **binary resolution**::

        L1 | C1        ~L2 | C2         sigma = MGU(L1, L2)
        ---------------------------------------------------
                      (C1 | C2) sigma

* **factoring**::

        L1 | L2 | C        sigma = MGU(L1, L2)
        --------------------------------------
                    (L1 | C) sigma

Search: the *given-clause* algorithm (as in Otter / Prover9) with

* the **set-of-support** strategy - two clauses of the knowledge base are never
  resolved together; every inference involves the negated goal or a clause
  derived from it,
* **subsumption** (forward and backward) and **tautology deletion**,
* weight-based clause selection mixed with FIFO selection for fairness,
* **answer extraction** with an ``Answer(...)`` literal (Green's method), which
  turns the prover into a question-answering system.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

from .clauses import ANSWER_PREDICATE, Clause
from .substitution import Substitution
from .terms import Literal, Term, Variable
from .unify import _match, unify

_SUFFIX = re.compile(r"_\d+$")
_COPY_VAR = re.compile(r"\b([A-Z_][A-Za-z0-9_']*?)_(\d+)\b")


# =========================================================================== variable handling


def renamed_copy(clause: Clause, tag: int) -> Clause:
    """Copy of a clause with every variable ``X`` renamed to ``X_tag`` (*standardizing apart*).

    Two clauses must not share variables before they are resolved: the
    variables of a clause are implicitly universally quantified, so ``p(X)``
    and ``~p(f(X))`` are refutable together although ``X`` does not unify
    with ``f(X)``.  The prover tags the copy with the clause number, so
    ``X_3`` reads as "the variable X of clause 3".  Clauses kept by the prover
    are normalized and never contain a ``_<digits>`` suffix, hence a copy never
    shares variables with another kept clause.
    """
    mapping = {var: Variable(f"{_SUFFIX.sub('', var.name)}_{tag}") for var in clause.variables()}
    return clause.apply(Substitution(mapping))


def normalize_variables(clause: Clause) -> Clause:
    """Rename variables to short readable names (``X_17`` -> ``X``, ``X_3`` -> ``X1`` ...)."""
    mapping: dict[Variable, Term] = {}
    used: set[str] = set()
    for var in clause.variables():
        base = _SUFFIX.sub("", var.name) or "V"
        name, i = base, 0
        while name in used:
            i += 1
            name = f"{base}{i}"
        used.add(name)
        mapping[var] = Variable(name)
    return clause.apply(Substitution(mapping))


# =========================================================================== inference rules


@dataclass(frozen=True)
class Inference:
    """A conclusion together with the information needed to explain it."""

    clause: Clause
    substitution: Substitution
    literals: tuple[Literal, ...]  # the literals that were resolved upon / merged


def resolvents(c1: Clause, c2: Clause) -> Iterator[Inference]:
    """All binary resolvents of ``c1`` and ``c2`` (which must not share variables)."""
    for l1 in c1:
        for l2 in c2:
            if not l1.is_complement_of(l2):
                continue
            sigma = unify(l1.atom, l2.atom)
            if sigma is None:
                continue
            rest = c1.without(l1) + c2.without(l2)
            yield Inference(Clause(sigma.apply(lit) for lit in rest), sigma, (l1, l2))


def factors(clause: Clause) -> Iterator[Inference]:
    """All binary factors of ``clause`` (two literals of the same sign unified into one)."""
    lits = clause.literals
    for i, a in enumerate(lits):
        for b in lits[i + 1:]:
            if a.negated != b.negated or a.predicate != b.predicate or a.atom.arity != b.atom.arity:
                continue
            sigma = unify(a.atom, b.atom)
            if sigma is not None:
                yield Inference(clause.apply(sigma), sigma, (a, b))


def subsumes(c: Clause, d: Clause) -> bool:
    """theta-subsumption: is there a ``theta`` with ``c theta`` a subset of ``d``?

    A subsumed clause ``d`` is redundant: everything it could prove, ``c`` proves
    with fewer (or equal) literals.  Variables of ``d`` are treated as constants.
    """
    if len(c) > len(d) or not c.signature <= d.signature:
        return False
    c_lits = sorted(c.literals, key=lambda lit: -len(str(lit)))  # most constrained first

    def search(i: int, bindings: dict) -> bool:
        if i == len(c_lits):
            return True
        lc = c_lits[i]
        for ld in d:
            if ld.negated != lc.negated or ld.predicate != lc.predicate:
                continue
            extended = _match(lc.atom, ld.atom, dict(bindings))
            if extended is not None and search(i + 1, extended):
                return True
        return False

    return search(0, {})


# =========================================================================== proof objects


@dataclass
class ProofStep:
    id: int
    clause: Clause
    rule: str                                # "axiom", "negated goal", "resolution", "factoring"
    parents: tuple[int, ...] = ()
    substitution: Substitution | None = None
    literals: tuple[Literal, ...] = ()

    def justification(self) -> str:
        if not self.parents:
            return self.rule
        parents = ", ".join(map(str, self.parents))
        text = f"{self.rule} {parents}"
        if self.substitution is not None:
            text += f"  {self.substitution}"
        return text


@dataclass
class ProofResult:
    """Outcome of a refutation attempt.

    ``status`` is ``"proved"`` (a refutation was found), ``"saturated"`` (no new
    clause can be derived: the goal does **not** follow) or ``"limit"`` (a
    resource limit stopped the search: unknown).
    """

    status: str
    steps: dict[int, ProofStep]
    final_ids: list[int] = field(default_factory=list)
    query_variables: tuple[Variable, ...] = ()
    iterations: int = 0
    elapsed: float = 0.0

    @property
    def proved(self) -> bool:
        return bool(self.final_ids)

    def __bool__(self) -> bool:
        return self.proved

    # ---------------------------------------------------------------- answers
    def answers(self) -> list[list[dict[str, str]]]:
        """One entry per answer clause; each entry lists the alternative bindings
        (more than one when the answer is disjunctive, e.g. ``X = a or X = b``)."""
        result = []
        for fid in self.best_final_ids():
            clause = self.steps[fid].clause
            alternatives = []
            for lit in clause:
                if lit.predicate == ANSWER_PREDICATE:
                    alternatives.append({str(v): str(t) for v, t in zip(self.query_variables, lit.atom.args)})
            result.append(alternatives)
        return result

    def answer_strings(self) -> list[str]:
        out = []
        for alternatives in self.answers():
            if not alternatives:
                out.append("yes")
                continue
            out.append("  or  ".join(", ".join(f"{k} = {v}" for k, v in alt.items()) for alt in alternatives))
        return out

    def best_final_ids(self) -> list[int]:
        """Final clauses that are not made redundant by a stronger answer
        (``Answer(a) | Answer(b)`` is dropped once ``Answer(a)`` is found)."""
        clauses = {fid: self.steps[fid].clause for fid in self.final_ids}
        return [
            fid for fid, c in clauses.items()
            if not any(o != fid and subsumes(oc, c) and not subsumes(c, oc) for o, oc in clauses.items())
        ]

    # ---------------------------------------------------------------- proof
    def proof(self, final_id: int | None = None) -> list[ProofStep]:
        """The steps that contribute to the refutation, in derivation order."""
        if not self.final_ids:
            return []
        start = final_id if final_id is not None else self.best_final_ids()[0]
        needed: set[int] = set()
        stack = [start]
        while stack:
            sid = stack.pop()
            if sid in needed:
                continue
            needed.add(sid)
            stack.extend(self.steps[sid].parents)
        return [self.steps[i] for i in sorted(needed)]

    def format_proof(self, final_id: int | None = None) -> str:
        steps = self.proof(final_id)
        if not steps:
            return "(no proof)"
        renumber = {step.id: n for n, step in enumerate(steps, 1)}
        rows = []
        for step in steps:
            just = step.rule
            if step.parents:
                just += " " + ", ".join(str(renumber[p]) for p in step.parents)
                if step.substitution is not None:
                    # X_17 = variable X of (original) clause 17 -> use the proof's numbering
                    just += "   " + _COPY_VAR.sub(lambda m: f"{m.group(1)}_{renumber.get(int(m.group(2)), m.group(2))}",
                                                  str(step.substitution))
            rows.append((f"{renumber[step.id]:>3}.", str(step.clause), just))
        width = min(max(len(r[1]) for r in rows), 60)
        return "\n".join(f"{num} {clause:<{width}}   [{just}]" for num, clause, just in rows)

    def summary(self) -> str:
        kept = len(self.steps)
        return f"status: {self.status}, given clauses: {self.iterations}, clauses kept: {kept}, time: {self.elapsed:.3f}s"


# =========================================================================== the prover


class ResolutionProver:
    """Given-clause resolution prover.

    Args:
        set_of_support: never resolve two axioms with each other (default ``True``).
        subsumption:    discard subsumed clauses (default ``True``).
        factoring:      use the factoring rule (needed for completeness).
        max_answers:    how many answers to collect before stopping.
        max_iterations: maximum number of given clauses to process.
        max_clauses:    maximum number of clauses kept.
        max_seconds:    wall-clock limit.
        max_weight:     discard derived clauses with more symbols than this (incomplete, but
                        keeps recursive rules from flooding the search); ``None`` = no limit.
        fifo_ratio:     every ``fifo_ratio``-th given clause is the oldest one
                        instead of the lightest (guarantees fairness); 0 disables it.
        on_event:       optional callback ``(message: str) -> None`` for tracing.
    """

    def __init__(
        self,
        *,
        set_of_support: bool = True,
        subsumption: bool = True,
        factoring: bool = True,
        max_answers: int = 1,
        max_iterations: int = 5000,
        max_clauses: int = 20000,
        max_seconds: float = 5.0,
        max_weight: int | None = None,
        fifo_ratio: int = 5,
        on_event: Callable[[str], None] | None = None,
    ):
        self.set_of_support = set_of_support
        self.subsumption = subsumption
        self.factoring = factoring
        self.max_answers = max_answers
        self.max_iterations = max_iterations
        self.max_clauses = max_clauses
        self.max_seconds = max_seconds
        self.max_weight = max_weight
        self.fifo_ratio = fifo_ratio
        self.on_event = on_event

    # ---------------------------------------------------------------- state
    def _reset(self) -> None:
        self.steps: dict[int, ProofStep] = {}
        self.usable: dict[int, None] = {}   # processed clauses (ordered set)
        self.sos: dict[int, None] = {}      # clauses waiting to be processed
        self.final_ids: list[int] = []
        self.answers_seen: set[Clause] = set()
        self.copies: dict[int, Clause] = {}  # cached renamed copies, see renamed_copy()
        self.next_id = 1

    def _emit(self, message: str) -> None:
        if self.on_event:
            self.on_event(message)

    def _done(self) -> bool:
        return len(self.final_ids) >= self.max_answers or any(self.steps[i].clause.is_empty() for i in self.final_ids)

    # ---------------------------------------------------------------- clause insertion
    def _add(self, clause: Clause, rule: str, *, parents=(), substitution=None, literals=(), to_sos: bool = True) -> int | None:
        clause = normalize_variables(clause)
        if clause.is_tautology():
            return None
        if self.max_weight is not None and rule not in ("axiom", "negated goal") and clause.weight() > self.max_weight:
            return None
        if clause.is_answer_clause() and any(subsumes(seen, clause) for seen in self.answers_seen):
            return None  # the same (or a more general) answer was already found
        if self.subsumption and not clause.is_empty() and not clause.is_answer_clause():
            for cid in list(self.usable) + list(self.sos):
                if subsumes(self.steps[cid].clause, clause):
                    return None

        cid = self.next_id
        self.next_id += 1
        self.steps[cid] = ProofStep(cid, clause, rule, tuple(parents), substitution, tuple(literals))
        self._emit(f"{cid:>4}. {clause}   [{self.steps[cid].justification()}]")

        if clause.is_empty() or clause.is_answer_clause():
            self.final_ids.append(cid)
            self.answers_seen.add(clause)
            return cid

        if self.subsumption:  # backward subsumption: drop clauses the new one makes redundant
            for pool in (self.usable, self.sos):
                for old in [o for o in pool if subsumes(clause, self.steps[o].clause)]:
                    del pool[old]
        (self.sos if to_sos else self.usable)[cid] = None
        return cid

    def _select_given(self, iteration: int) -> int:
        if self.fifo_ratio and iteration % self.fifo_ratio == 0:
            return next(iter(self.sos))
        return min(self.sos, key=lambda cid: (self.steps[cid].clause.weight(), cid))

    # ---------------------------------------------------------------- main loop
    def refute(self, axioms: Iterable[Clause], goals: Iterable[Clause] = (), query_variables: Iterable[Variable] = ()) -> ProofResult:
        """Try to derive the empty clause (or an answer clause) from ``axioms`` and ``goals``.

        ``goals`` are the clauses of the *negated* conjecture; with the
        set-of-support strategy they form the initial set of support.
        """
        self._reset()
        start = time.perf_counter()
        qvars = tuple(query_variables)

        def result(status: str, iterations: int) -> ProofResult:
            if self.final_ids:
                status = "proved"
            return ProofResult(status, self.steps, self.final_ids, qvars, iterations, time.perf_counter() - start)

        goals = list(goals)
        sos_axioms = not self.set_of_support or not goals
        for clause in axioms:
            cid = self._add(clause, "axiom", to_sos=sos_axioms)
            if cid is not None and not sos_axioms and self.factoring and cid in self.usable:
                for inf in factors(self.steps[cid].clause):
                    self._add(inf.clause, "factoring", parents=(cid,), substitution=inf.substitution, literals=inf.literals, to_sos=False)
        for clause in goals:
            self._add(clause, "negated goal")
        if self._done():
            return result("proved", 0)

        iteration = 0
        while self.sos:
            iteration += 1
            if iteration > self.max_iterations or len(self.steps) > self.max_clauses:
                return result("limit", iteration - 1)
            if time.perf_counter() - start > self.max_seconds:
                return result("limit", iteration - 1)

            given_id = self._select_given(iteration)
            del self.sos[given_id]
            self.usable[given_id] = None
            given = self.steps[given_id].clause
            self._emit(f"given #{given_id}: {given}")

            if self.factoring:
                for inf in factors(given):
                    self._add(inf.clause, "factoring", parents=(given_id,), substitution=inf.substitution, literals=inf.literals)
                    if self._done():
                        return result("proved", iteration)

            for partner_id in list(self.usable):
                if partner_id not in self.usable or given_id not in self.usable:
                    continue  # removed by backward subsumption in the meantime
                partner = self.copies.get(partner_id)
                if partner is None:
                    partner = self.copies[partner_id] = renamed_copy(self.steps[partner_id].clause, partner_id)
                for inf in resolvents(given, partner):
                    self._add(inf.clause, "resolution", parents=(given_id, partner_id), substitution=inf.substitution, literals=inf.literals)
                    if self._done():
                        return result("proved", iteration)

        return result("saturated", iteration)
