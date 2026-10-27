"""A ladder of real projects, from a beginner's sum to a whole audited proof.

`test_real_projects.py` checks single statements. This module checks *tasks*:
things a person sits down to do, in the order they get harder, plus the
question of whether the server survives being used for them.

  1 basics        a finite sum, its closed form, a factorisation
  2 textbook      induction, including an exponential one
  3 number theory congruences, CRT, a false strengthening with a real witness
  4 competition   chained inequalities; Nesbitt is allowed to stay undecided
  5 trig/complex  De Moivre, Euler, the addition formulas
  6 applied       the solid angle of a circular window and its limits
  7 harder        Schur, a quartic, and two identities that must stay honest
  8 proof         a two-lemma proof driven through the tool layer, audited
  9 stability     long sessions, large input, pipelining, malformed input, budget

Level 8 is where the audit used to break: proving a lemma copied the proving
step's citations onto the lemma, which sits earlier in the file, so every proof
that proved its lemmas audited as "flawed: forward reference".
"""

import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
_DIR_ARGS = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isdir(a)]
SERVER_DIR = os.path.abspath(
    os.environ.get("RIGOR_SERVER")
    or (_DIR_ARGS[0] if _DIR_ARGS else str(HERE / ".." / "server")))
sys.path.insert(0, SERVER_DIR)

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


def server():
    """The MCP server module of the build under test."""
    return __import__("math_rigor_server")


def call(function, *args, **kwargs):
    payload = function(*args, **kwargs)
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:  # noqa: BLE001 - plain-text exports land here
            return {"_text": payload}
    return payload


def verdict(payload):
    return payload.get("verdict") or payload.get("status") or ""


# --------------------------------------------------------------------------- #
# 1. basics
# --------------------------------------------------------------------------- #

def test_basics():
    s = server()
    exact = call(s.symbolic_numeric, "Sum(k^2, (k, 1, 1000))")
    check("1+4+...+1000000 = 333833500",
          exact.get("exact_fraction") == "333833500"
          or str(exact.get("value", "")).startswith("333833500"),
          json.dumps(exact, ensure_ascii=False)[:200])
    check("the closed form matches for every n",
          verdict(call(s.verify_identity, "Sum(k^2, (k, 1, n))",
                       "n*(n+1)*(2*n+1)/6", variables=["n"])) == "proven")
    check("360 = 2^3 * 3^2 * 5",
          call(s.number_theory, "factorize", numbers=["360"]).get("factorization")
          == {"2": 3, "3": 2, "5": 1})


# --------------------------------------------------------------------------- #
# 2. textbook induction
# --------------------------------------------------------------------------- #

def test_induction_chapter():
    s = server()
    cases = [("sum of 1..n", "Sum(k, (k, 1, n)) = n*(n+1)/2", "1"),
             ("sum of 2^k", "Sum(2^k, (k, 0, n)) = 2^(n+1) - 1", "0"),
             ("2^n >= n+1", "2^n >= n + 1", "0"),
             ("n < 2^n", "n < 2^n", "0")]
    for label, predicate, start in cases:
        payload = call(s.verify_induction, predicate, "n", start)
        check(label, verdict(payload) == "proven",
              json.dumps(payload, ensure_ascii=False)[:250])


# --------------------------------------------------------------------------- #
# 3. number theory
# --------------------------------------------------------------------------- #

def test_number_theory_chapter():
    s = server()
    for prime in (2, 3, 5):
        check(f"Fermat: {prime} | n^{prime} - n",
              verdict(call(s.verify_forall, f"forall n in Z: {prime} | n^{prime} - n",
                           timeout_ms=5000)) == "proven")

    payload = call(s.verify_forall, "forall n in Z: 8 | n^3 - n", timeout_ms=5000)
    check("8 | n^3 - n is false", verdict(payload) == "refuted",
          json.dumps(payload, ensure_ascii=False)[:200])
    witness = (payload.get("counterexample") or {}).get("n")
    check("and the reported witness really breaks it",
          witness is not None and (int(witness) ** 3 - int(witness)) % 8 != 0,
          f"n={witness}")

    check("CRT: x = 23 (mod 105)",
          "23" in json.dumps(call(s.number_theory, "crt", residues=["2", "3", "2"],
                                  moduli=["3", "5", "7"]), ensure_ascii=False))


# --------------------------------------------------------------------------- #
# 4. competition inequalities
# --------------------------------------------------------------------------- #

