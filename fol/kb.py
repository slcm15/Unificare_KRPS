"""A knowledge base that accepts formulas (TELL) and answers queries by resolution (ASK)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .clauses import ANSWER_PREDICATE, Clause
from .cnf import SkolemNamer, to_cnf
from .formulas import Formula, Not, Or, free_variables, function_symbols
from .parser import parse_formula
from .resolution import ProofResult, ResolutionProver
from .terms import Atom


@dataclass
class KnowledgeBase:
    """A set of first-order sentences stored in clausal form.

    >>> kb = KnowledgeBase()
    >>> _ = kb.tell("all X. (man(X) -> mortal(X))")
    >>> _ = kb.tell("man(socrates)")
    >>> kb.ask("mortal(Who)").answer_strings()
    ['Who = socrates']
    """

    formulas: list[Formula] = field(default_factory=list)
    clauses: list[Clause] = field(default_factory=list)
    namer: SkolemNamer = field(default_factory=SkolemNamer)

    def tell(self, sentence: str | Formula) -> list[Clause]:
        """Add a sentence; returns the clauses it was converted to."""
        formula = parse_formula(sentence) if isinstance(sentence, str) else sentence
        self.namer.reserve(function_symbols(formula))
        new = to_cnf(formula, self.namer).clauses
        self.formulas.append(formula)
        for clause in new:
            if clause not in self.clauses:
                self.clauses.append(clause)
        return new

    def goal_clauses(self, query: str | Formula) -> tuple[list[Clause], tuple]:
        """Clauses of the negated query, with an ``Answer`` literal if the query has free variables."""
        formula = parse_formula(query) if isinstance(query, str) else query
        qvars = tuple(free_variables(formula))
        negated: Formula = Not(formula)
        if qvars:
            # Green's trick: refuting  ~q(X) | Answer(X)  leaves Answer(t) for the witness t.
            negated = Or(negated, Atom(ANSWER_PREDICATE, qvars))
        namer = SkolemNamer()
        namer.reserve(set(self.namer.reserved) | function_symbols(formula))
        namer.counter = self.namer.counter
        return to_cnf(negated, namer).clauses, qvars

    def ask(self, query: str | Formula, **prover_options) -> ProofResult:
        """Try to prove ``query``.  Free variables in the query are answer variables:
        ``ask("mortal(X)")`` asks *which* X is mortal."""
        goals, qvars = self.goal_clauses(query)
        prover = ResolutionProver(**prover_options)
        return prover.refute(self.clauses, goals, qvars)

    def entails(self, query: str | Formula, **prover_options) -> bool:
        return self.ask(query, **prover_options).proved

    def __len__(self) -> int:
        return len(self.clauses)

    def __str__(self) -> str:
        return "\n".join(f"{i:>3}. {c}" for i, c in enumerate(self.clauses, 1))


# --------------------------------------------------------------------------- .fol files


@dataclass
class Program:
    """The contents of a ``.fol`` file: a knowledge base and a list of queries."""

    kb: KnowledgeBase
    queries: list[str]


def split_statements(text: str) -> list[tuple[int, str]]:
    """Split a ``.fol`` file into statements ``(line_number, text)``.

    * ``#`` and ``%`` start a comment that runs to the end of the line;
    * a statement may continue on the next lines while parentheses are open;
    * a trailing ``.`` is optional (Prolog habit).
    """
    statements: list[tuple[int, str]] = []
    buffer, start, depth = "", 0, 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].split("%", 1)[0].strip()
        if not line:
            continue
        if not buffer:
            start = number
        buffer = f"{buffer} {line}".strip()
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            statement = buffer[:-1].rstrip() if buffer.endswith(".") else buffer
            statements.append((start, statement))
            buffer, depth = "", 0
    if buffer:
        statements.append((start, buffer))
    return statements


def load_program(path: str | Path) -> Program:
    """Load a ``.fol`` file.  Lines starting with ``?`` are queries."""
    return parse_program(Path(path).read_text(encoding="utf-8"))


def parse_program(text: str) -> Program:
    """Parse the text of a ``.fol`` program."""
    kb = KnowledgeBase()
    queries = []
    for line, statement in split_statements(text):
        try:
            if statement.startswith("?"):
                query = statement[1:].lstrip("-").strip()
                parse_formula(query)  # validate early
                queries.append(query)
            else:
                kb.tell(statement)
        except ValueError as exc:
            raise ValueError(f"line {line}: {exc}") from exc
    return Program(kb, queries)
