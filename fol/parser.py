"""A small recursive-descent parser for terms, literals, clauses and formulas.

Grammar (EBNF)::

    formula     ::= iff
    iff         ::= implication ( "<->" implication )*
    implication ::= disjunction ( "->" implication )?          (right associative)
    disjunction ::= conjunction ( "|" conjunction )*
    conjunction ::= unary ( "&" unary )*
    unary       ::= "~" unary | quantifier | "(" formula ")" | atom
    quantifier  ::= ("all" | "forall" | "exists") VAR+ "."? formula
    atom        ::= PRED ( "(" term ( "," term )* ")" )?
    term        ::= VAR | CONST | FUNC "(" term ( "," term )* ")"
    clause      ::= "[]" | literal ( "|" literal )* | "{" literal ( "," literal )* "}"

Accepted operator spellings::

    not:  ~  !  ¬          and: &  /\\  ∧         or: |  \\/  ∨
    implies:  ->  =>  →    iff: <->  <=>  ↔       quantifiers: all forall ∀ exists ∃

Identifiers starting with an uppercase letter or ``_`` are variables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .clauses import Clause
from .formulas import And, Exists, ForAll, Formula, Iff, Implies, Not, Or
from .terms import Atom, Constant, Function, Literal, Term, Variable, is_variable_name


class ParseError(ValueError):
    """Raised for syntactically invalid input; the message points at the offending position."""

    def __init__(self, message: str, text: str, position: int):
        self.text = text
        self.position = position
        pointer = " " * position + "^"
        super().__init__(f"{message}\n  {text}\n  {pointer}")


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


_TOKEN_SPEC = [
    ("WS", r"\s+"),
    ("IFF", r"<->|<=>|↔"),
    ("IMPLIES", r"->|=>|→"),
    ("AND", r"&|/\\|∧"),
    ("OR", r"\||\\/|∨"),
    ("NOT", r"~|!|¬"),
    ("FORALL", r"∀"),
    ("EXISTS", r"∃"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("LBRACE", r"\{"),
    ("RBRACE", r"\}"),
    ("COMMA", r","),
    ("DOT", r"\."),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_']*|\d+"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{kind}>{pattern})" for kind, pattern in _TOKEN_SPEC))
_QUANTIFIER_WORDS = {"all": "FORALL", "forall": "FORALL", "exists": "EXISTS"}


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ParseError(f"unexpected character {text[pos]!r}", text, pos)
        if m.lastgroup != "WS":
            tokens.append(Token(m.lastgroup, m.group(), pos))
        pos = m.end()
    tokens.append(Token("EOF", "", len(text)))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.pos = 0

    # ---------------------------------------------------------------- token helpers
    def peek(self, offset: int = 0) -> Token:
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def accept(self, kind: str) -> Token | None:
        if self.peek().kind == kind:
            return self.advance()
        return None

    def expect(self, kind: str, what: str) -> Token:
        tok = self.peek()
        if tok.kind != kind:
            found = "end of input" if tok.kind == "EOF" else repr(tok.value)
            self.error(f"expected {what}, found {found}", tok)
        return self.advance()

    def error(self, message: str, tok: Token | None = None):
        tok = tok or self.peek()
        raise ParseError(message, self.text, tok.position)

    def finish(self) -> None:
        if self.peek().kind != "EOF":
            self.error(f"unexpected {self.peek().value!r}")

    # ---------------------------------------------------------------- terms
    def term(self) -> Term:
        tok = self.expect("IDENT", "a term")
        if self.peek().kind == "LPAREN":
            if is_variable_name(tok.value):
                self.error(f"variable {tok.value} cannot have arguments (function names start with a lowercase letter)", tok)
            return Function(tok.value, self.arguments(tok))
        if is_variable_name(tok.value):
            return Variable(tok.value)
        return Constant(tok.value)

    def arguments(self, head: Token) -> tuple[Term, ...]:
        self.expect("LPAREN", "'('")
        if self.peek().kind == "RPAREN":
            self.error(f"'{head.value}()' has no arguments; write just '{head.value}'")
        args = [self.term()]
        while self.accept("COMMA"):
            args.append(self.term())
        self.expect("RPAREN", "',' or ')'")
        return tuple(args)

    def atom(self) -> Atom:
        tok = self.expect("IDENT", "a predicate")
        if is_variable_name(tok.value):
            self.error(f"predicate names start with a lowercase letter, found variable {tok.value}", tok)
        if self.peek().kind == "LPAREN":
            return Atom(tok.value, self.arguments(tok))
        return Atom(tok.value)

    def literal(self) -> Literal:
        negated = False
        while self.accept("NOT"):
            negated = not negated
        return Literal(self.atom(), negated)

    def clause(self) -> Clause:
        if self.accept("LBRACKET"):
            self.expect("RBRACKET", "']' (the empty clause is written [])")
            return Clause()
        if self.accept("LBRACE"):
            if self.accept("RBRACE"):
                return Clause()
            lits = [self.literal()]
            while self.accept("COMMA"):
                lits.append(self.literal())
            self.expect("RBRACE", "',' or '}'")
            return Clause(lits)
        lits = [self.literal()]
        while self.accept("OR"):
            lits.append(self.literal())
        return Clause(lits)

    # ---------------------------------------------------------------- formulas
    def formula(self) -> Formula:
        left = self.implication()
        while self.accept("IFF"):
            left = Iff(left, self.implication())
        return left

    def implication(self) -> Formula:
        left = self.disjunction()
        if self.accept("IMPLIES"):
            return Implies(left, self.implication())
        return left

    def disjunction(self) -> Formula:
        left = self.conjunction()
        while self.accept("OR"):
            left = Or(left, self.conjunction())
        return left

    def conjunction(self) -> Formula:
        left = self.unary()
        while self.accept("AND"):
            left = And(left, self.unary())
        return left

    def unary(self) -> Formula:
        tok = self.peek()
        if self.accept("NOT"):
            return Not(self.unary())
        if self.accept("LPAREN"):
            inner = self.formula()
            self.expect("RPAREN", "')'")
            return inner
        quantifier = self._quantifier_kind()
        if quantifier is not None:
            return self.quantified(quantifier)
        if tok.kind == "IDENT":
            return self.atom()
        found = "end of input" if tok.kind == "EOF" else repr(tok.value)
        self.error(f"expected a formula, found {found}")

    def _quantifier_kind(self) -> str | None:
        tok = self.peek()
        if tok.kind in ("FORALL", "EXISTS"):
            return tok.kind
        # 'all' / 'exists' are keywords only when followed by a variable,
        # so they remain usable as ordinary predicate names (e.g. all(X)).
        nxt = self.peek(1)
        if tok.kind == "IDENT" and tok.value in _QUANTIFIER_WORDS and nxt.kind == "IDENT" and is_variable_name(nxt.value):
            return _QUANTIFIER_WORDS[tok.value]
        return None

    def quantified(self, kind: str) -> Formula:
        self.advance()
        variables = []
        while self.peek().kind == "IDENT" and is_variable_name(self.peek().value):
            variables.append(Variable(self.advance().value))
            self.accept("COMMA")
        if not variables:
            self.error("expected a variable after the quantifier")
        self.accept("DOT")
        body = self.formula()
        cls = ForAll if kind == "FORALL" else Exists
        for var in reversed(variables):
            body = cls(var, body)
        return body


# --------------------------------------------------------------------------- public API


def _parse(text: str, rule: str):
    parser = _Parser(text)
    result = getattr(parser, rule)()
    parser.finish()
    return result


def parse_term(text: str) -> Term:
    """Parse a term such as ``f(X, g(a))``."""
    return _parse(text, "term")


def parse_atom(text: str) -> Atom:
    """Parse an atomic formula such as ``knows(john, X)``."""
    return _parse(text, "atom")


def parse_literal(text: str) -> Literal:
    """Parse a possibly negated atom such as ``~knows(john, X)``."""
    return _parse(text, "literal")


def parse_clause(text: str) -> Clause:
    """Parse a clause such as ``~man(X) | mortal(X)`` or ``{~man(X), mortal(X)}``; ``[]`` is the empty clause."""
    return _parse(text, "clause")


def parse_formula(text: str) -> Formula:
    """Parse a first-order formula such as ``all X. (man(X) -> mortal(X))``."""
    return _parse(text, "formula")


def parse_expression(text: str):
    """Parse either a term or a literal: used by the command line ``unify`` tool.

    Input starting with ``~`` is read as a literal, everything else as a term.
    """
    stripped = text.lstrip()
    if stripped[:1] in ("~", "!", "¬"):
        return parse_literal(text)
    return parse_term(text)
