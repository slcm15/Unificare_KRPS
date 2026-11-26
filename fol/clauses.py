"""Clauses: finite disjunctions of literals, the input language of resolution."""
from __future__ import annotations

from typing import Iterable, Iterator

from .substitution import Substitution
from .terms import Literal, Variable, size, variables_of

#: Predicate symbol of the answer literal used for answer extraction (Green, 1969).
#: It starts with an uppercase letter, so it can never clash with a parsed predicate.
ANSWER_PREDICATE = "Answer"


def _literal_key(lit: Literal) -> tuple:
    return (lit.atom.predicate == ANSWER_PREDICATE, lit.atom.predicate, lit.negated, str(lit))


class Clause:
    """An immutable clause ``L1 | L2 | ... | Ln``; the empty clause is written ``[]``.

    Duplicate literals are merged and the literals are kept in a canonical
    (sorted) order, so two clauses are equal iff they contain the same literals.
    """

    __slots__ = ("literals", "_hash", "_signature")

    def __init__(self, literals: Iterable[Literal] = ()):
        lits = tuple(sorted(set(literals), key=_literal_key))
        for lit in lits:
            if not isinstance(lit, Literal):
                raise TypeError(f"clauses contain literals, got {lit!r}")
        self.literals: tuple[Literal, ...] = lits
        self._hash = hash(lits)
        self._signature: frozenset | None = None

    @property
    def signature(self) -> frozenset[tuple[bool, str]]:
        """The set of ``(negated, predicate)`` pairs; a cheap pre-filter for subsumption."""
        if self._signature is None:
            self._signature = frozenset((lit.negated, lit.predicate) for lit in self.literals)
        return self._signature

    def __iter__(self) -> Iterator[Literal]:
        return iter(self.literals)

    def __len__(self) -> int:
        return len(self.literals)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Clause) and self.literals == other.literals

    def __hash__(self) -> int:
        return self._hash

    def __str__(self) -> str:
        return " | ".join(map(str, self.literals)) if self.literals else "[]"

    def __repr__(self) -> str:
        return f"Clause({self})"

    # ---------------------------------------------------------------- properties
    def is_empty(self) -> bool:
        return not self.literals

    def is_answer_clause(self) -> bool:
        """A non-empty clause made only of answer literals (a successful query)."""
        return bool(self.literals) and all(lit.predicate == ANSWER_PREDICATE for lit in self.literals)

    def is_unit(self) -> bool:
        return len(self.literals) == 1

    def is_tautology(self) -> bool:
        """True if the clause contains a literal and its complement (always true)."""
        lits = set(self.literals)
        return any(lit.complement() in lits for lit in self.literals if not lit.negated)

    def variables(self) -> list[Variable]:
        return list(dict.fromkeys(v for lit in self.literals for v in variables_of(lit)))

    def weight(self) -> int:
        """Symbol count, ignoring answer literals; used to pick the next clause to process."""
        return sum(size(lit) for lit in self.literals if lit.predicate != ANSWER_PREDICATE)

    def apply(self, subst: Substitution) -> "Clause":
        return Clause(subst.apply(lit) for lit in self.literals)

    def without(self, *literals: Literal) -> list[Literal]:
        drop = set(literals)
        return [lit for lit in self.literals if lit not in drop]
