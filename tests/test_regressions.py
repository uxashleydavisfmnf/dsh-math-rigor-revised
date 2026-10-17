"""Regression tests for the 0.2.3 fixes.

Each test here failed on 0.2.2. They are grouped by the defect they pin:

1. **concurrent engine use** -- pipelined MCP requests (and any two threads) used
   to corrupt z3's global context. The symptom ranged from ``Z3Exception`` on a
   later, unrelated call to a hard abort of the interpreter
   (``0xC0000374``, heap corruption). Because the worst case kills the process,
   the thread test runs in a subprocess: a regression must fail this file, not
   crash the runner.
2. **predicate sorts** -- ``P(a) |- forall x: P(x)`` raised
   ``AttributeError: 'SortRef' object has no attribute 'is_int'`` from inside
   z3py's coercion path instead of being decided.
3. **premiseless arithmetic** -- an ``arithmetic`` step citing no premises was
   recorded as merely "unchecked", so ``2 + 2 = 5`` could be written into a
   proof without the audit ever refuting it.
4. **unbounded exact closure** -- ``symbolic_numeric`` on
   ``Sum(1/k^2, (k, 1, 1000000))`` tried to build the exact rational, which
   pushed the server process past 1.2GB without answering.
5. **Sum bounds** -- ``symbolic_eval`` refused a summation whose bounds were
   already written in the expression.
"""

import concurrent.futures as futures
import os
import subprocess
import sys
import textwrap
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# An explicit RIGOR_SERVER lets this module exercise a build under test rather
# than whatever sits next to this file. A bare directory argument does the same,
# so `python test_regressions.py <server-dir>` works without the env var.
_DIR_ARGS = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isdir(a)]
SERVER_DIR = os.path.abspath(
    os.environ.get("RIGOR_SERVER")
    or (_DIR_ARGS[0] if _DIR_ARGS else os.path.join(HERE, "..", "server")))
sys.path.insert(0, SERVER_DIR)


