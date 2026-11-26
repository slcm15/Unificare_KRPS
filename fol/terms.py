"""Core syntax of first-order logic: terms, atoms and literals.

Naming convention (Prolog style, used by the parser and the printer):

* a **variable** starts with an uppercase letter or ``_``  -> ``X``, ``Person``, ``_G1``
* a **constant** starts with a lowercase letter or a digit -> ``a``, ``john``, ``0``
* a **function** term is a lowercase symbol applied to arguments -> ``f(X, a)``
* an **atom** (atomic formula) is a predicate symbol applied to terms -> ``knows(john, X)``

All objects are immutable and hashable, so they can be safely shared, put in
sets and used as dictionary keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Union


class Term:
    """Base class of all FOL terms."""

    __slots__ = ()


@dataclass(frozen=True)
class Variable(Term):
    """A logical variable, e.g. ``X``."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Constant(Term):
    """A constant symbol (a function symbol of arity 0), e.g. ``john``."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Function(Term):
    """A function symbol applied to one or more terms, e.g. ``mother(X)``."""

    name: str
    args: tuple[Term, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        if not self.args:
            raise ValueError(f"function '{self.name}' needs arguments; use Constant for arity 0")
        for arg in self.args:
            if not isinstance(arg, Term):
                raise TypeError(f"argument {arg!r} of '{self.name}' is not a term")

    @property
    def arity(self) -> int:
        return len(self.args)

    def __str__(self) -> str:
        return f"{self.name}({', '.join(map(str, self.args))})"


@dataclass(frozen=True)
class Atom:
    """An atomic formula: a predicate symbol applied to terms, e.g. ``knows(john, X)``.

    Atoms are *not* terms: a variable can never be bound to an atom.
    Arity 0 is allowed (propositional symbols such as ``raining``).
    """

    predicate: str
    args: tuple[Term, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        for arg in self.args:
            if not isinstance(arg, Term):
                raise TypeError(f"argument {arg!r} of predicate '{self.predicate}' is not a term")

    @property
    def arity(self) -> int:
        return len(self.args)

    def __str__(self) -> str:
        if not self.args:
            return self.predicate
        return f"{self.predicate}({', '.join(map(str, self.args))})"


@dataclass(frozen=True)
class Literal:
    """An atom or a negated atom, e.g. ``~knows(john, X)``."""

    atom: Atom
    negated: bool = False

    @property
    def predicate(self) -> str:
        return self.atom.predicate

    @property
    def positive(self) -> bool:
        return not self.negated

    def complement(self) -> "Literal":
        return Literal(self.atom, not self.negated)

    def is_complement_of(self, other: "Literal") -> bool:
        """True if the two literals have the same predicate symbol and arity and opposite signs."""
        return (
            self.negated != other.negated
            and self.atom.predicate == other.atom.predicate
            and self.atom.arity == other.atom.arity
        )

    def __str__(self) -> str:
        return f"~{self.atom}" if self.negated else str(self.atom)


Expression = Union[Term, Atom, Literal]


# --------------------------------------------------------------------------- helpers


def is_variable_name(name: str) -> bool:
    """Prolog convention: variables start with an uppercase letter or an underscore."""
    return bool(name) and (name[0].isupper() or name[0] == "_")


def symbol_of(expr: Expression) -> tuple[str, str, int]:
    """Return ``(kind, name, arity)`` describing the head symbol of a non-variable expression."""
    if isinstance(expr, Constant):
        return ("function", expr.name, 0)
    if isinstance(expr, Function):
        return ("function", expr.name, expr.arity)
    if isinstance(expr, Atom):
        return ("predicate", expr.predicate, expr.arity)
    if isinstance(expr, Literal):
        return ("literal", ("~" if expr.negated else "") + expr.atom.predicate, expr.atom.arity)
    raise TypeError(f"{expr!r} has no head symbol")


def arguments(expr: Expression) -> tuple:
    """Immediate sub-expressions of an expression (empty for variables and constants)."""
    if isinstance(expr, (Function, Atom)):
        return expr.args
    if isinstance(expr, Literal):
        return (expr.atom,)
    return ()


def iter_variables(expr: Expression) -> Iterator[Variable]:
    """Yield the variables of ``expr`` in depth-first, left-to-right order (with repetitions)."""
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, Variable):
            yield node
        else:
            stack.extend(reversed(arguments(node)))


def variables_of(expr: Expression) -> list[Variable]:
    """The distinct variables of ``expr`` in order of first occurrence."""
    return list(dict.fromkeys(iter_variables(expr)))


def occurs_in(var: Variable, expr: Expression) -> bool:
    """The *occurs check*: does ``var`` appear anywhere inside ``expr``?"""
    return any(v == var for v in iter_variables(expr))


def is_ground(expr: Expression) -> bool:
    """True if the expression contains no variables."""
    return next(iter_variables(expr), None) is None


def size(expr: Expression) -> int:
    """Number of symbol occurrences (variables, constants, functions, predicates)."""
    total = 0
    stack = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, Literal):
            node = node.atom
        total += 1
        stack.extend(arguments(node))
    return total


def depth(expr: Expression) -> int:
    """Nesting depth of a term (variables and constants have depth 0)."""
    args = arguments(expr.atom if isinstance(expr, Literal) else expr)
    return 0 if not args else 1 + max(depth(a) for a in args)
