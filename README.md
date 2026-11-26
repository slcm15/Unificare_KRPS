# Unification & Resolution in First-Order Logic

Project for **Topic 3 — Implementation of the Unification Algorithm**: the
unification algorithm for first-order logic, tested on many pairs of terms
and predicates and used inside a small resolution theorem prover.

* **Unification:** Robinson's algorithm with occurs check and a step-by-step
  trace, plus the Martelli–Montanari algorithm for comparison
* **Resolution module:** conversion of any FOL formula to clauses
  (Skolemization), binary resolution + factoring, set-of-support, subsumption,
  readable proofs and answer extraction (`criminal(Who)` → `Who = west`)
* **Tests:** 39 documented unification cases with explanations, 75 automated tests (including randomized property tests)
* **Dependencies:** none, only the Python standard library (Python ≥ 3.10)

Full documentation: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) ·
Test cases with explanations: [docs/TEST_CASES.md](docs/TEST_CASES.md)

## Quick start

```bash
python main.py demo
```

Runs the catalogue of unification cases with explanations.

```bash
python main.py unify "knows(john, X)" "knows(Y, mother(Y))" --trace
```

```text
unify  knows(john, X)  with  knows(Y, mother(Y))   (Robinson)
   1. knows(john, X)  vs  knows(Y, mother(Y))   same symbol 'knows', unify the 2 argument pair(s)
   2. john  vs  Y   bind Y/john   ->   sigma = {Y/john}
   3. X  vs  mother(john)   bind X/mother(john)   ->   sigma = {Y/john, X/mother(john)}
   4. SUCCESS: MGU = {Y/john, X/mother(john)}
  MGU      = {Y/john, X/mother(john)}
  instance = knows(john, mother(john))
```

```bash
python main.py unify "f(X, g(X))" "f(Y, Y)" --algorithm mm --trace
```

```bash
python main.py cnf "all X. (all Y. (animal(Y) -> loves(X, Y))) -> exists Y. loves(Y, X)" --trace
```

```bash
python main.py prove examples/crime.fol
```

```bash
python main.py prove examples/family.fol --answers 5 --no-proof
```

```bash
python main.py
```

With no arguments, `main.py` opens an interactive shell (`help` lists the commands).

Run the tests:

```bash
python -m unittest discover -s tests -t . -v
```

## Syntax

| | Syntax |
|---|---|
| variables | `X`, `Who`, `_tmp` (uppercase or `_`) |
| constants / functions / predicates | `john`, `0`, `mother(X)`, `knows(X, Y)` |
| connectives | `~` not, `&` and, `\|` or, `->` implies, `<->` iff (Unicode `¬ ∧ ∨ → ↔` also accepted) |
| quantifiers | `all X. φ`, `exists X Y. φ` (also `∀`, `∃`), the body extends as far right as possible |

A `.fol` file contains one sentence per line (it may continue while
parentheses are open). `#` and `%` start comments, and lines starting with `?`
are queries:

```
all X. (man(X) -> mortal(X))
man(socrates)
? mortal(Who)
```

## Using it as a library

```python
from fol import parse_term, unify, unify_verbose, KnowledgeBase

print(unify(parse_term("f(X, b)"), parse_term("f(a, Y)")))      # {X/a, Y/b}
print(unify_verbose(parse_term("X"), parse_term("f(X)")))       # FAIL (occurs check): ...

kb = KnowledgeBase()
kb.tell("all X. (man(X) -> mortal(X))")
kb.tell("man(socrates)")
result = kb.ask("mortal(Who)")
print(result.answer_strings())    # ['Who = socrates']
print(result.format_proof())
```

## Examples

| File | Shows |
|---|---|
| `socrates.fol` | the classic syllogism; yes/no questions, "who" questions, a non-theorem |
| `crime.fol` | Colonel West (AIMA §9.3): answer extraction, Skolem constant |
| `curiosity.fol` | Curiosity killed the cat (AIMA §9.5): nested quantifiers, disjunctive answers |
| `family.fol` | recursive rules, several answers per query |
| `peano.fol` | computing with unification: addition and subtraction on `s(s(0))` numerals |
| `barber.fol` | barber paradox: refutation that needs **factoring** |
| `drinker.fol` | drinker paradox: a theorem of pure logic, Skolem functions in the goal |

## Project structure

```
fol/            the library (terms, substitution, unify, parser, formulas, clauses, cnf, resolution, kb, catalog)
main.py         command line interface and interactive shell
examples/       knowledge bases with queries
tests/          unittest suite
docs/           documentation and the table of test cases
```
