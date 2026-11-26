
from __future__ import annotations

from dataclasses import dataclass, field

from .substitution import Substitution
from .terms import (
    Atom,
    Expression,
    Literal,
    Term,
    Variable,
    arguments,
    occurs_in,
    symbol_of,
)

#: Failure categories reported by the algorithms.
CLASH = "symbol clash"
ARITY = "arity mismatch"
OCCURS = "occurs check"
SIGN = "sign clash"
KIND = "kind mismatch"


@dataclass
class UnificationResult:
    """Detailed outcome of a unification attempt.

    Attributes:
        success:      whether the expressions are unifiable.
        substitution: the MGU (``None`` on failure).
        steps:        human readable trace of the algorithm.
        failure:      category of the failure (``CLASH``, ``ARITY``, ``OCCURS``, ...).
        reason:       human readable explanation of the failure.
    """

    success: bool
    substitution: Substitution | None
    steps: list[str] = field(default_factory=list)
    failure: str | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        if self.success:
            return f"MGU = {self.substitution}"
        return f"FAIL ({self.failure}): {self.reason}"


def _describe(expr: Expression) -> str:
    kind, name, arity = symbol_of(expr)
    return f"{kind} '{name}/{arity}'"


def _decompose(a: Expression, b: Expression) -> tuple[list[tuple[Expression, Expression]] | None, str | None, str | None]:
    """Compare the head symbols of two non-variable expressions.

    Returns ``(pairs_of_arguments, None, None)`` if the heads agree, otherwise
    ``(None, failure_category, explanation)``.
    """
    if isinstance(a, Literal) or isinstance(b, Literal):
        if not (isinstance(a, Literal) and isinstance(b, Literal)):
            return None, KIND, f"cannot unify literal {a} with non-literal {b}"
        if a.negated != b.negated:
            return None, SIGN, f"{a} and {b} have opposite signs"
        return [(a.atom, b.atom)], None, None
    if isinstance(a, Atom) != isinstance(b, Atom):
        atom, term = (a, b) if isinstance(a, Atom) else (b, a)
        return None, KIND, f"cannot unify the atom {atom} with the term {term}"
    kind_a, name_a, arity_a = symbol_of(a)
    kind_b, name_b, arity_b = symbol_of(b)
    if name_a != name_b:
        return None, CLASH, f"{_describe(a)} differs from {_describe(b)} ({a} vs {b})"
    if arity_a != arity_b:
        return None, ARITY, f"'{name_a}' is used with {arity_a} and with {arity_b} arguments ({a} vs {b})"
    return list(zip(arguments(a), arguments(b))), None, None


# =========================================================================== Robinson


def _robinson(x: Expression, y: Expression, subst: Substitution, occurs_check: bool, steps: list[str] | None) -> UnificationResult:
    def log(message: str) -> None:
        if steps is not None:
            steps.append(message)

    def fail(category: str, reason: str) -> UnificationResult:
        log(f"FAIL: {reason}")
        return UnificationResult(False, None, steps or [], category, reason)

    sigma = subst
    # Stack of pairs still to be made equal; arguments are pushed in reverse so that
    # they are processed left to right, exactly as in the textbook recursive version.
    stack: list[tuple[Expression, Expression]] = [(x, y)]
    while stack:
        a, b = stack.pop()
        a, b = sigma.apply(a), sigma.apply(b)
        if a == b:
            log(f"{a}  ==  {b}   identical, nothing to do")
            continue

        if isinstance(a, Variable) or isinstance(b, Variable):
            var, term = (a, b) if isinstance(a, Variable) else (b, a)
            if not isinstance(term, Term):
                return fail(KIND, f"variable {var} cannot be bound to the non-term {term}")
            if occurs_check and occurs_in(var, term):
                return fail(OCCURS, f"{var} occurs in {term}; {var} = {term} would need an infinite term")
            sigma = sigma.bind(var, term)
            log(f"{a}  vs  {b}   bind {var}/{term}   ->   sigma = {sigma}")
            continue

        pairs, category, reason = _decompose(a, b)
        if pairs is None:
            return fail(category, reason)
        if pairs:
            name = symbol_of(a)[1]
            log(f"{a}  vs  {b}   same symbol '{name}', unify the {len(pairs)} argument pair(s)")
        stack.extend(reversed(pairs))

    log(f"SUCCESS: MGU = {sigma}")
    return UnificationResult(True, sigma, steps or [])


def unify(x: Expression, y: Expression, subst: Substitution | None = None, *, occurs_check: bool = True) -> Substitution | None:
    """Return the most general unifier of ``x`` and ``y`` (extending ``subst``), or ``None``.

    >>> from fol.parser import parse_term
    >>> print(unify(parse_term("f(X, b)"), parse_term("f(a, Y)")))
    {X/a, Y/b}
    """
    return _robinson(x, y, subst or Substitution(), occurs_check, None).substitution


