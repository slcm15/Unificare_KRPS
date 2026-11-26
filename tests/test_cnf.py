"""Tests for the conversion to clausal form."""
import unittest

from fol import parse_formula, to_cnf
from fol.cnf import SkolemNamer, standardize_variables, to_nnf


def clauses(text: str) -> set[str]:
    return {str(c) for c in to_cnf(parse_formula(text)).clauses}


class TestCNF(unittest.TestCase):
    def test_implication(self):
        self.assertEqual(clauses("all X. (man(X) -> mortal(X))"), {"~man(X) | mortal(X)"})

    def test_equivalence(self):
        self.assertEqual(clauses("p <-> q"), {"~p | q", "p | ~q"})

    def test_distribution(self):
        self.assertEqual(clauses("(p & q) | r"), {"p | r", "q | r"})
        self.assertEqual(clauses("(p & q) | (r & s)"), {"p | r", "p | s", "q | r", "q | s"})

    def test_de_morgan_and_double_negation(self):
        self.assertEqual(clauses("~(p | ~q)"), {"~p", "q"})
        self.assertEqual(clauses("~~p"), {"p"})

    def test_skolem_constant(self):
        self.assertEqual(clauses("exists X. (dog(X) & owns(jack, X))"), {"dog(sk1)", "owns(jack, sk1)"})

    def test_skolem_function_depends_on_enclosing_universals(self):
        self.assertEqual(clauses("all X. exists Y. loves(X, Y)"), {"loves(X, sk1(X))"})
        self.assertEqual(clauses("exists Y. all X. loves(X, Y)"), {"loves(X, sk1)"})

    def test_negated_quantifiers(self):
        self.assertEqual(clauses("~(all X. p(X))"), {"~p(sk1)"})
        self.assertEqual(clauses("~(exists X. p(X))"), {"~p(X)"})

    def test_free_variables_are_universal(self):
        # p(X) -> exists Y. q(X, Y): the Skolem function must depend on the free X
        self.assertEqual(clauses("p(X) -> exists Y. q(X, Y)"), {"~p(X) | q(X, sk1(X))"})

    def test_russell_norvig_animal_lover(self):
        """AIMA 9.5.1: "Everyone who loves all animals is loved by someone"."""
        self.assertEqual(
            clauses("all X. ((all Y. (animal(Y) -> loves(X, Y))) -> exists Y. loves(Y, X))"),
            {"animal(sk1(X)) | loves(sk2(X), X)", "loves(sk2(X), X) | ~loves(X, sk1(X))"},
        )

    def test_tautologies_are_removed(self):
        self.assertEqual(clauses("p | ~p"), set())
        self.assertEqual(clauses("(p | ~p) & q"), {"q"})

    def test_standardize_variables(self):
        f = standardize_variables(parse_formula("(all X. p(X)) | (exists X. q(X))"))
        self.assertEqual(str(f), "(all X. p(X)) | (exists X1. q(X1))")

    def test_standardization_avoids_free_variables(self):
        f = standardize_variables(parse_formula("p(X) & (exists X. q(X))"))
        self.assertEqual(str(f), "p(X) & (exists X1. q(X1))")

    def test_nnf(self):
        f = to_nnf(parse_formula("~(all X. (p(X) & ~q(X)))"))
        self.assertEqual(str(f), "exists X. ~p(X) | q(X)")

    def test_skolem_names_avoid_existing_symbols(self):
        namer = SkolemNamer()
        result = to_cnf(parse_formula("p(sk1) & (exists X. q(X))"), namer)
        self.assertEqual({str(c) for c in result.clauses}, {"p(sk1)", "q(sk2)"})

    def test_trace_lists_every_step(self):
        steps = to_cnf(parse_formula("all X. (p(X) -> exists Y. q(Y))"), trace=True).steps
        self.assertEqual(len(steps), 8)
        self.assertEqual(steps[4][1], "all X. ~p(X) | q(sk1(X))")


if __name__ == "__main__":
    unittest.main()
