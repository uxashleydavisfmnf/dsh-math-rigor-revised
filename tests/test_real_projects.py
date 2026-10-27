"""Real mathematics, not synthetic probes.

Every case below is a statement that occurs in a textbook, a paper, or a
competition problem, together with the answer mathematics gives it.  The suite
exists because the adversarial probes of 0.2.2/0.2.3 checked *shape* -- that a
tool returns some verdict, that it does not crash -- and several of the defects
found for 0.2.4 were invisible to that: `Sum(k, (k, 1, 100))` answered 505000
because the summation was applied twice, `x = 1 | x = 2` parsed as a conjunction
of three claims, and `verify_identity` never returned at all on a binomial sum.

Grouped by what a working mathematician would actually ask:

  A. divisibility and parity over the integers
  B. inequalities with a stated domain
  C. closed forms for sums and products
  D. identities, including the binomial ones
  E. calculus: derivatives, integrals, limits, series, roots
  F. exact integer facts
  G. propositional and predicate logic
  H. whole proofs, driven through the session audit

Sources are named per case where the statement is not simply standard.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_DIR_ARGS = [a for a in sys.argv[1:] if not a.startswith("-") and os.path.isdir(a)]
SERVER_DIR = os.path.abspath(
    os.environ.get("RIGOR_SERVER")
    or (_DIR_ARGS[0] if _DIR_ARGS else os.path.join(HERE, "..", "server")))
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


def call(function, *args, **kwargs):
    """Call a core function and return its payload as a dict."""
    return function(*args, **kwargs)


def as_dict(payload):
    """Some core functions return dataclasses; the tools serialise them."""
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    return payload if isinstance(payload, dict) else {"_value": payload}


def verdict_of(payload):
    payload = as_dict(payload)
    return payload.get("verdict") or payload.get("status") or ""


def expect(label, payload, verdict):
    payload = as_dict(payload)
    check(label, verdict_of(payload) == verdict,
          f"expected {verdict!r}, got {verdict_of(payload)!r}: "
          f"{json.dumps(payload, ensure_ascii=False, default=str)[:220]}")


def expect_number(label, payload, wanted):
    payload = as_dict(payload)
    got = str((payload.get("result") or {}).get("text", "")).replace(" ", "")
    check(label, got == wanted, f"expected {wanted!r}, got {got!r}")


# --------------------------------------------------------------------------- #
# A. divisibility and parity
# --------------------------------------------------------------------------- #

def test_divisibility_facts():
    verify = __import__("rigor.verify", fromlist=["verify_forall"]).verify_forall

    # Fermat's little theorem, small cases that a first course proves by cases.
    expect("6 | n^3 - n  (every integer, by n mod 6)", verify("forall n in Z: 6 | n^3 - n"),
           "proven")
    expect("30 | n^5 - n (n mod 30)", verify("forall n in Z: 30 | n^5 - n"), "proven")
    expect("3 | n^3 - n", verify("forall n in Z: 3 | n^3 - n"), "proven")

    # The classic "odd squares are 1 mod 8".
    expect("n odd -> 8 | n^2 - 1", verify("forall n in Z: n % 2 = 1 -> 8 | n^2 - 1"),
           "proven")
    expect("n^2 mod 4 is 0 or 1 (written with a single |)",
           verify("forall n in Z: n^2 % 4 = 0 | n^2 % 4 = 1"), "proven")

    # A false strengthening: the tool must say so, with a witness.
    expect("9 | n^3 - n is false (n = 2)", verify("forall n in Z: 9 | n^3 - n"), "refuted")

    # The lemma that carries the irrationality of sqrt(2).
    expect("p^2 = 2q^2 forces p even", verify(
        "forall p in Z: forall q in Z: q > 0 & p^2 = 2*q^2 -> 2 | p"), "proven")
    expect("p^2 = 2q^2 forces q even as well", verify(
        "forall p in Z: forall q in Z: q > 0 & p^2 = 2*q^2 -> 2 | q"), "proven")

    # Erdos–Suranyi-flavoured: 24 divides n(n^2-1)(3n+2) for every integer n.
    expect("24 | n(n^2-1)(3n+2)", verify("forall n in Z: 24 | n*(n^2-1)*(3*n+2)"),
           "proven")


def test_divisibility_claims_that_are_false():
    verify = __import__("rigor.verify", fromlist=["verify_forall"]).verify_forall
    expect("2 | n^2 is false (n = 1)", verify("forall n in Z: 2 | n^2"), "refuted")
    expect("4 | n^2 - n is false (n = 2)", verify("forall n in Z: 4 | n^2 - n"), "refuted")


# --------------------------------------------------------------------------- #
# B. inequalities with a stated domain
# --------------------------------------------------------------------------- #

def test_inequalities():
    verify = __import__("rigor.verify", fromlist=["verify_forall"]).verify_forall

    expect("AM-GM, two terms", verify(
        "forall a in R: forall b in R: a >= 0 & b >= 0 -> (a+b)^2 >= 4*a*b"), "proven")
    expect("Cauchy-Schwarz in R^2", verify(
        "forall a in R: forall b in R: forall c in R: forall d in R: "
        "(a*c+b*d)^2 <= (a^2+b^2)*(c^2+d^2)"), "proven")
    expect("Cauchy-Schwarz in R^3", verify(
        "forall a in R: forall b in R: forall c in R: "
        "(a+b+c)^2 <= 3*(a^2+b^2+c^2)"), "proven")
    expect("triangle inequality", verify(
        "forall x in R: forall y in R: abs(x+y) <= abs(x)+abs(y)"), "proven")
    expect("x^2 + 2x + 2 > 0 (completed square)", verify(
        "forall x in R: x^2 + 2*x + 2 > 0"), "proven")
    expect("x^2 >= x is false (x = 1/2)", verify("forall x in R: x^2 >= x"), "refuted")
    expect("ab = 0 -> a = 0 is false in R", verify(
        "forall a in R: forall b in R: a*b = 0 -> a = 0"), "refuted")

    inequality = __import__("rigor.verify", fromlist=["verify_inequality"]).verify_inequality
    expect("x + 1/x >= 2 for x > 0", inequality(
        "x + 1/x", ">=", "2", variables={"x": "real"}, constraints=["x > 0"]), "proven")
    expect("x + 1/x >= 3 for x > 0 is false", inequality(
        "x + 1/x", ">=", "3", variables={"x": "real"}, constraints=["x > 0"]), "refuted")

    # A claim the SMT backend cannot settle: `inconclusive` is the honest answer,
    # and it must not be dressed up as a proof.
    expect("2^n > n^2 for n >= 5 is beyond the solver", verify(
        "forall n in N: n >= 5 -> 2^n > n^2", timeout_ms=3000), "inconclusive")


# --------------------------------------------------------------------------- #
# C. closed forms for sums and products
# --------------------------------------------------------------------------- #

def test_closed_forms_are_applied_once():
    """`Sum(...)` already *is* the operator; applying it again is a different sum.

    Measured on 0.2.3 through the MCP tools: `Sum(k, (k, 1, 100))` answered
    505000 (100 * 5050), `Product(k, (k, 1, 5))` answered 120^5, and the Basel
    sum answered `oo`.  Every one of those is the operator applied twice.
    """
    symbolic = __import__("rigor.symbolic", fromlist=["symbolic_eval"]).symbolic_eval

    expect_number("sum of 1..100 is 5050",
                  symbolic("Sum(k, (k, 1, 100))", "sum"), "5050")
    expect_number("sum of squares up to 10 is 385",
                  symbolic("Sum(k^2, (k, 1, 10))", "sum"), "385")
    expect_number("Basel sum is pi^2/6",
                  symbolic("Sum(1/k^2, (k, 1, oo))", "sum"), "pi**2/6")
    expect_number("5! is 120", symbolic("Product(k, (k, 1, 5))", "product"), "120")
    expect_number("sum of 1..n is n(n+1)/2",
                  symbolic("Sum(k, (k, 1, n))", "sum"), "n**2/2+n/2")
    expect_number("sum of cubes", symbolic("Sum(k^3, (k, 1, n))", "sum"),
                  "n**4/4+n**3/2+n**2/4")


# --------------------------------------------------------------------------- #
# D. identities
# --------------------------------------------------------------------------- #

def test_identities():
    verify = __import__("rigor.symbolic", fromlist=["verify_identity"]).verify_identity

    expect("sum of the first n odd numbers is n^2", verify(
        "Sum(2*k-1, (k, 1, n))", "n^2", variables=["n"]), "proven")
    expect("sum k^2 closed form", verify(
        "Sum(k^2, (k, 1, n))", "n*(n+1)*(2*n+1)/6", variables=["n"]), "proven")
    expect("telescoping 1/(k(k+1))", verify(
        "Sum(1/(k*(k+1)), (k, 1, n))", "n/(n+1)", variables=["n"]), "proven")
    expect("Sophie Germain: n^4 + 4 factors", verify(
        "n^4 + 4", "(n^2-2*n+2)*(n^2+2*n+2)", variables=["n"]), "proven")
    expect("sin^2 + cos^2 = 1", verify(
        "sin(x)^2 + cos(x)^2", "1", variables=["x"]), "proven")
    expect("sin^2 + cos^2 = 2 is false", verify(
        "sin(x)^2 + cos(x)^2", "2", variables=["x"]), "refuted")
    expect("Basel, as an identity against pi^2/6", verify(
        "Sum(1/k^2, (k, 1, oo))", "pi^2/6"), "proven")

    # The binomial identities used to hang: sampling substituted a fraction into
    # the upper bound of the sum and sympy then tried a symbolic summation.
    started = time.perf_counter()
    expect("sum C(n,k) = 2^n", verify(
        "Sum(binomial(n,k), (k, 0, n))", "2^n", variables=["n"]), "proven")
    expect("Vandermonde convolution", verify(
        "Sum(binomial(m,k)*binomial(n,r-k), (k, 0, r))", "binomial(m+n,r)",
        variables=["m", "n", "r"]), "proven")
    check("the binomial identities answer in bounded time",
          time.perf_counter() - started < 30,
          f"took {time.perf_counter() - started:.1f}s")


def test_identity_respects_declared_domains():
    """A sample outside the declared domain is not a counterexample."""
    symbolic = __import__("rigor.symbolic", fromlist=["_is_admissible_sub"])
    assumptions = __import__("rigor.symbolic", fromlist=["split_assumptions"])
    import sympy as sp

    admissible = symbolic._is_admissible_sub(
        {"n": sp.Rational(3, 2)}, assumptions.split_assumptions(["n: integer"]))
    check("3/2 is not an admissible sample for an integer symbol", not admissible)
    check("4 is admissible for an integer symbol",
          symbolic._is_admissible_sub(
              {"n": sp.Integer(4)}, assumptions.split_assumptions(["n: integer"])))
    check("5 is not admissible for an even symbol",
          not symbolic._is_admissible_sub(
              {"n": sp.Integer(5)}, assumptions.split_assumptions(["n: even"])))


# --------------------------------------------------------------------------- #
# E. calculus
# --------------------------------------------------------------------------- #

def test_calculus():
    symbolic = __import__("rigor.symbolic", fromlist=["symbolic_eval"]).symbolic_eval
    limit = __import__("rigor.verify", fromlist=["verify_limit"]).verify_limit

    expect_number("d/dx x^x = x^x (log x + 1)",
                  symbolic("x^x", "diff", variable="x"), "x**x*(log(x)+1)")
    expect_number("d/dx arctan x = 1/(1+x^2)",
                  symbolic("arctan(x)", "diff", variable="x"), "1/(x**2+1)")
    expect_number("integral of x e^-x over [0, oo) is 1",
                  symbolic("x*exp(-x)", "integrate", variable="x", lower="0", upper="oo"), "1")
    expect_number("integral of 1/(1+x^2) over R is pi",
                  symbolic("1/(1+x^2)", "integrate", variable="x", lower="-oo", upper="oo"),
                  "pi")
    expect_number("series of exp(x) to order 4",
                  symbolic("exp(x)", "series", variable="x", point="0", order=4),
                  "x**4/24+x**3/6+x**2/2+x+1")

    cubic = symbolic("x^3 - 6*x^2 + 11*x - 6", "solve", variable="x")
    check("x^3-6x^2+11x-6 has roots 1, 2, 3",
          [s["text"] for s in cubic.get("solutions", [])] == ["1", "2", "3"],
          json.dumps(cubic, ensure_ascii=False)[:200])

    expect("(1+1/n)^n -> e", limit("(1+1/n)^n", "n", "oo", "e"), "proven")
    expect("sin x / x -> 1", limit("sin(x)/x", "x", "0", "1"), "proven")
    expect("(1-cos x)/x^2 -> 1/2", limit("(1-cos(x))/x^2", "x", "0", "1/2"), "proven")
    expect("sin x / x -> 2 is false", limit("sin(x)/x", "x", "0", "2"), "refuted")


# --------------------------------------------------------------------------- #
# F. exact integer facts
# --------------------------------------------------------------------------- #

def test_number_theory():
    theory = __import__("rigor.verify", fromlist=["number_theory"]).number_theory

    check("2^31 - 1 is prime (Mersenne)", theory("is_prime", numbers=["2147483647"])
          .get("is_prime") is True)
    factored = theory("factorize", numbers=["4294967297"])
    check("the fifth Fermat number is 641 * 6700417",
          factored.get("factorization") == {"641": 1, "6700417": 1},
          json.dumps(factored, ensure_ascii=False)[:200])
    check("phi(36) = 12", theory("totient", numbers=["36"]).get("totient") == "12")
    check("lambda(561) = 80", theory("carmichael", numbers=["561"])
          .get("carmichael_lambda") == "80")
    check("(2/7) = 1", theory("legendre", numbers=["2", "7"]).get("symbol") == 1)
    check("F(100) = 354224848179261915075",
          theory("fibonacci", numbers=["100"]).get("fibonacci") == "354224848179261915075")
    check("C(50,25) = 126410606437752",
          theory("binomial", numbers=["50", "25"]).get("binomial") == "126410606437752")
    check("20! = 2432902008176640000",
          theory("factorial", numbers=["20"]).get("factorial") == "2432902008176640000")
    check("561 is not prime", theory("is_prime", numbers=["561"]).get("is_prime") is False)


# --------------------------------------------------------------------------- #
# G. logic
# --------------------------------------------------------------------------- #

def test_logic():
    entails = __import__("rigor.smt", fromlist=["check_entailment"])
    step = __import__("rigor.logic", fromlist=["check_step"]).check_step

    expect("De Morgan: ~(P&Q) |= ~P | ~Q",
           entails.check_entailment(["~(P & Q)"], "~P | ~Q"), "proven")
    expect("quantifier negation: ~forall x P(x) |= exists x ~P(x)",
           entails.check_entailment(["~(forall x in R: x > 0)"],
                                    "exists x in R: ~(x > 0)"), "proven")
    expect("affirming the consequent is not valid",
           entails.check_entailment(["P -> Q", "Q"], "P"), "refuted")
    expect("hypothetical syllogism",
           entails.check_entailment(["P -> Q", "Q -> R"], "P -> R"), "proven")

    check("modus tollens is a valid rule instance",
          step(["P -> Q", "~Q"], "~P", "modus_tollens").verdict == "valid")
    check("modus tollens does not license ~P from ~P alone",
          step(["P -> Q", "~P"], "~Q", "modus_tollens").verdict != "valid")
    check("a lone | between propositions is disjunction",
          step(["P | Q", "~P"], "Q", "disjunctive_syllogism").verdict == "valid")


# --------------------------------------------------------------------------- #
# H. whole proofs through the session audit
# --------------------------------------------------------------------------- #

def _session(goal, variables=None):
    proof = __import__("rigor.proof", fromlist=["ProofSession"])
    return proof.ProofSession(session_id="t_" + str(abs(hash(goal)) % 10 ** 8),
                              problem="real mathematics", goal=goal,
                              variables=variables or {})


def _add(proof, session, entry_id, statement, rule="", from_ids=(), kind="step", **extra):
    entry = proof.Entry(id=entry_id, statement=statement, rule=rule,
                        from_ids=list(from_ids), kind=kind, **extra)
    proof.check_entry(session, entry)
    session.entries.append(entry)
    return entry


def test_sqrt2_lemma_chain_is_fully_machine_checked():
    """The descent at the heart of "sqrt(2) is irrational", step by step.

    This is a real proof, not a probe: p^2 = 2q^2 forces p even; substituting
    p = 2m gives 2m^2 = q^2, so q is even too.  Every step is an algebra or
    arithmetic claim, so the audit should report full machine coverage.
    """
    proof = __import__("rigor.proof", fromlist=["audit"])
    session = _session("2 | p0 & 2 | q0", {"p0": "int", "q0": "int"})
    _add(proof, session, "g1", "p0^2 = 2*q0^2", kind="given")
    _add(proof, session, "s1", "2 | p0^2", "algebra", ["g1"])
    _add(proof, session, "s2", "2 | p0", "arithmetic", ["s1"])
    _add(proof, session, "s3", "4 | p0^2", "algebra", ["s2"])
    _add(proof, session, "s4", "4 | 2*q0^2", "equality_substitution", ["s3", "g1"])
    _add(proof, session, "s5", "2 | q0^2", "algebra", ["s4"])
    _add(proof, session, "s6", "2 | q0", "arithmetic", ["s5"])
    _add(proof, session, "s7", "2 | p0 & 2 | q0", "conjunction_intro", ["s2", "s6"])
    result = proof.audit(session)

    expect("the lemma chain audits as verified", result, "verified")
    check("the goal is derived", result["goal_reached"] is True,
          json.dumps(result["flaws"], ensure_ascii=False)[:200])
    check("every step was machine-checked", result["machine_coverage"]["checked_fraction"] == 1.0,
          json.dumps(result["machine_coverage"], ensure_ascii=False))


def test_a_planted_error_in_the_chain_is_caught():
    proof = __import__("rigor.proof", fromlist=["audit"])
    session = _session("2 | p0 & 2 | q0", {"p0": "int", "q0": "int"})
    _add(proof, session, "g1", "p0^2 = 2*q0^2", kind="given")
    _add(proof, session, "s1", "2 | p0^2", "algebra", ["g1"])
    _add(proof, session, "s2", "2 | p0", "arithmetic", ["s1"])
    # The classic slip: 4 | p0^2 does not give 4 | q0^2.
    _add(proof, session, "s3", "4 | q0^2", "algebra", ["s2"])
    _add(proof, session, "s4", "2 | p0 & 2 | q0", "conjunction_intro", ["s2", "s3"])
    result = proof.audit(session)

    expect("the planted false step makes the proof flawed", result, "flawed")
    check("the false step is the one refuted", "s3" in result["refuted_ids"],
          json.dumps(result["refuted_ids"], ensure_ascii=False))


def test_undischarged_assumption_is_a_flaw():
    proof = __import__("rigor.proof", fromlist=["audit"])
    session = _session("2 | q0", {"p0": "int", "q0": "int"})
    _add(proof, session, "a1", "2 | p0", kind="assumption")
    _add(proof, session, "s1", "2 | q0", "theorem_citation", ["a1"])
    result = proof.audit(session)
    expect("an assumption nobody closes makes the proof flawed", result, "flawed")
    check("the open assumption is named", "a1" in result["undischarged_assumption_ids"],
          json.dumps(result["undischarged_assumption_ids"]))


def test_a_true_step_the_solver_cannot_decide_is_a_disclosed_gap():
    """Euclid's theorem is true; z3 cannot prove it, and the audit must say so."""
    proof = __import__("rigor.proof", fromlist=["audit"])
    session = _session("forall n in N: exists p in N: p > n & prime(p)")
    _add(proof, session, "s1", "forall n in N: exists p in N: p > n & prime(p)",
         "theorem_citation")
    result = proof.audit(session)
    expect("an undecidable true theorem leaves a disclosed gap", result, "sound_with_gaps")


