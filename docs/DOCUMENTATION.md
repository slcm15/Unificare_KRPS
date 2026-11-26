# Unification and Resolution in First-Order Logic — Documentation

**Topic 3: Implementation of the Unification Algorithm**

| Task from the project statement | Where it is solved |
|---|---|
| Implement the unification algorithm | `fol/unify.py` — Robinson's algorithm (+ Martelli–Montanari for comparison) |
| Test it on different pairs of terms and predicates | `fol/catalog.py`, `tests/`, [TEST_CASES.md](TEST_CASES.md) |
| Integrate it into a small resolution module | `fol/resolution.py`, `fol/cnf.py`, `fol/kb.py` |
| Deliverables: source code, test cases with explanations, documentation | this folder |

---

## 1. Background

### 1.1 Terms, atoms and literals

The language of first-order logic (FOL) is built from:

| Concept | Example | Python class |
|---|---|---|
| variable | `X`, `Who` | `Variable` |
| constant (0-ary function) | `john`, `0` | `Constant` |
| function term | `mother(X)`, `s(s(0))` | `Function` |
| atom (predicate applied to terms) | `knows(john, X)` | `Atom` |
| literal (atom or negated atom) | `~knows(john, X)` | `Literal` |
| clause (disjunction of literals) | `~man(X) \| mortal(X)` | `Clause` |

**Syntax convention** (same as Prolog): identifiers starting with an uppercase
letter or `_` are variables, everything else is a constant, function or
predicate symbol. Terms and atoms are different syntactic categories: a
variable can be bound to a term, never to an atom.

### 1.2 Substitutions

A *substitution* `σ = {X1/t1, …, Xn/tn}` replaces every `Xi` by `ti`
**simultaneously** (e.g. `{X/Y, Y/X}` swaps two variables). Applying `σ` to an
expression `E` gives the *instance* `Eσ`.

*Composition* `σθ` means "first σ, then θ": `E(σθ) = (Eσ)θ`. It is computed as
`{X/(tθ) | X/t ∈ σ} ∪ {Y/s ∈ θ | Y ∉ dom(σ)}`. Composition is associative but
not commutative.

A substitution is *idempotent* if no variable of its domain occurs in its
range; then `(Eσ)σ = Eσ`. All unifiers built by this project are idempotent
(checked by tests).

### 1.3 Unifiers and the most general unifier

A *unifier* of `s` and `t` is a substitution `σ` with `sσ = tσ`.
`knows(john, X)` and `knows(Y, Z)` have infinitely many unifiers:
`{Y/john, X/Z}`, `{Y/john, X/a, Z/a}`, `{Y/john, X/f(b), Z/f(b)}`, …

The **most general unifier** (MGU) is a unifier `σ` such that every other
unifier `θ` can be written as `θ = σλ` for some `λ`. Here the MGU is
`{Y/john, X/Z}`: it commits to nothing more than necessary. Robinson proved
(1965) that **if two expressions are unifiable, they have an MGU, and it is
unique up to renaming of variables**. This is why resolution with MGUs is
complete: a single general inference replaces infinitely many ground ones.

---

## 2. Robinson's unification algorithm

### 2.1 Pseudocode

```
UNIFY(s, t):
    σ := {}                                  -- empty substitution
    stack := [(s, t)]
    while stack is not empty:
        (a, b) := pop(stack)
        a, b := aσ, bσ                       -- apply what we know so far
        if a = b:              continue      -- identical: nothing to do
        if a is a variable:    BIND(a, b)
        elif b is a variable:  BIND(b, a)
        elif head(a) ≠ head(b) or arity(a) ≠ arity(b):
                               FAIL "symbol clash" / "arity mismatch"
        else:                  push the argument pairs (a1,b1) … (an,bn)
    return σ

BIND(X, u):
    if X occurs in u:          FAIL "occurs check"
    σ := σ ∘ {X/u}                           -- keeps σ idempotent
```

The implementation (`fol/unify.py`, function `_robinson`) follows this
pseudocode directly. Two design decisions:

* **Explicit stack instead of recursion**, so deeply nested terms can't
  overflow Python's call stack. Arguments are pushed in reverse order, so they
  are processed left to right, the same order as the textbook recursive
  version.
* **Bindings are composed immediately** (`Substitution.bind`), so the
  substitution stays idempotent and the MGU can be read directly, without
  following chains of variable bindings.

### 2.2 Worked example

