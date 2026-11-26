"""Tests for the resolution module: inference rules, redundancy and complete proofs."""
import unittest
from pathlib import Path

from fol import KnowledgeBase, ResolutionProver, load_program, parse_clause
from fol.resolution import factors, normalize_variables, renamed_copy, resolvents, subsumes

C = parse_clause
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestInferenceRules(unittest.TestCase):
    def test_binary_resolution(self):
        out = list(resolvents(C("~man(X) | mortal(X)"), C("man(socrates)")))
        self.assertEqual([str(i.clause) for i in out], ["mortal(socrates)"])
        self.assertEqual(str(out[0].substitution), "{X/socrates}")

    def test_resolution_needs_complementary_literals(self):
        self.assertEqual(list(resolvents(C("p(X)"), C("p(a)"))), [])
        self.assertEqual(list(resolvents(C("p(a)"), C("~p(b)"))), [])

    def test_all_resolvents_are_produced(self):
        out = {str(i.clause) for i in resolvents(C("p(X) | q(X)"), C("~p(a) | ~q(b)"))}
        self.assertEqual(out, {"q(a) | ~q(b)", "p(b) | ~p(a)"})

    def test_resolving_to_the_empty_clause(self):
        out = list(resolvents(C("p(X)"), C("~p(f(Y))")))
        self.assertTrue(out[0].clause.is_empty())

    def test_standardizing_apart_matters(self):
        """p(X) and ~p(f(X)) contradict each other, but only after renaming apart."""
        self.assertEqual(list(resolvents(C("p(X)"), C("~p(f(X))"))), [])
        copy = renamed_copy(C("~p(f(X))"), 2)
        self.assertEqual(str(copy), "~p(f(X_2))")
        self.assertTrue(next(resolvents(C("p(X)"), copy)).clause.is_empty())

    def test_factoring(self):
        out = [str(i.clause) for i in factors(C("p(X) | p(a) | q(X)"))]
        self.assertEqual(out, ["p(a) | q(a)"])
        self.assertEqual(list(factors(C("p(a) | ~p(X)"))), [])  # different signs

    def test_normalize_variables(self):
        self.assertEqual(str(normalize_variables(C("p(X_3, X_7, Y_1)"))), "p(X, X1, Y)")


class TestRedundancy(unittest.TestCase):
    def test_subsumption(self):
        self.assertTrue(subsumes(C("p(X)"), C("p(a) | q(b)")))
        self.assertTrue(subsumes(C("p(X) | q(Y)"), C("p(a) | q(b) | r")))
        self.assertFalse(subsumes(C("p(a)"), C("p(X)")))
        self.assertFalse(subsumes(C("p(X, X)"), C("p(a, b)")))
        self.assertFalse(subsumes(C("p(X) | ~q(X)"), C("p(a) | ~q(b)")))

    def test_subsumption_uses_one_substitution_for_the_whole_clause(self):
        self.assertTrue(subsumes(C("p(X) | q(X)"), C("p(a) | q(a) | q(b)")))

    def test_tautology(self):
        self.assertTrue(C("p(X) | ~p(X) | q").is_tautology())
        self.assertFalse(C("p(X) | ~p(Y)").is_tautology())