def test_a_false_claim_cannot_be_dressed_up_as_a_premise():
    """`2 + 2 = 5` used to audit as sound_with_gaps when labelled `premise`.

    The 0.2.3 fix refuted premiseless `arithmetic`/`algebra`/`computation` steps
    but left the other premiseless rules alone, so relabelling the same claim
    was enough to have it filed as "unchecked" -- and a session whose only step
    is that claim audited as "structurally sound, nothing refuted".
    """
    proof = __import__("rigor.proof", fromlist=["audit"])
    for rule in ("premise", "definition", "machine_verified", "theorem_citation"):
        session = _session("2 + 2 = 5")
        _add(proof, session, "s1", "2 + 2 = 5", rule)
        result = proof.audit(session)
        expect(f"`2 + 2 = 5` by {rule} is refuted, not excused", result, "flawed")


def test_a_true_premise_is_still_accepted():
    proof = __import__("rigor.proof", fromlist=["audit"])
    session = _session("2 + 2 = 4")
    _add(proof, session, "s1", "2 + 2 = 4", "premise")
    expect("a true concrete claim is machine-verified", proof.audit(session), "verified")


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #

def main():
    only = {a.lstrip("-") for a in sys.argv[1:] if a.startswith("--")}
    groups = [
        ("divisibility", test_divisibility_facts),
        ("refutable", test_divisibility_claims_that_are_false),
        ("inequalities", test_inequalities),
        ("closed-forms", test_closed_forms_are_applied_once),
        ("identities", test_identities),
        ("domains", test_identity_respects_declared_domains),
        ("calculus", test_calculus),
        ("number-theory", test_number_theory),
        ("logic", test_logic),
        ("proof-chain", test_sqrt2_lemma_chain_is_fully_machine_checked),
        ("proof-planted-error", test_a_planted_error_in_the_chain_is_caught),
        ("proof-assumption", test_undischarged_assumption_is_a_flaw),
        ("proof-gap", test_a_true_step_the_solver_cannot_decide_is_a_disclosed_gap),
        ("proof-laundering", test_a_false_claim_cannot_be_dressed_up_as_a_premise),
        ("proof-true-premise", test_a_true_premise_is_still_accepted),
    ]
    started = time.perf_counter()
    for name, test in groups:
        if only and name not in only:
            continue
        print(f"\n=== {name} ===")
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a broken tool must be reported
            check(f"{name} ran to completion", False, f"{type(exc).__name__}: {str(exc)[:300]}")
    print(f"\n   passed {PASSED}, failed {FAILED} in {time.perf_counter() - started:.1f}s")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
