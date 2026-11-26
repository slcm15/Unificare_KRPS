"""Randomized (property-based) tests of the unification algorithms.

Thousands of random pairs are generated with a fixed seed (reproducible). For
each pair we check the defining properties of a most general unifier:

1. soundness       - sigma(s) == sigma(t)
2. idempotence     - sigma(sigma(e)) == sigma(e)
3. generality      - when s and t have a known common instance u, sigma(s) is
                     more general than u (u is an instance of sigma(s))
4. agreement       - Robinson and Martelli-Montanari succeed / fail together
                     and their results are equal up to variable renaming
"""
import random
import unittest

from fol import is_instance, is_variant, unify, unify_mm
from fol.terms import Constant, Function, Variable

SEED = 2026
FUNCTIONS = [("f", 1), ("g", 2), ("h", 3)]
CONSTANTS = ["a", "b", "c"]
VARIABLES = ["X", "Y", "Z", "W"]


def random_term(rng: random.Random, depth: int, variables=VARIABLES):
    roll = rng.random()
    if depth == 0 or roll < 0.3:
        if rng.random() < 0.5:
            return Variable(rng.choice(variables))
        return Constant(rng.choice(CONSTANTS))
    name, arity = rng.choice(FUNCTIONS)
    return Function(name, tuple(random_term(rng, depth - 1, variables) for _ in range(arity)))


def generalize(rng: random.Random, term, prefix: str, counter: list[int]):
    """Replace random sub-terms by fresh variables: ``term`` is an instance of the result."""
    if rng.random() < 0.25:
        counter[0] += 1
        return Variable(f"{prefix}{counter[0]}")
    if isinstance(term, Function):
        return Function(term.name, tuple(generalize(rng, a, prefix, counter) for a in term.args))
    return term


class TestRandomPairs(unittest.TestCase):
    def test_random_pairs(self):
        rng = random.Random(SEED)
        successes = 0
        for _ in range(3000):
            s, t = random_term(rng, 3), random_term(rng, 3)
            sigma, mm = unify(s, t), unify_mm(s, t)
            self.assertEqual(sigma is None, not mm, f"{s} vs {t}")
            if sigma is None:
                continue
            successes += 1
            self.assertEqual(sigma.apply(s), sigma.apply(t), f"{s} vs {t}")
            self.assertEqual(sigma.apply(sigma.apply(s)), sigma.apply(s))
            self.assertTrue(is_variant(sigma.apply(s), mm.substitution.apply(s)))
        self.assertGreater(successes, 100)  # the generator must exercise the success path

    def test_mgu_is_more_general_than_a_known_common_instance(self):
        rng = random.Random(SEED + 1)
        for _ in range(2000):
            u = random_term(rng, 4)
            counter = [0]
            s = generalize(rng, u, "L", counter)
            t = generalize(rng, u, "R", counter)
            sigma = unify(s, t)
            self.assertIsNotNone(sigma, f"{s} and {t} have the common instance {u}")
            self.assertTrue(is_instance(u, sigma.apply(s)), f"{u} must be an instance of {sigma.apply(s)}")


if __name__ == "__main__":
    unittest.main()
