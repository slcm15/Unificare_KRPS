
from __future__ import annotations

from dataclasses import dataclass

from .parser import parse_atom, parse_literal, parse_term
from .unify import ARITY, CLASH, OCCURS, SIGN


@dataclass(frozen=True)
class UnifyCase:
    left: str
    right: str
    expected: dict[str, str] | None     # the MGU produced by Robinson's algorithm, None = not unifiable
    explanation: str
    kind: str = "term"                  # how to parse both sides: "term", "atom" or "literal"
    failure: str | None = None          # expected failure category
    group: str = "terms"

    def parse(self):
        parser = {"term": parse_term, "atom": parse_atom, "literal": parse_literal}[self.kind]
        return parser(self.left), parser(self.right)


CASES: list[UnifyCase] = [
    # ------------------------------------------------------------------ basic terms
    UnifyCase("a", "a", {}, "Two identical constants unify with the empty substitution.", group="basic"),
    UnifyCase("a", "b", None, "Distinct constants never unify: constants are rigid symbols.", failure=CLASH, group="basic"),
    UnifyCase("X", "a", {"X": "a"}, "A variable unifies with any term not containing it.", group="basic"),
    UnifyCase("a", "X", {"X": "a"}, "Unification is symmetric: the variable may appear on either side.", group="basic"),
    UnifyCase("X", "Y", {"X": "Y"}, "Two variables: bind one to the other ({Y/X} would be an equally general MGU).", group="basic"),
    UnifyCase("X", "X", {}, "A variable unifies with itself; no binding is needed.", group="basic"),
    UnifyCase("X", "f(Y)", {"X": "f(Y)"}, "A variable can be bound to a compound term containing other variables.", group="basic"),

    # ------------------------------------------------------------------ compound terms
    UnifyCase("f(X)", "f(a)", {"X": "a"}, "Same function symbol and arity: unify the arguments pairwise.", group="compound"),
    UnifyCase("f(X, b)", "f(a, Y)", {"X": "a", "Y": "b"}, "Variables can be on both sides; each argument pair contributes one binding.", group="compound"),
    UnifyCase("f(X)", "g(X)", None, "Different function symbols (f vs g) clash.", failure=CLASH, group="compound"),
    UnifyCase("f(X)", "f(X, Y)", None, "Same name but different arity: f/1 and f/2 are different symbols.", failure=ARITY, group="compound"),
    UnifyCase("f(a, X)", "f(b, X)", None, "The first argument pair a = b already fails, whatever X is.", failure=CLASH, group="compound"),
    UnifyCase("f(g(X), Y)", "f(g(a), h(b))", {"X": "a", "Y": "h(b)"}, "Unification descends into nested terms.", group="compound"),
    UnifyCase("f(g(h(X)), Y)", "f(g(Y), h(a))", {"Y": "h(a)", "X": "a"},
              "Y is first bound to h(X); the later pair Y = h(a) becomes h(X) = h(a), which forces X = a.", group="compound"),

    # ------------------------------------------------------------------ shared variables
    UnifyCase("f(X, X)", "f(a, b)", None,
              "X is bound to a by the first pair; the second pair becomes a = b and clashes.", failure=CLASH, group="shared variables"),
    UnifyCase("f(X, X)", "f(a, a)", {"X": "a"}, "Repeated variable, consistent values.", group="shared variables"),
    UnifyCase("f(X, X)", "f(Y, a)", {"X": "a", "Y": "a"},
              "X/Y first, then Y = a; composing gives X/a as well (the substitution is kept idempotent).", group="shared variables"),
    UnifyCase("f(X, Y, Z)", "f(Y, Z, a)", {"X": "a", "Y": "a", "Z": "a"},
              "A chain of variable bindings X->Y->Z->a collapses to a single value.", group="shared variables"),
    UnifyCase("g(X, f(Y))", "g(f(Y), X)", {"X": "f(Y)"},
              "After X/f(Y) the second pair f(Y) = f(Y) is already identical.", group="shared variables"),
    UnifyCase("f(g(X), X)", "f(Y, a)", {"Y": "g(a)", "X": "a"},
              "Y/g(X) is updated to Y/g(a) once X/a is found: bindings are composed.", group="shared variables"),
    UnifyCase("p(X, g(X), Z)", "p(f(Y), Z, W)", {"X": "f(Y)", "Z": "g(f(Y))", "W": "g(f(Y))"},
              "Bindings propagate through several argument positions (W gets the value of Z).", group="shared variables"),

    # ------------------------------------------------------------------ occurs check
    UnifyCase("X", "f(X)", None,
              "Occurs check: X = f(X) has no finite solution (it would be f(f(f(...)))).", failure=OCCURS, group="occurs check"),
    UnifyCase("f(X, g(X))", "f(Y, Y)", None,
              "Indirect occurs check: X/Y, then Y = g(Y) fails.", failure=OCCURS, group="occurs check"),
    UnifyCase("f(X, Y)", "f(Y, g(X))", None,
              "X/Y, then the second pair becomes Y = g(Y): a cycle through two variables.", failure=OCCURS, group="occurs check"),
    UnifyCase("f(X)", "f(f(X))", None, "X = f(X) hidden one level deep.", failure=OCCURS, group="occurs check"),

    # ------------------------------------------------------------------ predicates (atoms)
    UnifyCase("knows(john, X)", "knows(john, jane)", {"X": "jane"},
              "Russell & Norvig, Sec. 9.2.2 (1): match a query against a fact.", kind="atom", group="predicates"),
    UnifyCase("knows(john, X)", "knows(Y, bill)", {"Y": "john", "X": "bill"},
              "Russell & Norvig (2): each side provides a value for the other's variable.", kind="atom", group="predicates"),
    UnifyCase("knows(john, X)", "knows(Y, mother(Y))", {"Y": "john", "X": "mother(john)"},
              "Russell & Norvig (3): X receives a compound term that depends on Y.", kind="atom", group="predicates"),
    UnifyCase("knows(john, X)", "knows(X, elizabeth)", None,
              "Russell & Norvig (4): fails only because both sentences use the name X. "
              "Sentences are universally quantified, so variables must be standardized apart first (next case).",
              kind="atom", failure=CLASH, group="predicates"),
    UnifyCase("knows(john, X)", "knows(X1, elizabeth)", {"X1": "john", "X": "elizabeth"},
              "After renaming X to X1 in the second sentence the unification succeeds.", kind="atom", group="predicates"),
    UnifyCase("loves(X, X)", "loves(romeo, juliet)", None,
              "loves(X, X) talks about self-love; romeo and juliet are different constants.", kind="atom", failure=CLASH, group="predicates"),
    UnifyCase("older(father(Y), Y)", "older(father(X), john)", {"Y": "john", "X": "john"},
              "Y/X from the nested arguments, then X = john; the composition updates Y as well.", kind="atom", group="predicates"),
    UnifyCase("p(X)", "q(X)", None, "Different predicate symbols never unify.", kind="atom", failure=CLASH, group="predicates"),
    UnifyCase("p(X, Y)", "p(a)", None, "Predicate p used with arity 2 and arity 1.", kind="atom", failure=ARITY, group="predicates"),
    UnifyCase("raining", "raining", {}, "Propositional atoms (arity 0) unify only with themselves.", kind="atom", group="predicates"),

    # ------------------------------------------------------------------ literals
    UnifyCase("~p(X, b)", "~p(a, Y)", {"X": "a", "Y": "b"},
              "Two negative literals unify if their atoms unify.", kind="literal", group="literals"),
    UnifyCase("p(X)", "~p(a)", None,
              "Literals of opposite sign do not unify; resolution instead unifies the *atoms* of complementary literals.",
              kind="literal", failure=SIGN, group="literals"),

    # ------------------------------------------------------------------ larger examples
    UnifyCase("h(X1, X2, X3)", "h(g(X0, X0), g(X1, X1), g(X2, X2))",
              {"X1": "g(X0, X0)", "X2": "g(g(X0, X0), g(X0, X0))",
               "X3": "g(g(g(X0, X0), g(X0, X0)), g(g(X0, X0), g(X0, X0)))"},
              "Worst case of the naive representation: the size of the MGU doubles with every argument (exponential growth). "
              "Shared (DAG) representations avoid this blow-up.", group="larger examples"),
    UnifyCase("tuple(a, f(X, Y), g(Z, h(W)), V)", "tuple(A, f(b, c), g(k(A), h(d)), A)",
              {"A": "a", "X": "b", "Y": "c", "Z": "k(a)", "W": "d", "V": "a"},
              "A larger term mixing every situation: constants, nested terms and a variable shared between distant positions.",
              group="larger examples"),
]
