"""Tests for the parser and the printer (printing must produce re-parsable text)."""
import unittest

from fol import ParseError, parse_atom, parse_clause, parse_formula, parse_literal, parse_term
from fol.formulas import And, Exists, ForAll, Implies, Not, Or
from fol.terms import Constant, Function, Variable


class TestTerms(unittest.TestCase):
    def test_variables_constants_functions(self):
        self.assertEqual(parse_term("X"), Variable("X"))
        self.assertEqual(parse_term("_tmp"), Variable("_tmp"))
        self.assertEqual(parse_term("john"), Constant("john"))
        self.assertEqual(parse_term("42"), Constant("42"))
        self.assertEqual(parse_term("f(X, a)"), Function("f", (Variable("X"), Constant("a"))))

    def test_nested_round_trip(self):
        text = "f(g(X, h(a)), Y, k(k(k(b))))"
        self.assertEqual(str(parse_term(text)), text)

    def test_errors_point_at_the_problem(self):
        for bad in ["f(", "f(a,", "f()", "X(a)", "f(a))", "f(a b)", "", "f(a, $)"]:
            with self.subTest(text=bad), self.assertRaises(ParseError):
                parse_term(bad)

    def test_error_message_has_caret(self):
        with self.assertRaises(ParseError) as ctx:
            parse_term("f(a, )")
        self.assertIn("^", str(ctx.exception))


class TestAtomsLiteralsClauses(unittest.TestCase):
    def test_atoms(self):
        self.assertEqual(str(parse_atom("knows(john, X)")), "knows(john, X)")
        self.assertEqual(parse_atom("raining").arity, 0)
        with self.assertRaises(ParseError):
            parse_atom("Knows(john)")  # predicates start with a lowercase letter

    def test_literals(self):
        self.assertTrue(parse_literal("~p(X)").negated)
        self.assertFalse(parse_literal("~~p(X)").negated)
        self.assertTrue(parse_literal("!p(X)").negated)

    def test_clauses(self):
        self.assertEqual(str(parse_clause("mortal(X) | ~man(X)")), "~man(X) | mortal(X)")
        self.assertEqual(parse_clause("{~man(X), mortal(X)}"), parse_clause("~man(X) | mortal(X)"))
        self.assertTrue(parse_clause("[]").is_empty())
        self.assertEqual(len(parse_clause("p(X) | p(X)")), 1)  # duplicates are merged


class TestFormulas(unittest.TestCase):
    def test_precedence(self):
        f = parse_formula("~p & q | r -> s")
        self.assertIsInstance(f, Implies)
        self.assertIsInstance(f.left, Or)
        self.assertIsInstance(f.left.left, And)
        self.assertIsInstance(f.left.left.left, Not)

    def test_implication_is_right_associative(self):
        f = parse_formula("p -> q -> r")
        self.assertIsInstance(f.right, Implies)

    def test_quantifier_scope_extends_right(self):
        f = parse_formula("all X. p(X) -> q(X)")
        self.assertIsInstance(f, ForAll)
        self.assertIsInstance(f.body, Implies)

    def test_multiple_quantified_variables(self):
        f = parse_formula("all X Y. exists Z. p(X, Y, Z)")
        self.assertIsInstance(f, ForAll)
        self.assertIsInstance(f.body, ForAll)
        self.assertIsInstance(f.body.body, Exists)

    def test_unicode_and_alternative_syntax(self):
        ascii_version = parse_formula("all X. (p(X) -> exists Y. (q(X, Y) & ~r(Y)))")
        for text in [
            "∀X (p(X) → ∃Y (q(X, Y) ∧ ¬r(Y)))",
            "forall X. (p(X) => exists Y. (q(X, Y) /\\ !r(Y)))",
        ]:
            with self.subTest(text=text):
                self.assertEqual(parse_formula(text), ascii_version)

    def test_keywords_are_usable_as_predicates(self):
        self.assertEqual(str(parse_formula("all(a) & exists(b)")), "all(a) & exists(b)")

    def test_printing_round_trip(self):
        for text in [
            "all X. (man(X) -> mortal(X))",
            "p | q & r",
            "(p | q) & r",
            "~(p & q) <-> ~p | ~q",
            "p -> (q -> r)",
            "(p -> q) -> r",
            "~(all X. p(X)) -> (exists X. ~p(X))",
            "all X. ((all Y. animal(Y) -> loves(X, Y)) -> (exists Y. loves(Y, X)))",
        ]:
            with self.subTest(text=text):
                f = parse_formula(text)
                self.assertEqual(parse_formula(str(f)), f)


if __name__ == "__main__":
    unittest.main()