def test_inequalities():
    s = server()
    check("(a+b+c)^2 >= 3(ab+bc+ca)",
          verdict(call(s.verify_forall,
                       "forall a in R: forall b in R: forall c in R: "
                       "(a+b+c)^2 >= 3*(a*b+b*c+c*a)", timeout_ms=6000)) == "proven")
    check("Cauchy-Schwarz in R^3",
          verdict(call(s.verify_forall,
                       "forall a in R: forall b in R: forall c in R: "
                       "forall x in R: forall y in R: forall z in R: "
                       "(a*x+b*y+c*z)^2 <= (a^2+b^2+c^2)*(x^2+y^2+z^2)",
                       timeout_ms=6000)) == "proven")
    # Three divisions: no polynomial reformulation, so undecided is acceptable.
    # A wrong verdict is not.
    payload = call(s.verify_forall,
                   "forall a in R: forall b in R: forall c in R: "
                   "a > 0 & b > 0 & c > 0 -> a/(b+c) + b/(c+a) + c/(a+b) >= 3/2",
                   timeout_ms=8000)
    check("Nesbitt: an honest verdict, never a wrong one",
          verdict(payload) in ("proven", "inconclusive"), verdict(payload))


# --------------------------------------------------------------------------- #
# 5. trigonometry and complex numbers
# --------------------------------------------------------------------------- #

def test_trigonometry_and_complex():
    s = server()
    for label, lhs, rhs in [
        ("cos 3x = 4cos^3 x - 3cos x", "cos(3*x)", "4*cos(x)^3 - 3*cos(x)"),
        ("sin 3x = 3sin x - 4sin^3 x", "sin(3*x)", "3*sin(x) - 4*sin(x)^3"),
        ("cos 2x = 1 - 2sin^2 x", "cos(2*x)", "1 - 2*sin(x)^2"),
    ]:
        check(label, verdict(call(s.verify_identity, lhs, rhs, variables=["x"])) == "proven")

    expanded = call(s.symbolic_eval, "(cos(x)+i*sin(x))^3", "expand",
                    assumptions=["x: real"])
    text = (expanded.get("result") or {}).get("text", "")
    check("a bare i is the imaginary unit", "-I*sin(x)" in text, text[:160])
    check("De Moivre: (cos x + i sin x)^3 = cos 3x + i sin 3x",
          verdict(call(s.verify_identity, "(cos(x)+i*sin(x))^3",
                       "cos(3*x)+i*sin(3*x)", variables=["x"])) == "proven")
    check("Euler: e^(i*pi) = -1",
          verdict(call(s.verify_identity, "exp(i*pi)", "-1")) == "proven")

    # ... but i is still an index letter where it is bound.
    total = call(s.symbolic_eval, "Sum(i^2, (i, 1, n))", "sum")
    check("a bound i stays a symbol",
          "n**3" in (total.get("result") or {}).get("text", ""),
          json.dumps(total, ensure_ascii=False)[:200])


# --------------------------------------------------------------------------- #
# 6. applied calculus: the solid angle of a circular window
# --------------------------------------------------------------------------- #

def test_applied_calculus():
    s = server()
    check("the two written forms of the solid angle agree",
          verdict(call(s.verify_identity, "2*pi*(1 - d/sqrt(d^2+R^2))",
                       "2*pi*(1 - 1/sqrt(1+(R/d)^2))",
                       variables=["d", "R"],
                       assumptions=["d: positive", "R: positive"])) == "proven")
    check("a very large window approaches 2*pi",
          verdict(call(s.verify_limit, "2*pi*(1 - d/sqrt(d^2+R^2))", "R", "oo",
                       "2*pi")) == "proven")
    check("a distant source subtends nothing",
          verdict(call(s.verify_limit, "2*pi*(1 - d/sqrt(d^2+R^2))", "d", "oo",
                       "0")) == "proven")
    check("integral of x e^(-x^2) over [0, oo) is 1/2",
          (call(s.symbolic_eval, "x*exp(-x^2)", "integrate", variable="x",
                lower="0", upper="oo").get("result") or {}).get("text", "").replace(" ", "")
          == "1/2")


# --------------------------------------------------------------------------- #
# 7. harder: Schur, a quartic, and two honest boundaries
# --------------------------------------------------------------------------- #

