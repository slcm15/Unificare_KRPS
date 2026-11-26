"""Command line interface for the unification / resolution project.

Usage examples::

    python main.py                                   # interactive shell
    python main.py unify "p(X, f(Y))" "p(a, f(b))" --trace
    python main.py unify "f(X, g(X))" "f(Y, Y)" --algorithm mm
    python main.py cnf "all X. (man(X) -> mortal(X))" --trace
    python main.py prove examples/crime.fol --proof
    python main.py demo                              # the catalogue of unification cases
    python main.py demo --markdown > docs/TEST_CASES.md
"""
from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from fol import (
    KnowledgeBase,
    ParseError,
    load_program,
    parse_formula,
    parse_literal,
    parse_term,
    to_cnf,
    unify_mm,
    unify_verbose,
)
from fol.catalog import CASES

RULE = "-" * 78


# =========================================================================== unify


def parse_pair(left: str, right: str):
    """Parse both sides as literals if either is negated, otherwise as terms.

    Atoms such as ``knows(john, X)`` parse fine as terms, so ``unify`` also
    works on predicates.
    """
    if any(s.lstrip()[:1] in ("~", "!") for s in (left, right)):
        return parse_literal(left), parse_literal(right)
    return parse_term(left), parse_term(right)


def run_unify(left: str, right: str, *, algorithm: str = "robinson", trace: bool = False, occurs_check: bool = True) -> bool:
    a, b = parse_pair(left, right)
    if algorithm == "mm":
        result = unify_mm(a, b, occurs_check=occurs_check)
    else:
        result = unify_verbose(a, b, occurs_check=occurs_check)
    name = "Martelli-Montanari" if algorithm == "mm" else "Robinson"
    print(f"unify  {a}  with  {b}   ({name})")
    if trace:
        for i, step in enumerate(result.steps, 1):
            print(f"  {i:>2}. {step}")
    if result:
        sigma = result.substitution
        print(f"  MGU      = {sigma}")
        print(f"  instance = {sigma.apply(a)}")
    else:
        print(f"  not unifiable - {result.failure}: {result.reason}")
    return result.success


# =========================================================================== cnf


def run_cnf(text: str, *, trace: bool = False) -> None:
    result = to_cnf(parse_formula(text), trace=trace)
    if trace:
        width = max(len(title) for title, _ in result.steps)
        for title, value in result.steps:
            print(f"  {title:<{width}}  {value}")
        print()
    print(f"{len(result.clauses)} clause(s):")
    for i, clause in enumerate(result.clauses, 1):
        print(f"  C{i}: {clause}")


# =========================================================================== prove


def answer_query(kb: KnowledgeBase, query: str, *, show_proof: bool = True, max_answers: int = 1, trace: bool = False, **options) -> bool:
    parse_formula(query)  # report syntax errors before printing anything
    print(f"?- {query}")
    if trace:
        options["on_event"] = lambda message: print("     " + message)
    result = kb.ask(query, max_answers=max_answers, **options)
    if result.proved:
        if result.query_variables:
            for answer in result.answer_strings():
                print(f"   answer: {answer}")
        else:
            print("   YES - the query follows from the knowledge base")
        if show_proof:
            print("   proof by refutation:")
            for line in result.format_proof().splitlines():
                print("     " + line)
    elif result.status == "saturated":
        print("   NO - the clause set is saturated: the query does not follow")
    else:
        print("   UNKNOWN - search limit reached before a proof was found")
    print(f"   ({result.summary()})")
    return result.proved


def run_prove(path: str, *, show_proof: bool, show_clauses: bool, extra_queries: list[str], **options) -> None:
    program = load_program(path)
    print(f"Knowledge base {path}: {len(program.kb.formulas)} sentence(s), {len(program.kb)} clause(s)")
    if show_clauses:
        print(program.kb)
    print(RULE)
    for query in program.queries + list(extra_queries):
        answer_query(program.kb, query, show_proof=show_proof, **options)
        print(RULE)


# =========================================================================== demo


def run_demo(*, markdown: bool = False, trace: bool = False) -> None:
    if markdown:
        print(catalogue_markdown())
        return
    group = None
    passed = 0
    for n, case in enumerate(CASES, 1):
        if case.group != group:
            group = case.group
            print(f"\n=== {group.upper()} " + "=" * (70 - len(group)))
        a, b = case.parse()
        result = unify_verbose(a, b)
        got = result.substitution.as_strings() if result else None
        ok = got == case.expected and result.failure == case.failure
        passed += ok
        print(f"\n[{n:>2}] {a}  =?=  {b}    {'OK' if ok else 'UNEXPECTED'}")
        print(f"     {result}")
        if trace:
            for step in result.steps:
                print(f"        . {step}")
        print(f"     why: {case.explanation}")
    print(f"\n{passed}/{len(CASES)} cases behave as documented.")


def catalogue_markdown() -> str:
    lines = [
        "# Unification test cases",
        "",
        "Generated by `python main.py demo --markdown` from `fol/catalog.py`;",
        "every row is also checked automatically by `tests/test_unify.py`.",
        "",
        "Notation: `{X/t}` means *X is replaced by t*. Variables start with an uppercase letter.",
    ]
    group = None
    for n, case in enumerate(CASES, 1):
        if case.group != group:
            group = case.group
            lines += ["", f"## {group.capitalize()}", "", "| # | Left | Right | Result (Robinson) | Explanation |", "|---|---|---|---|---|"]
        a, b = case.parse()
        result = unify_verbose(a, b)
        outcome = f"`{result.substitution}`" if result else f"**fail** ({result.failure})"
        lines.append(f"| {n} | `{a}` | `{b}` | {outcome} | {case.explanation.replace('|', '/')} |")
    lines += ["", "## Example trace", "", "```text", "$ python main.py unify \"f(g(X), X)\" \"f(Y, a)\" --trace"]
    a, b = parse_term("f(g(X), X)"), parse_term("f(Y, a)")
    for i, step in enumerate(unify_verbose(a, b).steps, 1):
        lines.append(f"  {i:>2}. {step}")
    lines += ["```", ""]
    return "\n".join(lines)