def submodule(name: str):
    """The `rigor.<name>` module of the build under test.

    Loaded lazily so that running this file against a build that predates a
    module reports a failing test instead of a collection error.
    """
    return __import__(f"rigor.{name}", fromlist=[name])

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"   ok   {name}")
    else:
        FAILED += 1
        print(f"   FAIL {name}" + (f"   {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# 1. the engine lock exists and is re-entrant
# --------------------------------------------------------------------------- #

def test_engine_lock_is_reentrant():
    import threading

    lock = submodule("engine").ENGINE_LOCK
    check("the engine lock is an RLock", hasattr(lock, "_is_owned"))
    check("the engine lock starts free", not lock._is_owned())
    with lock:
        with lock:  # nested entry must not deadlock
            acquired = True
        check("the engine lock nests", acquired)
    check("the engine lock is released again", not lock._is_owned())
    check("the engine lock is one process-wide object",
          lock is submodule("engine").ENGINE_LOCK)
    check("a thread can take the lock after release",
          _thread_can_acquire(lock))


def _thread_can_acquire(lock):
    import threading

    seen = []

    def worker():
        with lock:
            seen.append(True)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=10)
    return seen == [True]


# --------------------------------------------------------------------------- #
# 2. concurrent solver use must not corrupt or kill the process
# --------------------------------------------------------------------------- #

STATEMENTS = [
    "forall n in Z: n + 1 > n",
    "forall x in R: x^2 >= x",
    "forall n in Z: n < n + 0",
    "forall x in R: x^2 - 2 = 0",
    "forall n in N: 2^n > n^2",
    "exists x in R: x^2 + 1 = 0",
]


def test_concurrent_calls_in_process():
    check_valid = submodule("smt").check_valid
    for workers in (2, 4, 8):
        # Bounded on purpose: on a build without the lock this either raises or
        # wedges the solver, and a regression test has to report that rather than
        # hang the runner.
        statuses, problems = [], []
        with futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pending = [pool.submit(check_valid, s) for s in STATEMENTS * 2]
            for job in pending:
                try:
                    statuses.append(job.result(timeout=60).status)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{type(exc).__name__}: {str(exc)[:60]}")
        check(f"{workers} threads x 12 solver calls all answer",
              len(statuses) == 12
              and all(s in ("proven", "refuted", "unknown") for s in statuses),
              f"{len(statuses)} answered, problems={problems[:3]}")


def test_concurrent_calls_in_subprocess():
    """The pre-0.2.3 failure here was a native abort, so isolate it."""
    script = textwrap.dedent(
        """
        import concurrent.futures as futures, sys
        sys.path.insert(0, sys.argv[1])
        from rigor.smt import check_valid
        STATEMENTS = [
            "forall n in Z: n + 1 > n",
            "forall x in R: x^2 >= x",
            "forall n in Z: n < n + 0",
            "forall x in R: x^2 - 2 = 0",
        ]
        with futures.ThreadPoolExecutor(max_workers=4) as pool:
            out = list(pool.map(check_valid, STATEMENTS * 4))
        statuses = sorted({r.status for r in out})
        assert len(out) == 16, out
        assert set(statuses) <= {"proven", "refuted", "unknown"}, statuses
        print("OK", len(out), statuses)
        """
    )
    server_dir = SERVER_DIR
    try:
        completed = subprocess.run([sys.executable, "-c", script, server_dir],
                                   capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        check("16 concurrent solver calls survive in a fresh process", False,
              "the child wedged: no answer within 180s (the pre-0.2.3 symptom)")
        return
    check("16 concurrent solver calls survive in a fresh process",
          completed.returncode == 0 and "OK 16" in (completed.stdout or ""),
          f"exit={completed.returncode} stdout={(completed.stdout or '').strip()[-160:]} "
          f"stderr={(completed.stderr or '').strip()[-200:]}")


# --------------------------------------------------------------------------- #
# 3. predicate sorts: the SortRef crash
# --------------------------------------------------------------------------- #

def test_predicate_sort_unification():
    cases = [
        ("P(a) does not entail forall x: P(x)", ["P(a)"], "forall x: P(x)", "refuted"),
        ("P(a) entails exists x: P(x)", ["P(a)"], "exists x: P(x)", "proven"),
        ("forall x in Z: P(x) entails exists x in Z: P(x)",
         ["forall x in Z: P(x)"], "exists x in Z: P(x)", "proven"),
    ]
    check_entailment = submodule("smt").check_entailment
    for label, premises, goal, expected in cases:
        try:
            outcome = check_entailment(premises, goal)
            check(label, outcome.status == expected,
                  f"expected {expected}, got {outcome.status} ({outcome.reason})")
        except Exception as exc:  # noqa: BLE001
            check(label, False, f"{type(exc).__name__}: {exc}")


def test_uninterpreted_sort_is_not_invented():
    ast = submodule("ast_nodes")
    whole = ast.And((ast.parse("forall x: P(x)"), ast.Not(ast.parse("exists x: P(x)"))))
    table = submodule("translate").SortTable(whole, declared={})
    check("with no concrete evidence the sort stays uninterpreted",
          table.sort_of("x") == "uninterpreted", f"got {table.sort_of('x')}")


def test_decimal_literals_are_not_truncated():
    """`1.5` used to reach z3 as the integer 1, which turned a claim about Z into a
    claim about R and produced a false `proven`."""
    import z3

    translate = submodule("translate")
    ast = submodule("ast_nodes")
    smt = submodule("smt")

    for text, expected in (("1.5", "3/2"), ("0.5", "1/2"), ("0.125", "1/8")):
        node = ast.parse(text)
        table = translate.SortTable(node, declared={})
        ctx, _ = translate.z3_constants(node, table)
        term = translate.ast_to_z3(node, ctx, False)
        check(f"the literal {text} keeps its value ({expected})",
              str(z3.simplify(term)) == expected, f"got {z3.simplify(term)}")

    # the soundness consequence: an integer universal says nothing about 1.5
    outcome = smt.check_entailment(["forall x in Z: P(x)"], "P(1.5)")
    check("an integer universal does not entail a claim about 1.5",
          outcome.status != "proven", f"status={outcome.status} ({outcome.reason})")
    check("and the refusal is explained, not a raw solver message",
          outcome.status == "error" and "type-check" in str(outcome.reason or ""),
          f"status={outcome.status} reason={outcome.reason}")
    outcome = smt.check_entailment(["forall n in Z: even(n)"], "even(1.5)")
    check("even() on 1.5 is refused too", outcome.status != "proven",
          f"status={outcome.status}")
    # control: this one really is valid, so it must still be proven
    outcome = smt.check_entailment(["forall n in Z: n^2 >= 0"], "forall x in R: x^2 >= 0")
    check("the true control still comes back proven", outcome.status == "proven",
          f"status={outcome.status}")


def test_sort_helpers_tolerate_sorts():
    import z3

    translate = submodule("translate")
    for function in (translate.is_int_term, translate.is_real_term):
        for value in (z3.IntSort(), z3.RealSort(), z3.BoolSort()):
            try:
                result = function(value)
                check(f"{function.__name__}({value}) is False, not an error", result is False,
                      f"returned {result!r}")
            except Exception as exc:  # noqa: BLE001
                check(f"{function.__name__}({value}) does not raise", False,
                      f"{type(exc).__name__}: {exc}")


def test_mismatched_predicate_sorts_report_clearly():
    """A genuine sort conflict must be a TranslateError with a remedy, not a z3py fault."""
    translate = submodule("translate")
    smt = submodule("smt")
    try:
        outcome = smt.check_entailment(["forall x in Z: P(x)"],
                                       "P(a)&forall x in R: P(x)")
        check("a sort conflict is reported, not crashed", True,
              f"{outcome.status}: {outcome.reason}"[:160])
    except translate.TranslateError as exc:
        check("a sort conflict is a TranslateError naming the remedy",
              "domain" in str(exc) or "sort" in str(exc), str(exc)[:160])
    except Exception as exc:  # noqa: BLE001
        check("a sort conflict does not leak a z3py AttributeError",
              not isinstance(exc, AttributeError), f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# 4. a premiseless arithmetic step that is false must be refuted
# --------------------------------------------------------------------------- #

def test_false_premiseless_arithmetic_is_refuted():
    proof = submodule("proof")
    session = proof.ProofSession(session_id="ps_regression_arith", problem="regression",
                                 goal="2 + 2 = 5")
    entry = proof.Entry(id="s1", statement="2 + 2 = 5", rule="arithmetic",
                        from_ids=[], justification="trust me", kind="step")
    session.entries = [entry]
    proof.check_entry(session, entry)
    check("a false premiseless `arithmetic` step is refuted",
          entry.verdict == "refuted", f"verdict={entry.verdict} detail={entry.detail}")


def test_true_premiseless_arithmetic_is_verified():
    proof = submodule("proof")
    session = proof.ProofSession(session_id="ps_regression_arith_true", problem="regression",
                                 goal="2 + 2 = 4")
    entry = proof.Entry(id="s1", statement="2 + 2 = 4", rule="arithmetic",
                        from_ids=[], justification="arithmetic", kind="step")
    session.entries = [entry]
    proof.check_entry(session, entry)
    check("a true premiseless `arithmetic` step is machine-verified",
          entry.verdict == "verified", f"verdict={entry.verdict} detail={entry.detail}")


def test_algebra_follows_from_its_premises():
    proof = submodule("proof")
    session = proof.ProofSession(session_id="ps_regression_algebra", problem="regression",
                                 goal="y + 1 > 0")
    given = proof.Entry(id="g1", statement="x = y", rule="", kind="given")
    premise = proof.Entry(id="g2", statement="x + 1 > 0", rule="", kind="given")
    step = proof.Entry(id="s1", statement="y + 1 > 0", rule="algebra",
                       from_ids=["g1", "g2"], justification="substitute x = y")
    session.entries = [given, premise, step]
    proof.check_entry(session, step)
    check("an algebra step is re-derived from the premises it cites",
          step.verdict == "verified", f"verdict={step.verdict} detail={step.detail}")


# --------------------------------------------------------------------------- #
# 5. exact closure must stay bounded
# --------------------------------------------------------------------------- #

def test_huge_sum_is_bounded():
    numeric_eval = submodule("symbolic").numeric_eval
    started = time.perf_counter()
    out = numeric_eval("Sum(1/k^2, (k, 1, 1000000))", {}, precision=30)
    elapsed = time.perf_counter() - started
    check("a million-term sum answers in under 30s", elapsed < 30, f"{elapsed:.2f}s")
    check("its value is the Basel partial sum",
          str(out.get("value", "")).startswith("1.644933"), str(out.get("value"))[:40])
    check("exactness is declared as not computed, not guessed",
          out.get("exactness") == "not_computed", str(out.get("exactness")))


def test_exactness_is_still_reported_when_cheap():
    numeric_eval = submodule("symbolic").numeric_eval
    out = numeric_eval("1/3 + 1/6", {}, precision=30)
    check("a plain rational is still exact", out.get("is_exact_rational") is True, str(out))
    out = numeric_eval("Sum(k, (k, 1, 100))", {}, precision=30)
    check("a small integer sum is still an exact integer",
          out.get("is_exact_integer") is True, str(out))


def test_symbolic_eval_takes_sum_bounds_from_the_expression():
    symbolic = submodule("symbolic")
    out = symbolic.symbolic_eval("Sum(k, (k, 1, n))", "sum")
    text = str(out.get("result", ""))
    check("the bounds come from the expression",
          "n**2" in text or "n*(n + 1)" in text, text[:120])
    try:
        symbolic.symbolic_eval("Sum(k, (k, 1, n))", "product")
        check("a mismatched operation still explains itself", True)
    except ValueError as exc:
        check("the error names what is missing",
              "Product" in str(exc) or "lower" in str(exc), str(exc)[:120])


def main():
    print("=" * 72)
    print("test_regressions.py -- the 0.2.3 fixes")
    print("=" * 72)
    only = [a for a in sys.argv[1:]
            if not a.startswith("-") and not os.path.isdir(a)]
    tests = [
        ("lock", test_engine_lock_is_reentrant),
        ("threads", test_concurrent_calls_in_process),
        ("subprocess", test_concurrent_calls_in_subprocess),
        ("predicates", test_predicate_sort_unification),
        ("sorts", test_uninterpreted_sort_is_not_invented),
        ("decimals", test_decimal_literals_are_not_truncated),
        ("sortref", test_sort_helpers_tolerate_sorts),
        ("sortconflict", test_mismatched_predicate_sorts_report_clearly),
        ("arith-false", test_false_premiseless_arithmetic_is_refuted),
        ("arith-true", test_true_premiseless_arithmetic_is_verified),
        ("algebra", test_algebra_follows_from_its_premises),
        ("sum-bounded", test_huge_sum_is_bounded),
        ("sum-exact", test_exactness_is_still_reported_when_cheap),
        ("sum-bounds", test_symbolic_eval_takes_sum_bounds_from_the_expression),
    ]
    for name, test in tests:
        if only and name not in only:
            continue
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a missing fix must be reported, not fatal
            check(f"{name} ran to completion", False,
                  f"{type(exc).__name__}: {str(exc)[:200]}")
    print(f"\n   passed {PASSED}, failed {FAILED}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
