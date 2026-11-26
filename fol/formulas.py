"""Abstract syntax of first-order formulas.

A formula is one of::

    Atom                      knows(john, X)
    Not(f)                    ~f
    And(f, g)                 f & g
    Or(f, g)                  f | g
    Implies(f, g)             f -> g
    Iff(f, g)                 f <-> g
    ForAll(X, f)              all X. f
    Exists(X, f)              exists X. f

Operator precedence (strongest first): ``~``, ``&``, ``|``, ``->`` (right
associative), ``<->``; the body of a quantifier extends as far right as possible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .terms import Atom, Constant, Function, Term, Variable, variables_of


@dataclass(frozen=True)
class Not:
    arg: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class And:
    left: "Formula"
    right: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class Or:
    left: "Formula"
    right: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class Implies:
    left: "Formula"
    right: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class Iff:
    left: "Formula"
    right: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class ForAll:
    var: Variable
    body: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


@dataclass(frozen=True)
class Exists:
    var: Variable
    body: "Formula"

    def __str__(self) -> str:
        return format_formula(self)


Formula = Union[Atom, Not, And, Or, Implies, Iff, ForAll, Exists]
BINARY = (And, Or, Implies, Iff)
QUANTIFIERS = (ForAll, Exists)


def conjunction(*formulas: Formula) -> Formula:
    """``f1 & f2 & ... & fn`` (left nested)."""
    if not formulas:
        raise ValueError("empty conjunction")
    result = formulas[0]
    for f in formulas[1:]:
        result = And(result, f)
    return result


def disjunction(*formulas: Formula) -> Formula:
    """``f1 | f2 | ... | fn`` (left nested)."""
    if not formulas:
        raise ValueError("empty disjunction")
    result = formulas[0]
    for f in formulas[1:]:
        result = Or(result, f)
    return result


# --------------------------------------------------------------------------- traversal


def free_variables(f: Formula) -> list[Variable]:
    """Variables that are not bound by any quantifier, in order of first occurrence."""
    result: dict[Variable, None] = {}

    def go(g: Formula, bound: frozenset[Variable]) -> None:
        if isinstance(g, Atom):
            for v in variables_of(g):
                if v not in bound:
                    result.setdefault(v)
        elif isinstance(g, Not):
            go(g.arg, bound)
        elif isinstance(g, BINARY):
            go(g.left, bound)
            go(g.right, bound)
        elif isinstance(g, QUANTIFIERS):
            go(g.body, bound | {g.var})
        else:
            raise TypeError(f"not a formula: {g!r}")

    go(f, frozenset())
    return list(result)


def all_variable_names(f: Formula) -> set[str]:
    """Names of all variables occurring in ``f`` (free, bound or quantified)."""
    names: set[str] = set()
    for node in _walk(f):
        if isinstance(node, Atom):
            names.update(v.name for v in variables_of(node))
        elif isinstance(node, QUANTIFIERS):
            names.add(node.var.name)
    return names


def function_symbols(f: Formula) -> set[str]:
    """Names of all constant and function symbols occurring in ``f``."""
    names: set[str] = set()
    for node in _walk(f):
        if isinstance(node, Atom):
            stack: list[Term] = list(node.args)
            while stack:
                t = stack.pop()
                if isinstance(t, Constant):
                    names.add(t.name)
                elif isinstance(t, Function):
                    names.add(t.name)
                    stack.extend(t.args)
    return names


def _walk(f: Formula):
    stack = [f]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, Not):
            stack.append(node.arg)
        elif isinstance(node, BINARY):
            stack.extend((node.right, node.left))
        elif isinstance(node, QUANTIFIERS):
            stack.append(node.body)


def substitute(f: Formula, mapping: dict[Variable, Term]) -> Formula:
    """Replace the *free* occurrences of variables according to ``mapping``.

    The caller must make sure that no variable capture can happen (the CNF
    converter standardizes the quantified variables apart before calling it).
    """
    from .substitution import Substitution

    if not mapping:
        return f
    if isinstance(f, Atom):
        return Substitution(mapping).apply(f)
    if isinstance(f, Not):
        return Not(substitute(f.arg, mapping))
    if isinstance(f, BINARY):
        return type(f)(substitute(f.left, mapping), substitute(f.right, mapping))
    if isinstance(f, QUANTIFIERS):
        inner = {v: t for v, t in mapping.items() if v != f.var}
        return type(f)(f.var, substitute(f.body, inner))
    raise TypeError(f"not a formula: {f!r}")


# --------------------------------------------------------------------------- printing

_PRECEDENCE = {Iff: 1, Implies: 2, Or: 3, And: 4}
_SYMBOL = {Iff: "<->", Implies: "->", Or: "|", And: "&"}


def _precedence(f: Formula) -> int:
    if isinstance(f, QUANTIFIERS):
        return 0
    if isinstance(f, Not):
        return 5
    if isinstance(f, Atom):
        return 6
    return _PRECEDENCE[type(f)]


def format_formula(f: Formula, parent: int = 0) -> str:
    """Pretty-print a formula with the minimum number of parentheses (re-parsable)."""
    if isinstance(f, Atom):
        return str(f)
    if isinstance(f, Not):
        return "~" + format_formula(f.arg, 5)
    if isinstance(f, QUANTIFIERS):
        keyword = "all" if isinstance(f, ForAll) else "exists"
        names = [str(f.var)]
        body = f.body
        while type(body) is type(f):  # collapse  all X. all Y.  into  all X Y.
            names.append(str(body.var))
            body = body.body
        text = f"{keyword} {' '.join(names)}. {format_formula(body, 0)}"
        return f"({text})" if parent > 0 else text

    op = type(f)
    p = _PRECEDENCE[op]

    def side(child: Formula, is_left: bool) -> str:
        cp = _precedence(child)
        if cp == 0:
            needs = True  # quantifiers inside binary operators are always bracketed
        elif cp != p:
            needs = cp < p
        elif op in (And, Or):
            needs = False
        elif op is Implies:
            needs = is_left
        else:
            needs = True
        inner = format_formula(child, 0)
        return f"({inner})" if needs else inner

    text = f"{side(f.left, True)} {_SYMBOL[op]} {side(f.right, False)}"
    return f"({text})" if parent > p else text