```text
$ python main.py unify "f(g(X), X)" "f(Y, a)" --trace
   1. f(g(X), X)  vs  f(Y, a)   same symbol 'f', unify the 2 argument pair(s)
   2. g(X)  vs  Y   bind Y/g(X)   ->   sigma = {Y/g(X)}
   3. X  vs  a   bind X/a   ->   sigma = {Y/g(a), X/a}
   4. SUCCESS: MGU = {Y/g(a), X/a}
```

In step 3 the binding `X/a` is applied to the range of the earlier binding, so
`Y/g(X)` becomes `Y/g(a)`.

### 2.3 The occurs check

`X` and `f(X)` must **not** unify: a solution would be the infinite term
`f(f(f(…)))`, which does not exist in FOL. The occurs check
(`terms.occurs_in`) rejects such bindings, including indirect cycles like
`f(X, g(X))` vs `f(Y, Y)` (after `X/Y`, the pair `Y = g(Y)` remains).

Prolog omits the occurs check for speed. This is unsound: the option
`occurs_check=False` (CLI `--no-occurs-check`) shows that the returned
"unifier" does not actually unify the terms (see
`test_without_occurs_check_cyclic_binding_is_accepted`). In a theorem prover
this would allow false proofs, so the check is always on in the resolution
module.

### 2.4 Failure categories

| Category | Example | Meaning |
|---|---|---|
| `symbol clash` | `f(X)` vs `g(X)`, `a` vs `b` | different function/predicate/constant symbols |
| `arity mismatch` | `f(X)` vs `f(X, Y)` | same name, different number of arguments |
| `occurs check` | `X` vs `f(X)` | binding would create an infinite term |
| `sign clash` | `p(X)` vs `~p(a)` | literals of opposite sign |
| `kind mismatch` | atom `p(a)` vs term `p(a)` | a predicate can't be unified with a term |

### 2.5 Complexity

With this representation (terms as trees, eager application of σ), the worst
case is **exponential** in time and space. Catalogue case 38 shows why:

```
h(X1, X2, X3)  =?=  h(g(X0,X0), g(X1,X1), g(X2,X2))
X1/g(X0,X0),  X2/g(g(X0,X0),g(X0,X0)),  X3/ … (size doubles each time)
```

The MGU *written as a tree* has size `O(2^n)`. Linear and almost-linear
algorithms exist (Paterson–Wegman 1978, Martelli–Montanari 1982 with
multi-equations). They represent terms as **shared DAGs**, so they never copy
a sub-term. For the problems a resolution prover sees (small terms), the
simple version is faster in practice and much easier to verify, which is why
Robinson's algorithm was chosen.

---

## 3. The Martelli–Montanari algorithm (for comparison)

`unify_mm` treats unification as solving a set of equations. Six rules are
applied until no rule matches:

| Rule | Equation | Action |
|---|---|---|
| Delete | `t = t` | remove it |
| Decompose | `f(s1..sn) = f(t1..tn)` | replace by `s1 = t1, …, sn = tn` |
| Conflict | `f(…) = g(…)` | fail |
| Swap | `t = X` (t not a variable) | rewrite as `X = t` |
| Eliminate | `X = t`, X not in t | apply `{X/t}` to all other equations |
| Check | `X = t`, X in t, t ≠ X | fail (occurs check) |

The final *solved form* `{X1 = t1, …}` is the MGU.

```text
$ python main.py unify "f(g(X), X)" "f(Y, a)" --algorithm mm --trace
   1. Decompose  f(g(X), X) = f(Y, a)   ->   g(X) = Y, X = a
   2. Swap       g(X) = Y   ->   Y = g(X)
   3. Eliminate  Y = g(X)   (apply {Y/g(X)} to the other equations)
   4. Eliminate  X = a   (apply {X/a} to the other equations)
   5. SUCCESS: solved form = {Y/g(a), X/a}
```

The test suite checks that both algorithms always agree: they succeed on the
same inputs, and their MGUs are equal up to renaming. This holds on all
catalogue cases and on 3000 random pairs.

---

## 4. The resolution module

### 4.1 Pipeline

```
 sentences (text)         query (text)
       │                       │
   parser.py               parser.py
       │                       │  negate, add Answer(vars)
    cnf.py  ──────────────  cnf.py
       │  clauses              │  clauses of ¬query
       └──────────┬────────────┘
           resolution.py   (given-clause loop; every inference calls unify)
                  │
          proof / answers / "does not follow"
```

