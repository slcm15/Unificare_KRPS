"""Conversion of arbitrary first-order formulas to clausal (conjunctive normal) form.

The classical pipeline (Russell & Norvig, section 9.5.1):

1. eliminate ``<->`` and ``->``
2. move ``~`` inwards (negation normal form)
3. standardize variables: every quantifier gets its own variable
4. Skolemize: replace existentially quantified variables by Skolem
   constants / functions of the enclosing universal variables
5. drop the universal quantifiers
6. distribute ``|`` over ``&`` and read off the clauses

Free variables of the input are treated as universally quantified.  The result
is *equisatisfiable* with the input (Skolemization does not preserve
equivalence), which is exactly what refutation needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .clauses import Clause
from .formulas import (
    BINARY,
    QUANTIFIERS,
    And,
    Exists,
    ForAll,
    Formula,
    Iff,
    Implies,
    Not,
    Or,
    all_variable_names,
    format_formula,
    free_variables,
    function_symbols,
    substitute,
)
from .terms import Atom, Constant, Function, Literal, Term, Variable


class SkolemNamer:
    """Generates fresh Skolem symbols ``sk1, sk2, ...`` that avoid the reserved names."""

    def __init__(self, prefix: str = "sk"):
        self.prefix = prefix
        self.counter = 0
        self.reserved: set[str] = set()

    def reserve(self, names: set[str]) -> None:
        self.reserved |= names

    def fresh(self) -> str:
        while True:
            self.counter += 1
            name = f"{self.prefix}{self.counter}"
            if name not in self.reserved:
                self.reserved.add(name)
                return name


@dataclass
class CNFResult:
    clauses: list[Clause]
    steps: list[tuple[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return "\n".join(str(c) for c in self.clauses)


# --------------------------------------------------------------------------- step 1


def eliminate_implications(f: Formula) -> Formula:
    """Rewrite ``A -> B`` as ``~A | B`` and ``A <-> B`` as ``(~A | B) & (~B | A)``."""
    if isinstance(f, Atom):
        return f
    if isinstance(f, Not):
        return Not(eliminate_implications(f.arg))
    if isinstance(f, QUANTIFIERS):
        return type(f)(f.var, eliminate_implications(f.body))
    left, right = eliminate_implications(f.left), eliminate_implications(f.right)
    if isinstance(f, Implies):
        return Or(Not(left), right)
    if isinstance(f, Iff):
        return And(Or(Not(left), right), Or(Not(right), left))
    return type(f)(left, right)


# --------------------------------------------------------------------------- step 2


def to_nnf(f: Formula) -> Formula:
    """Negation normal form: ``~`` is applied only to atoms (input must be free of -> and <->)."""
    if isinstance(f, Atom):
        return f
    if isinstance(f, (And, Or)):
        return type(f)(to_nnf(f.left), to_nnf(f.right))
    if isinstance(f, QUANTIFIERS):
        return type(f)(f.var, to_nnf(f.body))
    if isinstance(f, Not):
        g = f.arg
        if isinstance(g, Atom):
            return f
        if isinstance(g, Not):                       # ~~A          ==  A
            return to_nnf(g.arg)
        if isinstance(g, And):                       # ~(A & B)     ==  ~A | ~B
            return Or(to_nnf(Not(g.left)), to_nnf(Not(g.right)))
        if isinstance(g, Or):                        # ~(A | B)     ==  ~A & ~B
            return And(to_nnf(Not(g.left)), to_nnf(Not(g.right)))
        if isinstance(g, ForAll):                    # ~all X. A    ==  exists X. ~A
            return Exists(g.var, to_nnf(Not(g.body)))
        if isinstance(g, Exists):                    # ~exists X. A ==  all X. ~A
            return ForAll(g.var, to_nnf(Not(g.body)))
        return to_nnf(Not(eliminate_implications(g)))
    if isinstance(f, (Implies, Iff)):
        return to_nnf(eliminate_implications(f))
    raise TypeError(f"not a formula: {f!r}")


# --------------------------------------------------------------------------- step 3


def standardize_variables(f: Formula) -> Formula:
    """Rename quantified variables so that every quantifier binds a distinct variable,
    different from all free variables (``all X. p(X) | exists X. q(X)`` becomes
    ``all X. p(X) | exists X1. q(X1)``)."""
    used = {v.name for v in free_variables(f)}
    taken = all_variable_names(f) | used

    def fresh(base: str) -> str:
        if base not in used:
            used.add(base)
            return base
        i = 1
        while f"{base}{i}" in taken or f"{base}{i}" in used:
            i += 1
        name = f"{base}{i}"
        used.add(name)
        return name

    def go(g: Formula) -> Formula:
        if isinstance(g, Atom):
            return g
        if isinstance(g, Not):
            return Not(go(g.arg))
        if isinstance(g, BINARY):
            return type(g)(go(g.left), go(g.right))
        new_var = Variable(fresh(g.var.name))
        body = g.body if new_var == g.var else substitute(g.body, {g.var: new_var})
        return type(g)(new_var, go(body))

    return go(f)


# --------------------------------------------------------------------------- step 4


def skolemize(f: Formula, namer: SkolemNamer) -> Formula:
    """Remove existential quantifiers (input in NNF, standardized apart).

    ``exists Y`` inside the scope of ``all X1 ... Xn`` becomes the Skolem term
    ``skK(X1, ..., Xn)`` (a Skolem constant ``skK`` when n = 0).
    """
    namer.reserve(function_symbols(f))

    def go(g: Formula, universals: tuple[Variable, ...]) -> Formula:
        if isinstance(g, Atom):
            return g
        if isinstance(g, Not):
            return g
        if isinstance(g, (And, Or)):
            return type(g)(go(g.left, universals), go(g.right, universals))
        if isinstance(g, ForAll):
            return ForAll(g.var, go(g.body, universals + (g.var,)))
        if isinstance(g, Exists):
            name = namer.fresh()
            sk: Term = Function(name, universals) if universals else Constant(name)
            return go(substitute(g.body, {g.var: sk}), universals)
        raise ValueError(f"skolemize expects a formula in NNF, got {format_formula(g)}")

    return go(f, tuple(free_variables(f)))


# --------------------------------------------------------------------------- steps 5-6


def drop_universals(f: Formula) -> Formula:
    if isinstance(f, ForAll):
        return drop_universals(f.body)
    if isinstance(f, (And, Or)):
        return type(f)(drop_universals(f.left), drop_universals(f.right))
    return f


def _clause_sets(f: Formula) -> list[frozenset[Literal]]:
    """Distribute ``|`` over ``&`` on a quantifier-free NNF formula."""
    if isinstance(f, Atom):
        return [frozenset({Literal(f)})]
    if isinstance(f, Not) and isinstance(f.arg, Atom):
        return [frozenset({Literal(f.arg, True)})]
    if isinstance(f, And):
        return _clause_sets(f.left) + _clause_sets(f.right)
    if isinstance(f, Or):
        return [a | b for a in _clause_sets(f.left) for b in _clause_sets(f.right)]
    raise ValueError(f"unexpected sub-formula in CNF conversion: {format_formula(f)}")


def _distributed_formula(clauses: list[Clause]) -> str:
    if not clauses:
        return "true"
    return " & ".join(f"({c})" if len(c) > 1 and len(clauses) > 1 else str(c) for c in clauses)


def to_cnf(formula: Formula, namer: SkolemNamer | None = None, *, trace: bool = False) -> CNFResult:
    """Convert ``formula`` to a list of clauses (tautologies and duplicates are removed)."""
    namer = namer or SkolemNamer()
    steps: list[tuple[str, str]] = []

    def record(title: str, value: Formula) -> None:
        if trace:
            steps.append((title, format_formula(value)))

    record("0. input", formula)
    f = eliminate_implications(formula)
    record("1. eliminate -> and <->", f)
    f = to_nnf(f)
    record("2. move ~ inwards (NNF)", f)
    f = standardize_variables(f)
    record("3. standardize variables", f)
    f = skolemize(f, namer)
    record("4. Skolemize", f)
    f = drop_universals(f)
    record("5. drop universal quantifiers", f)

    clauses: list[Clause] = []
    seen: set[Clause] = set()
    for lits in _clause_sets(f):
        clause = Clause(lits)
        if clause.is_tautology() or clause in seen:
            continue
        seen.add(clause)
        clauses.append(clause)
    if trace:
        steps.append(("6. distribute | over & (CNF)", _distributed_formula(clauses)))
        steps.append(("7. clauses", "; ".join(f"{{{', '.join(map(str, c))}}}" for c in clauses) or "(none)"))
    return CNFResult(clauses, steps)


def clausify(formula: Formula, namer: SkolemNamer | None = None) -> list[Clause]:
    """Shortcut for ``to_cnf(formula, namer).clauses``."""
    return to_cnf(formula, namer).clauses
