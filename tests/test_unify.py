"""Tests for substitutions and the two unification algorithms.

Every case of the documented catalogue (fol/catalog.py, docs/TEST_CASES.md) is
checked, plus algebraic properties of substitutions and of the MGU.
"""
import unittest

from fol import Substitution, is_variant, match, parse_atom, parse_term, unify, unify_mm, unify_verbose
from fol.catalog import CASES
from fol.terms import Variable
from fol.unify import OCCURS, unify_sequences

T = parse_term


class TestCatalogue(unittest.TestCase):
    """The documented examples behave exactly as described."""

    def test_robinson_matches_documentation(self):
        for case in CASES:
            with self.subTest(left=case.left, right=case.right):
                a, b = case.parse()
                result = unify_verbose(a, b)
                got = result.substitution.as_strings() if result else None
                self.assertEqual(got, case.expected, case.explanation)
                self.assertEqual(result.failure, case.failure)

    def test_mgu_really_unifies(self):
        for case in CASES:
            a, b = case.parse()
            sigma = unify(a, b)
            if sigma is not None:
                with self.subTest(left=case.left, right=case.right):
                    self.assertEqual(sigma.apply(a), sigma.apply(b))
                    self.assertTrue(sigma.is_idempotent())

    def test_martelli_montanari_agrees_with_robinson(self):
        """Both algorithms succeed on the same inputs and give equivalent MGUs."""
        for case in CASES:
            with self.subTest(left=case.left, right=case.right):
                a, b = case.parse()
                r, m = unify_verbose(a, b), unify_mm(a, b)
                self.assertEqual(bool(r), bool(m))
                if r:
                    # MGUs are unique up to renaming: the common instances are variants
                    self.assertTrue(is_variant(r.substitution.apply(a), m.substitution.apply(a)))
                else:
                    self.assertEqual(r.failure, m.failure)

    def test_unification_is_symmetric(self):
        for case in CASES:
            with self.subTest(left=case.left, right=case.right):
                a, b = case.parse()
                s1, s2 = unify(a, b), unify(b, a)
                self.assertEqual(s1 is None, s2 is None)
                if s1 is not None:
                    self.assertTrue(is_variant(s1.apply(a), s2.apply(a)))


class TestSubstitution(unittest.TestCase):
    def test_apply_is_simultaneous(self):
        # {X/Y, Y/X} swaps the variables, it does not chain them
        sigma = Substitution({Variable("X"): Variable("Y"), Variable("Y"): Variable("X")})
        self.assertEqual(str(sigma.apply(T("f(X, Y)"))), "f(Y, X)")

    def test_identity_bindings_are_dropped(self):
        self.assertEqual(len(Substitution({Variable("X"): Variable("X")})), 0)

    def test_composition_law(self):
        s = Substitution({Variable("X"): T("f(Y)")})
        t = Substitution({Variable("Y"): T("a"), Variable("Z"): T("b")})
        term = T("g(X, Y, Z)")
        self.assertEqual(s.compose(t).apply(term), t.apply(s.apply(term)))
        self.assertEqual(str(s.compose(t)), "{X/f(a), Y/a, Z/b}")

    def test_composition_is_not_commutative(self):
        s = Substitution({Variable("X"): T("a")})
        t = Substitution({Variable("X"): T("b")})
        self.assertNotEqual(s.compose(t), t.compose(s))

    def test_only_terms_can_be_bound(self):
        with self.assertRaises(TypeError):
            Substitution({Variable("X"): parse_atom("p(a)")})


class TestUnificationDetails(unittest.TestCase):
    def test_trace_is_recorded(self):
        result = unify_verbose(T("f(X, b)"), T("f(a, Y)"))
        self.assertTrue(any("bind X/a" in step for step in result.steps))
        self.assertTrue(result.steps[-1].startswith("SUCCESS"))

    def test_existing_substitution_is_extended(self):
        start = Substitution({Variable("X"): T("a")})
        self.assertIsNone(unify(T("X"), T("b"), start))
        self.assertEqual(str(unify(T("f(X, Y)"), T("f(a, b)"), start)), "{X/a, Y/b}")

    def test_without_occurs_check_cyclic_binding_is_accepted(self):
        """Prolog omits the occurs check for speed; the result is then unsound."""
        self.assertIsNone(unify(T("X"), T("f(X)")))
        sigma = unify(T("X"), T("f(X)"), occurs_check=False)
        self.assertIsNotNone(sigma)
        self.assertNotEqual(sigma.apply(T("X")), sigma.apply(T("f(X)")))  # not a real unifier

    def test_occurs_failure_category(self):
        self.assertEqual(unify_verbose(T("f(X)"), T("f(g(X))")).failure, OCCURS)

    def test_atom_and_term_do_not_unify(self):
        result = unify_verbose(parse_atom("p(a)"), T("p(a)"))
        self.assertFalse(result)
        self.assertEqual(result.failure, "kind mismatch")

    def test_variable_cannot_be_bound_to_atom(self):
        self.assertIsNone(unify(T("X"), parse_atom("p(a)")))

    def test_unify_sequences(self):
        sigma = unify_sequences([T("X"), T("Y")], [T("f(Y)"), T("a")])
        self.assertEqual(str(sigma), "{X/f(a), Y/a}")
        self.assertIsNone(unify_sequences([T("X")], [T("a"), T("b")]))

    def test_deeply_nested_terms(self):
        """The algorithm itself is iterative (explicit stack), so depth is not a problem."""
        deep_left, deep_right = "X", "a"
        for _ in range(200):
            deep_left, deep_right = f"f({deep_left})", f"f({deep_right})"
        self.assertEqual(str(unify(T(deep_left), T(deep_right))), "{X/a}")


class TestMatching(unittest.TestCase):
    def test_match_is_one_way(self):
        self.assertEqual(str(match(T("f(X, Y)"), T("f(a, Z)"))), "{X/a, Y/Z}")
        self.assertIsNone(match(T("f(a, Z)"), T("f(X, Y)")))  # constants do not match variables

    def test_match_respects_repeated_variables(self):
        self.assertIsNone(match(T("f(X, X)"), T("f(a, b)")))
        self.assertIsNotNone(match(T("f(X, X)"), T("f(Y, Y)")))

    def test_variant(self):
        self.assertTrue(is_variant(T("f(X, g(Y))"), T("f(A, g(B))")))
        self.assertFalse(is_variant(T("f(X, Y)"), T("f(A, A)")))
        self.assertFalse(is_variant(T("f(X)"), T("f(a)")))


if __name__ == "__main__":
    unittest.main()