# =========================================================================== interactive shell

SHELL_HELP = """\
Commands
  unify <t1> = <t2>      unify two terms/atoms/literals with Robinson's algorithm (with trace)
  mm <t1> = <t2>         the same with the Martelli-Montanari algorithm
  cnf <formula>          convert a formula to clausal form, step by step
  tell <formula>         add a sentence to the knowledge base
  ask <formula>          prove a query (free variables are answer variables)
  all <formula>          like ask, but collect up to 10 answers
  load <file.fol>        load a knowledge base (and run its queries)
  kb                     list the clauses of the knowledge base
  clear                  empty the knowledge base
  trace on|off           show every clause generated by the prover
  help                   this text
  quit                   leave

Syntax:  variables X, Who, _Y   constants a, john   functions f(X)   predicates p(X, a)
         ~ not   & and   | or   -> implies   <-> iff   all X. ...   exists X. ...
"""


def shell() -> None:
    print("First-order logic: unification & resolution.  Type 'help' for the commands.")
    kb = KnowledgeBase()
    trace = False
    while True:
        try:
            line = input("fol> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        command, _, rest = line.partition(" ")
        command, rest = command.lower(), rest.strip()
        try:
            if command in ("quit", "exit", "q"):
                return
            elif command in ("help", "?"):
                print(SHELL_HELP)
            elif command in ("unify", "mm"):
                if "=" not in rest:
                    print("usage: unify <t1> = <t2>")
                    continue
                left, right = rest.split("=", 1)
                run_unify(left.strip(), right.strip(), algorithm="mm" if command == "mm" else "robinson", trace=True)
            elif command == "cnf":
                run_cnf(rest, trace=True)
            elif command == "tell":
                clauses = kb.tell(rest)
                print("ok: " + ("; ".join(map(str, clauses)) if clauses else "(tautology, nothing added)"))
            elif command in ("ask", "all"):
                answer_query(kb, rest, max_answers=10 if command == "all" else 1, trace=trace)
            elif command == "load":
                program = load_program(shlex.split(rest)[0])
                kb = program.kb
                print(f"loaded {len(kb.formulas)} sentence(s), {len(kb)} clause(s)")
                for query in program.queries:
                    answer_query(kb, query, show_proof=False)
            elif command == "kb":
                print(kb if len(kb) else "(empty)")
            elif command == "clear":
                kb = KnowledgeBase()
                print("knowledge base cleared")
            elif command == "trace":
                trace = rest.lower() == "on"
                print(f"trace {'on' if trace else 'off'}")
            else:
                print(f"unknown command {command!r}; type 'help'")
        except ParseError as exc:
            print(f"syntax error: {exc}")
        except (OSError, ValueError) as exc:
            print(f"error: {exc}")


# =========================================================================== entry point


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unification and resolution in first-order logic.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("unify", help="unify two terms, atoms or literals")
    p.add_argument("left")
    p.add_argument("right")
    p.add_argument("--algorithm", choices=["robinson", "mm"], default="robinson")
    p.add_argument("--trace", action="store_true", help="print every step of the algorithm")
    p.add_argument("--no-occurs-check", action="store_true", help="disable the occurs check (unsound!)")

    p = sub.add_parser("cnf", help="convert a formula to clausal form")
    p.add_argument("formula")
    p.add_argument("--trace", action="store_true", help="show the intermediate formulas")

    p = sub.add_parser("prove", help="load a .fol file and answer its queries")
    p.add_argument("file")
    p.add_argument("--query", "-q", action="append", default=[], help="an extra query (repeatable)")
    p.add_argument("--no-proof", action="store_true", help="do not print the proofs")
    p.add_argument("--clauses", action="store_true", help="print the clauses of the knowledge base")
    p.add_argument("--answers", type=int, default=1, help="maximum number of answers per query")
    p.add_argument("--no-sos", action="store_true", help="disable the set-of-support strategy")
    p.add_argument("--no-subsumption", action="store_true", help="disable subsumption")
    p.add_argument("--no-factoring", action="store_true", help="disable the factoring rule")
    p.add_argument("--trace", action="store_true", help="print every clause generated")
    p.add_argument("--max-seconds", type=float, default=10.0)

    p = sub.add_parser("demo", help="run the catalogue of unification cases")
    p.add_argument("--markdown", action="store_true", help="print the catalogue as a Markdown document")
    p.add_argument("--trace", action="store_true")

    sub.add_parser("shell", help="interactive shell (default)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        if args.command == "unify":
            return 0 if run_unify(args.left, args.right, algorithm=args.algorithm, trace=args.trace,
                                  occurs_check=not args.no_occurs_check) else 1
        if args.command == "cnf":
            run_cnf(args.formula, trace=args.trace)
        elif args.command == "prove":
            run_prove(args.file, show_proof=not args.no_proof, show_clauses=args.clauses, extra_queries=args.query,
                      max_answers=args.answers, set_of_support=not args.no_sos, subsumption=not args.no_subsumption,
                      factoring=not args.no_factoring, trace=args.trace, max_seconds=args.max_seconds)
        elif args.command == "demo":
            run_demo(markdown=args.markdown, trace=args.trace)
        else:
            shell()
    except ParseError as exc:
        print(f"syntax error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
