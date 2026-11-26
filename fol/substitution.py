
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping

from .terms import Atom, Constant, Expression, Function, Literal, Term, Variable, occurs_in


class Substitution(Mapping[Variable, Term]):
    """An immutable substitution ``{Variable -> Term}``.

    Trivial bindings ``X/X`` are dropped automatically.
    """

    __slots__ = ("_bindings",)

    def __init__(self, bindings: Mapping[Variable, Term] | Iterable[tuple[Variable, Term]] | None = None):
        raw = dict(bindings) if bindings else {}
        for var, term in raw.items():
            if not isinstance(var, Variable):
                raise TypeError(f"substitution domain must contain variables, got {var!r}")
            if not isinstance(term, Term):
                raise TypeError(f"a variable can only be bound to a term, got {term!r}")
        self._bindings: dict[Variable, Term] = {v: t for v, t in raw.items() if v != t}

    # ---------------------------------------------------------------- Mapping API
    def __getitem__(self, var: Variable) -> Term:
        return self._bindings[var]

    def __iter__(self) -> Iterator[Variable]:
        return iter(self._bindings)

    def __len__(self) -> int:
        return len(self._bindings)

    def __hash__(self) -> int:
        return hash(frozenset(self._bindings.items()))

    # ---------------------------------------------------------------- application
    def apply(self, expr: Expression) -> Expression:
        """Return ``expr`` with every bound variable replaced by its term."""
        if not self._bindings:
            return expr
        return self._apply(expr)

    __call__ = apply

    def _apply(self, expr):
        if isinstance(expr, Variable):
            return self._bindings.get(expr, expr)
        if isinstance(expr, Constant):
            return expr
        if isinstance(expr, Function):
            return Function(expr.name, tuple(self._apply(a) for a in expr.args))
        if isinstance(expr, Atom):
            return Atom(expr.predicate, tuple(self._apply(a) for a in expr.args)) if expr.args else expr
        if isinstance(expr, Literal):
            return Literal(self._apply(expr.atom), expr.negated)
        raise TypeError(f"cannot apply a substitution to {expr!r}")

    # ---------------------------------------------------------------- algebra
    def compose(self, other: "Substitution") -> "Substitution":
        """Composition ``self ; other`` - first apply ``self``, then ``other``.

        For every expression ``e``: ``self.compose(other).apply(e) == other.apply(self.apply(e))``.
        """
        result: dict[Variable, Term] = {v: other.apply(t) for v, t in self._bindings.items()}
        for v, t in other.items():
            if v not in self._bindings:
                result[v] = t
        return Substitution(result)

    def bind(self, var: Variable, term: Term) -> "Substitution":
        """Extend the substitution with ``var/term`` keeping it idempotent.

        ``term`` must already have this substitution applied and must not contain ``var``.
        """
        return self.compose(Substitution({var: term}))

    def restrict(self, variables: Iterable[Variable]) -> "Substitution":
        """Keep only the bindings of the given variables."""
        keep = set(variables)
        return Substitution({v: t for v, t in self._bindings.items() if v in keep})

    def is_idempotent(self) -> bool:
        return not any(occurs_in(v, t) for v in self._bindings for t in self._bindings.values())

    def is_renaming(self) -> bool:
        """True if the substitution maps distinct variables to distinct variables."""
        values = list(self._bindings.values())
        return all(isinstance(t, Variable) for t in values) and len(set(values)) == len(values)

    # ---------------------------------------------------------------- printing
    def as_strings(self) -> dict[str, str]:
        return {str(v): str(t) for v, t in self._bindings.items()}

    def __str__(self) -> str:
        return "{" + ", ".join(f"{v}/{t}" for v, t in self._bindings.items()) + "}"

    def __repr__(self) -> str:
        return f"Substitution({self})"


EMPTY = Substitution()