def unify_verbose(x: Expression, y: Expression, subst: Substitution | None = None, *, occurs_check: bool = True) -> UnificationResult:
    """Like :func:`unify`, but return a :class:`UnificationResult` with a step-by-step trace."""
    return _robinson(x, y, subst or Substitution(), occurs_check, [])


def unify_sequences(xs: list[Expression], ys: list[Expression], subst: Substitution | None = None, *, occurs_check: bool = True) -> Substitution | None:
    """Simultaneously unify ``xs[i]`` with ``ys[i]`` for every ``i``."""
    if len(xs) != len(ys):
        return None
    sigma = subst or Substitution()
    for a, b in zip(xs, ys):
        sigma = unify(a, b, sigma, occurs_check=occurs_check)
        if sigma is None:
            return None
    return sigma


# =========================================================================== Martelli-Montanari


def unify_mm(x: Expression, y: Expression, *, occurs_check: bool = True) -> UnificationResult:
    """Martelli-Montanari unification by transformation of a set of equations.

    Rules (``s``, ``t`` non-variable terms, ``X`` a variable):

    ============  =================================================================
    Delete        ``t = t``                         -> remove the equation
    Decompose     ``f(s1..sn) = f(t1..tn)``         -> ``s1 = t1, ..., sn = tn``
    Conflict      ``f(...) = g(...)``               -> FAIL
    Swap          ``t = X``                         -> ``X = t``
    Eliminate     ``X = t`` and X not in t          -> apply ``{X/t}`` everywhere, keep ``X = t``
    Check         ``X = t`` and X in t, t != X      -> FAIL
    ============  =================================================================
    """
    steps: list[str] = []

    def fail(category: str, rule: str, reason: str) -> UnificationResult:
        steps.append(f"{rule:<10} FAIL: {reason}")
        return UnificationResult(False, None, steps, category, reason)

    equations: list[tuple[Expression, Expression]] = [(x, y)]
    solved: dict[Variable, Term] = {}
    while equations:
        s, t = equations.pop(0)
        if s == t:
            steps.append(f"{'Delete':<10} {s} = {t}")
            continue
        s_var, t_var = isinstance(s, Variable), isinstance(t, Variable)
        if t_var and not s_var:
            steps.append(f"{'Swap':<10} {s} = {t}   ->   {t} = {s}")
            equations.insert(0, (t, s))
            continue
        if not s_var:
            pairs, category, reason = _decompose(s, t)
            if pairs is None:
                return fail(category, "Conflict", reason)
            shown = ", ".join(f"{a} = {b}" for a, b in pairs)
            steps.append(f"{'Decompose':<10} {s} = {t}   ->   {shown}")
            equations[0:0] = pairs
            continue
        # s is a variable
        if not isinstance(t, Term):
            return fail(KIND, "Conflict", f"variable {s} cannot be bound to the non-term {t}")
        if occurs_check and occurs_in(s, t):
            return fail(OCCURS, "Check", f"{s} occurs in {t}")
        elim = Substitution({s: t})
        equations = [(elim.apply(a), elim.apply(b)) for a, b in equations]
        solved = {v: elim.apply(u) for v, u in solved.items()}
        solved[s] = t
        steps.append(f"{'Eliminate':<10} {s} = {t}   (apply {{{s}/{t}}} to the other equations)")

    sigma = Substitution(solved)
    steps.append(f"SUCCESS: solved form = {sigma}")
    return UnificationResult(True, sigma, steps)


# =========================================================================== matching


def _match(pattern: Expression, target: Expression, bindings: dict[Variable, Term]) -> dict[Variable, Term] | None:
    """One-way unification on a plain dict (identity bindings ``X->X`` are kept)."""
    stack = [(pattern, target)]
    while stack:
        p, t = stack.pop()
        if isinstance(p, Variable):
            bound = bindings.get(p)
            if bound is None:
                if not isinstance(t, Term):
                    return None
                bindings[p] = t
            elif bound != t:
                return None
            continue
        if isinstance(t, Variable):
            return None
        pairs, _, _ = _decompose(p, t)
        if pairs is None:
            return None
        stack.extend(reversed(pairs))
    return bindings


def match(pattern: Expression, target: Expression, subst: Substitution | None = None) -> Substitution | None:
    """One-way unification: find ``theta`` with ``theta(pattern) == target``.

    Only the variables of ``pattern`` may be bound; the variables of ``target``
    behave like constants.  Returns ``None`` if ``target`` is not an instance of
    ``pattern``.
    """
    result = _match(pattern, target, dict(subst) if subst else {})
    return None if result is None else Substitution(result)


def is_instance(expr: Expression, general: Expression) -> bool:
    """True if ``expr`` is an instance of ``general`` (``general`` is at least as general)."""
    return _match(general, expr, {}) is not None


def is_variant(x: Expression, y: Expression) -> bool:
    """True if ``x`` and ``y`` are equal up to a consistent renaming of variables."""
    return _match(x, y, {}) is not None and _match(y, x, {}) is not None