def test_harder_inequalities():
    s = server()
    schur = ("forall a in R: forall b in R: forall c in R: "
             "a >= 0 & b >= 0 & c >= 0 -> "
             "a^3+b^3+c^3+3*a*b*c >= "
             "a^2*b+a^2*c+b^2*a+b^2*c+c^2*a+c^2*b")
    check("Schur's inequality (r = 1, three variables)",
          verdict(call(s.verify_forall, schur, timeout_ms=8000)) == "proven")
    check("a^4+b^4+c^4 >= abc(a+b+c)",
          verdict(call(s.verify_forall,
                       "forall a in R: forall b in R: forall c in R: "
                       "a >= 0 & b >= 0 & c >= 0 -> a^4+b^4+c^4 >= a*b*c*(a+b+c)",
                       timeout_ms=8000)) == "proven")

    # sympy cannot close either of these; undecided is right, a confident wrong
    # answer is not.
    probability = call(s.verify_identity,
                       "Sum(binomial(n,k)*p^k*(1-p)^(n-k), (k, 0, n))", "1",
                       variables=["n", "p"])
    check("the binomial probability sum stays honest",
          verdict(probability) in ("proven", "inconclusive"), verdict(probability))
    geometric = call(s.verify_identity, "Sum(r^k, (k, 0, n))",
                     "(1 - r^(n+1))/(1 - r)", variables=["r", "n"])
    check("the finite geometric sum is honest about r = 1",
          verdict(geometric) in ("proven", "inconclusive"), verdict(geometric))


# --------------------------------------------------------------------------- #
# 8. a whole proof, through the tool layer
# --------------------------------------------------------------------------- #
def test_proof_with_lemmas():
    s = server()
    opened = call(s.proof_start,
                  problem="6 divides n^3 - n for every integer n",
                  goal="forall n in Z: 6 | n^3 - n",
                  variables={"n": "int"},
                  strategy="split 6 = 2*3 and prove each factor")
    session = opened.get("session_id")
    check("a session opens", bool(session))

    call(s.proof_add_given, session, "n is an integer")
    lemma_a = call(s.proof_add_lemma, session, "even case", "2 | n^3 - n")
    lemma_b = call(s.proof_add_lemma, session, "mod 3 case", "3 | n^3 - n")
    id_a = (lemma_a.get("added") or {}).get("id")
    id_b = (lemma_b.get("added") or {}).get("id")

    steps = []
    steps.append(call(s.proof_add_step, session, "forall m in Z: 2 | m^3 - m",
                      "arithmetic"))
    steps.append(call(s.proof_add_step, session, "2 | n^3 - n",
                      "universal_instantiation", from_ids=[steps[-1]["step"]["id"]],
                      proves_lemma=id_a))
    steps.append(call(s.proof_add_step, session, "forall m in Z: 3 | m^3 - m",
                      "arithmetic"))
    steps.append(call(s.proof_add_step, session, "3 | n^3 - n",
                      "universal_instantiation", from_ids=[steps[-1]["step"]["id"]],
                      proves_lemma=id_b))
    steps.append(call(s.proof_add_step, session, "6 | n^3 - n", "arithmetic",
                      from_ids=[steps[1]["step"]["id"], steps[3]["step"]["id"]]))
    steps.append(call(s.proof_add_step, session, "forall n in Z: 6 | n^3 - n",
                      "universal_generalization", from_ids=[steps[4]["step"]["id"]]))

    check("each step is machine-checked as it is added",
          all(p.get("verdict") == "verified" for p in steps),
          f"verdicts={[p.get('verdict') for p in steps]}")

    audit = call(s.proof_validate, session, steps[-1]["step"]["id"])
    check("proving a lemma does not create a forward reference",
          not any("forward reference" in f.get("issue", "") for f in audit.get("flaws", [])),
          json.dumps(audit.get("flaws"), ensure_ascii=False)[:300])
    check("the finished proof audits as verified", audit.get("verdict") == "verified",
          json.dumps(audit.get("flaws"), ensure_ascii=False)[:300])

    export = call(s.proof_export, session, "markdown")
    text = export.get("_text", "")
    check("the export names the verdict and the discharging step",
          "machine-verified" in text and "proved by" in text, text[:200])


# --------------------------------------------------------------------------- #
# 8. stability
# --------------------------------------------------------------------------- #

def test_stability_long_session():
    s = server()
    opened = call(s.proof_start, problem="long session",
                  goal="forall n in Z: 6 | n^3 - n", variables={"n": "int"})
    session = opened.get("session_id")
    added = 0
    for index in range(1, 41):
        if call(s.proof_add_step, session, f"0 <= {index}^2",
                "arithmetic").get("verdict") == "verified":
            added += 1
    check("40 steps can be appended one call at a time", added == 40, f"{added}/40")

    last = call(s.proof_add_step, session, "forall n in Z: 6 | n^3 - n", "arithmetic")
    audit = call(s.proof_validate, session, last["step"]["id"])
    check("a 41-step session audits", verdict(audit) in ("verified", "sound_with_gaps"),
          json.dumps(audit.get("flaws"), ensure_ascii=False)[:200])
    sessions = __import__("rigor.proof", fromlist=["sessions_directory"]).sessions_directory()
    check("the session is written to disk", (sessions / f"{session}.json").exists(),
          str(sessions))