class TestProver(unittest.TestCase):
    def kb(self, *sentences: str) -> KnowledgeBase:
        kb = KnowledgeBase()
        for s in sentences:
            kb.tell(s)
        return kb

    def test_socrates(self):
        kb = self.kb("all X. (man(X) -> mortal(X))", "man(socrates)")
        result = kb.ask("mortal(socrates)")
        self.assertEqual(result.status, "proved")
        proof = result.proof()
        self.assertTrue(proof[-1].clause.is_empty())
        self.assertEqual([s.rule for s in proof].count("resolution"), 2)

    def test_non_theorem_saturates(self):
        kb = self.kb("all X. (man(X) -> mortal(X))", "man(socrates)")
        result = kb.ask("mortal(zeus)")
        self.assertFalse(result.proved)
        self.assertEqual(result.status, "saturated")

    def test_answer_extraction(self):
        kb = self.kb("all X. (man(X) -> mortal(X))", "man(socrates)", "man(plato)")
        result = kb.ask("mortal(Who)", max_answers=5)
        self.assertEqual(sorted(result.answer_strings()), ["Who = plato", "Who = socrates"])

    def test_every_proof_step_is_justified(self):
        """Each resolution step can be re-derived from its parents."""
        program = load_program(EXAMPLES / "crime.fol")
        result = program.kb.ask("criminal(west)")
        for step in result.proof():
            if step.rule == "resolution":
                a, b = (result.steps[p].clause for p in step.parents)
                derived = {normalize_variables(i.clause) for i in resolvents(a, renamed_copy(b, 0))}
                self.assertIn(step.clause, derived)
            elif step.rule == "factoring":
                (a,) = (result.steps[p].clause for p in step.parents)
                self.assertIn(step.clause, {normalize_variables(i.clause) for i in factors(a)})

    def test_factoring_is_necessary_for_completeness(self):
        """{p(X) | p(Y)}, {~p(U) | ~p(V)} is unsatisfiable, but binary resolution
        alone only produces two-literal clauses: factoring is required."""
        axioms = [C("p(X) | p(Y)"), C("~p(U) | ~p(V)")]
        self.assertTrue(ResolutionProver().refute(axioms).proved)
        without = ResolutionProver(factoring=False).refute(axioms)
        self.assertFalse(without.proved)
        self.assertEqual(without.status, "saturated")

    def test_strategies_agree(self):
        """Disabling set-of-support or subsumption changes the effort, not the answer."""
        program = load_program(EXAMPLES / "curiosity.fol")
        for options in ({}, {"set_of_support": False}, {"subsumption": False}):
            with self.subTest(options=options):
                self.assertTrue(program.kb.ask("kills(curiosity, tuna)", **options).proved)

    def test_inconsistent_knowledge_base_proves_anything(self):
        kb = self.kb("p(a)", "~p(a)")
        self.assertTrue(kb.ask("q(b)", set_of_support=False).proved)

    def test_limit_status(self):
        kb = self.kb("all X. (nat(X) -> nat(s(X)))", "nat(0)")
        result = kb.ask("nat(Y) & stop(Y)", max_iterations=30)
        self.assertEqual(result.status, "limit")


class TestExamples(unittest.TestCase):
    """The example programs shipped in examples/ give the documented answers."""

    def ask(self, file: str, query: str, **options):
        return load_program(EXAMPLES / file).kb.ask(query, **options)

    def test_curiosity_killed_the_cat(self):
        self.assertTrue(self.ask("curiosity.fol", "kills(curiosity, tuna)").proved)
        self.assertFalse(self.ask("curiosity.fol", "kills(jack, tuna)").proved)

    def test_colonel_west(self):
        self.assertEqual(self.ask("crime.fol", "criminal(Who)").answer_strings(), ["Who = west"])

    def test_family(self):
        result = self.ask("family.fol", "grandparent(tom, Who)", max_answers=5)
        self.assertEqual(sorted(result.answer_strings()), ["Who = ann", "Who = pat"])
        result = self.ask("family.fol", "ancestor(Who, jim)", max_answers=3)
        self.assertEqual(sorted(result.answer_strings()), ["Who = bob", "Who = pat", "Who = tom"])
        self.assertEqual(self.ask("family.fol", "sibling(ann, Who)").answer_strings(), ["Who = pat"])
        self.assertFalse(self.ask("family.fol", "grandparent(jim, tom)").proved)

    def test_peano_arithmetic(self):
        self.assertEqual(self.ask("peano.fol", "plus(s(s(0)), s(0), R)").answer_strings(), ["R = s(s(s(0)))"])
        self.assertEqual(self.ask("peano.fol", "plus(A, s(0), s(s(s(0))))").answer_strings(), ["A = s(s(0))"])

    def test_pure_logic_theorems(self):
        self.assertTrue(self.ask("drinker.fol", "exists X. (drinks(X) -> all Y. drinks(Y))").proved)
        self.assertTrue(self.ask("barber.fol", "~(exists B. all X. (shaves(B, X) <-> ~shaves(X, X)))").proved)

    def test_every_example_file_loads(self):
        for path in sorted(EXAMPLES.glob("*.fol")):
            with self.subTest(file=path.name):
                program = load_program(path)
                self.assertTrue(program.queries)


if __name__ == "__main__":
    unittest.main()