### 4.2 Conversion to clausal form (`fol/cnf.py`)

| Step | Example: `all X. (all Y. (animal(Y) -> loves(X,Y))) -> exists Y. loves(Y,X)` |
|---|---|
| 1. eliminate `->`, `<->` | `all X. ~(all Y. ~animal(Y) \| loves(X,Y)) \| (exists Y. loves(Y,X))` |
| 2. push `~` inwards (NNF) | `all X. (exists Y. animal(Y) & ~loves(X,Y)) \| (exists Y. loves(Y,X))` |
| 3. standardize variables | `… \| (exists Y1. loves(Y1,X))` |
| 4. Skolemize | `all X. animal(sk1(X)) & ~loves(X,sk1(X)) \| loves(sk2(X),X)` |
| 5. drop `all` | `animal(sk1(X)) & ~loves(X,sk1(X)) \| loves(sk2(X),X)` |
| 6. distribute `\|` over `&` | `(animal(sk1(X)) \| loves(sk2(X),X)) & (~loves(X,sk1(X)) \| loves(sk2(X),X))` |

This matches the result in Russell & Norvig, §9.5.1 (`python main.py cnf "…" --trace`).

Skolemization replaces an existential variable by a **new** function of the
universal variables in whose scope it occurs (`sk1(X)`: "the animal X does
not love depends on X"). It preserves satisfiability, not equivalence, which
is all refutation needs. Free variables are treated as universally quantified.

### 4.3 Inference rules (`fol/resolution.py`)

**Binary resolution** — from `L1 ∨ C1` and `¬L2 ∨ C2`, with `σ = MGU(L1, L2)`,
infer `(C1 ∨ C2)σ`. *This is where the unification algorithm is used*: two
literals are complementary when their atoms unify.

**Factoring** — from `L1 ∨ L2 ∨ C` with `σ = MGU(L1, L2)` infer `(L1 ∨ C)σ`.
Binary resolution alone is **not** complete. `{p(X) ∨ p(Y)}` and `{¬p(U) ∨ ¬p(V)}`
are contradictory, but every resolvent again has two literals. The test
`test_factoring_is_necessary_for_completeness` and `examples/barber.fol`
show this.

**Standardizing apart** — before two clauses are resolved, the variables of
one are renamed (`X` → `X_3`, "X of clause 3"). Otherwise `p(X)` and
`¬p(f(X))` could not be resolved, although they contradict each other
(variables in different clauses are independent). Catalogue cases 29–30 show
the same effect for plain unification.

### 4.4 Refutation and the search strategy

To prove `KB ⊨ q` the prover shows that `KB ∧ ¬q` is unsatisfiable, by
deriving the empty clause `[]`. Resolution is **sound** and
**refutation-complete**: if `KB ⊨ q`, a refutation exists. FOL is only
semi-decidable, so when `q` does not follow the search may run forever.

The prover uses the **given-clause algorithm** (the main loop of Otter,
Prover9, E and Vampire):

```
usable := axioms;  sos := clauses of ¬query
while sos not empty:
    given := lightest clause of sos (every 5th time: the oldest — fairness)
    move given to usable
    add all factors of given, and all resolvents of given with every clause in usable
    (each new clause: normalize, drop if tautology or subsumed, delete clauses it subsumes)
    stop when [] (or an Answer clause) is derived
```

| Technique | Effect |
|---|---|
| **Set of support** | axioms are never resolved with each other; every inference involves the goal. Complete as long as the KB is consistent. |
| **Weight-based selection** | short clauses first (unit preference); combined with FIFO for fairness |
| **Forward / backward subsumption** | a clause `C` subsumes `D` if `Cθ ⊆ D`; `D` is redundant and is removed. Uses one-way matching (`unify.match`). |
| **Tautology deletion** | clauses containing `L` and `¬L` are always true |
| **Limits** | `max_iterations`, `max_clauses`, `max_seconds`, optional `max_weight`. The result is then `limit` (unknown), not `saturated` (definitely not provable). |

### 4.5 Answer extraction

For a query with free variables, such as `criminal(Who)`, the negated goal
gets an extra literal: `¬criminal(Who) ∨ Answer(Who)` (Green, 1969). Every
unification along the refutation also instantiates `Answer(Who)`. A clause
that contains only `Answer` literals counts as the empty clause, and its
arguments are the answer: `Answer(west)` → **Who = west**. When the KB only
supports a disjunction, the answer is disjunctive (`Who = curiosity or Who = jack`).
Several answers can be collected (`max_answers`).

### 4.6 Example proof (Colonel West, AIMA §9.3)

```text
$ python main.py prove examples/crime.fol -q "criminal(Who)"
   answer: Who = west
   …
    9. ~criminal(Who) | Answer(Who)                     [negated goal]
   10. ~american(X) | ~hostile(Z) | ~sells(X, Y, Z) | ~weapon(Y) | Answer(X)   [resolution 9, 1   {Who/X_1}]
   11. ~hostile(Z) | ~sells(west, Y, Z) | ~weapon(Y) | Answer(west)            [resolution 10, 7  {X/west}]
   …
   17. Answer(west)                                     [resolution 16, 8   {}]
```

Each line shows the parents and the MGU that was used.

---

## 5. Project structure

```
fol/
  terms.py         Variable, Constant, Function, Atom, Literal + helpers (occurs check, size…)
  substitution.py  Substitution: apply, compose, bind, idempotence
  unify.py         Robinson (unify, unify_verbose), Martelli–Montanari (unify_mm), match, is_variant
  parser.py        tokenizer + recursive-descent parser, readable error messages
  formulas.py      formula AST (Not, And, Or, Implies, Iff, ForAll, Exists) + printer
  clauses.py       Clause (canonical, hashable), tautology test
  cnf.py           conversion to clausal form with Skolemization (optional trace)
  resolution.py    resolution, factoring, subsumption, given-clause prover, proofs
  kb.py            KnowledgeBase (tell/ask) and .fol file loader
  catalog.py       the documented unification test cases
main.py            command line interface + interactive shell
examples/*.fol     knowledge bases with queries
tests/             unittest test suite (75 tests)
docs/              this documentation and the generated test case table
```

The code uses only the Python standard library (Python ≥ 3.10).

## 6. Testing

```bash
python -m unittest discover -s tests -t . -v
```

| File | What is tested |
|---|---|
| `test_unify.py` | all 39 catalogue cases (exact MGU and failure category), MGU properties, Robinson ≡ Martelli–Montanari, symmetry, substitution algebra (composition law, simultaneity), occurs check on/off, matching and variants |
| `test_properties.py` | randomized tests (fixed seed): soundness, idempotence and agreement on 3000 random pairs; **most-generality** on 2000 pairs built with a known common instance `u` (then `u` must be an instance of `σ(s)`) |
| `test_parser.py` | syntax, precedence, quantifier scope, Unicode operators, error messages, print → parse round trip |
| `test_cnf.py` | each conversion step, Skolem constants/functions, AIMA example, tautology removal |
| `test_resolution.py` | resolution and factoring rules, standardizing apart, subsumption, **every proof step is re-derivable from its parents**, factoring needed for completeness, all strategies agree, all example programs give the documented answers, saturation and limit statuses |

## 7. Limitations and possible extensions

* **No built-in equality.** `=` would need paramodulation or demodulation. Use
  explicit predicates instead (`same/2` in `family.fol`).
* **Term representation is not shared.** Unification is exponential in the
  worst case (§2.5). A DAG / union-find representation would make it almost linear.
* **Clause indexing.** Subsumption and partner selection scan all clauses. A
  discrimination tree or feature-vector index would be needed for thousands
  of clauses.
* **Semi-decidability.** For non-theorems over infinite domains (e.g. recursive
  rules) the search can only stop at a limit.

## 8. References

1. J. A. Robinson, *A Machine-Oriented Logic Based on the Resolution Principle*, Journal of the ACM 12(1), 1965.
2. A. Martelli, U. Montanari, *An Efficient Unification Algorithm*, ACM TOPLAS 4(2), 1982.
3. M. S. Paterson, M. N. Wegman, *Linear Unification*, JCSS 16, 1978.
4. C. C. Green, *Theorem Proving by Resolution as a Basis for Question-Answering Systems*, Machine Intelligence 4, 1969.
5. S. Russell, P. Norvig, *Artificial Intelligence: A Modern Approach*, 3rd/4th ed., chapter 9 (Inference in First-Order Logic).
6. W. McCune, *Otter 3.3 Reference Manual*, Argonne National Laboratory, 2003 (given-clause algorithm).
7. F. Baader, W. Snyder, *Unification Theory*, Handbook of Automated Reasoning, ch. 8, 2001.
