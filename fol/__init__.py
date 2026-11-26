"""fol - unification and resolution for first-order logic.

Quick tour::

    >>> from fol import parse_term, unify
    >>> print(unify(parse_term("knows(john, X)"), parse_term("knows(Y, mother(Y))")))
    {Y/john, X/mother(john)}

    >>> from fol import KnowledgeBase
    >>> kb = KnowledgeBase()
    >>> _ = kb.tell("all X. (man(X) -> mortal(X))")
    >>> _ = kb.tell("man(socrates)")
    >>> kb.ask("mortal(socrates)").proved
    True
"""
from .clauses import ANSWER_PREDICATE, Clause
from .cnf import SkolemNamer, to_cnf
from .formulas import And, Exists, ForAll, Iff, Implies, Not, Or, free_variables
from .kb import KnowledgeBase, Program, load_program, parse_program
from .parser import (
    ParseError,
    parse_atom,
    parse_clause,
    parse_expression,
    parse_formula,
    parse_literal,
    parse_term,
)
from .resolution import ProofResult, ResolutionProver, factors, resolvents, subsumes
from .substitution import Substitution
from .terms import Atom, Constant, Function, Literal, Term, Variable
from .unify import UnificationResult, is_instance, is_variant, match, unify, unify_mm, unify_verbose

__all__ = [
    "ANSWER_PREDICATE", "And", "Atom", "Clause", "Constant", "Exists", "ForAll", "Function", "Iff",
    "Implies", "KnowledgeBase", "Literal", "Not", "Or", "ParseError", "Program", "ProofResult",
    "ResolutionProver", "SkolemNamer", "Substitution", "Term", "UnificationResult", "Variable",
    "factors", "free_variables", "is_instance", "is_variant", "load_program", "match", "parse_atom",
    "parse_clause", "parse_expression", "parse_formula", "parse_literal", "parse_program",
    "parse_term", "resolvents", "subsumes", "to_cnf", "unify", "unify_mm", "unify_verbose",
]

__version__ = "1.0.0"