def test_stability_large_input():
    s = server()
    big = " + ".join(f"{k}^2" for k in range(1, 1201))
    started = time.perf_counter()
    payload = call(s.expr_normalise, big, "text")
    check("a 1,200-term expression is accepted",
          "parsed" in payload and time.perf_counter() - started < 20,
          json.dumps(payload, ensure_ascii=False)[:200])
    deep = "(" * 400 + "x" + ")" * 400
    check("400 levels of nesting are accepted",
          "parsed" in call(s.expr_normalise, deep + " + 1", "text"))


def test_stability_malformed():
    s = server()
    bad = ["forall n in Z:", "x = ", "(", ")", "1/0", "n is an integer",
           "forall n in Z: n >", "P(", "6 || n", "\\frac{1}{", "x^{2",
           "Sum(k,(k,1,))", "forall x in R: x^2 + 1", "exists x in Z:",
           "&&", "x = = 1", "forall n in : n > 0", "2 |"]
    leaked = []
    for statement in bad:
        try:
            payload = call(s.verify_forall, statement)
        except Exception as exc:  # noqa: BLE001
            leaked.append((statement, f"raised {type(exc).__name__}: {exc}"))
            continue
        if not (payload.get("error") or payload.get("verdict") or payload.get("status")):
            leaked.append((statement, "no verdict and no error"))
    check("every malformed statement gets a structured answer", not leaked,
          json.dumps(leaked, ensure_ascii=False)[:300])


def test_stability_budget():
    s = server()
    started = time.perf_counter()
    payload = call(s.verify_forall, "forall p in Z: forall q in Z: q > 0 -> p^2 != 2*q^2",
                   timeout_ms=4000)
    elapsed = time.perf_counter() - started
    check("the sqrt(2) statement returns instead of hanging", elapsed < 40,
          f"{elapsed:.1f}s")
    check("and it is not claimed as proven", verdict(payload) != "proven", verdict(payload))


def test_stability_memory():
    """A long session must not grow the heap without bound.

    The measurement itself was wrong once: `GetProcessMemoryInfo` was called
    without declaring `argtypes`, the 64-bit process handle was truncated, the
    call failed, and the counters stayed at zero -- so the check compared 0MB
    with 0MB and could never fail.  It now reports the measurement, and says so
    when it cannot measure instead of passing silently.
    """
    s = server()
    try:
        import psutil
        read = lambda: psutil.Process().memory_info().rss / (1024 * 1024)  # noqa: E731
    except Exception:  # noqa: BLE001 - psutil is not a dependency
        print("   ..   psutil is not installed; the heap check is skipped")
        return

    base = read()
    for index in range(50):
        call(s.verify_forall, f"forall n in Z: 2 | n^2 + n + {index}*2")
        call(s.number_theory, "totient", numbers=["360"])
        call(s.logic_entails, ["~(P & Q)"], conclusion="~P | ~Q")
        call(s.expr_normalise, "(x-1)*(x+1) + x^2", "latex")
        call(s.verify_identity, "sin(x)^2 + cos(x)^2", "1", variables=["x"])
    growth = read() - base
    check("250 calls do not grow the heap without bound", growth < 120,
          f"+{growth:.0f}MB")


def main():
    only = {a.lstrip("-") for a in sys.argv[1:] if a.startswith("--")}
    groups = [
        ("basics", test_basics),
        ("induction", test_induction_chapter),
        ("number-theory", test_number_theory_chapter),
        ("inequalities", test_inequalities),
        ("trig-complex", test_trigonometry_and_complex),
        ("applied", test_applied_calculus),
        ("harder", test_harder_inequalities),
        ("proof", test_proof_with_lemmas),
        ("long-session", test_stability_long_session),
        ("large-input", test_stability_large_input),
        ("malformed", test_stability_malformed),
        ("memory", test_stability_memory),
        ("budget", test_stability_budget),
    ]
    started = time.perf_counter()
    for name, test in groups:
        if only and name not in only:
            continue
        print(f"\n=== {name} ===")
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a broken level is a finding
            check(f"{name} ran to completion", False, f"{type(exc).__name__}: {str(exc)[:300]}")
    print(f"\n   passed {PASSED}, failed {FAILED} in {time.perf_counter() - started:.1f}s")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
