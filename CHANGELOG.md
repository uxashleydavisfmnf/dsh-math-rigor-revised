# Changelog

## 0.2.4 — measured against real mathematics

The 0.2.3 work probed every tool with synthetic claims: it established that the
tools answer, agree with themselves, and do not crash. This release came out of
running an ordinary mathematical workload through them — divisibility lemmas,
classical inequalities, closed forms, textbook integrals, and four complete
proofs audited step by step. That is a different kind of test, and it found a
different kind of defect: five of the seven below return a *wrong mathematical
answer*, not a wrong shape, and three of those had been reported as correct.

### Fixed

- **`x = 1 | x = 2` parsed as three conjoined claims.** A single `|` between two
  statements is disjunction, but the tokenizer only recognised it when both sides
  began with a capital letter, so a bar between two *relations* became the
  divisibility operator and `parse_cmp` then read the whole input as a chained
  relation: `a = b | a = c` parsed to `And(a = b, b | a, a = c)`. Measured on
  0.2.3, `forall n in Z: n^2 % 4 = 0 | n^2 % 4 = 1` — a true statement — came
  back `refuted` with the "counterexample" `n = 0`. A bar is now a disjunction
  whenever either side is a formula (it contains a relation or a connective at
  bracket depth zero, or it is a call to a predicate such as `even(n)`), a bar
  between two arithmetic terms is still divisibility, and a `|` that would be
  chained with other relations is rejected instead of being read as a
  conjunction.
- **`symbolic_eval` applied `sum` and `product` twice.** `Sum(k, (k, 1, 100))`
  already *is* a summation, and the expression is translated unevaluated, so
  `sp.summation` summed the whole sum again over the same index. Every such
  result was wrong: `Sum(k, (k, 1, 100))` answered **505000** instead of 5050,
  `Sum(k^2, (k, 1, 10))` answered **3850** instead of 385, `Product(k, (k, 1, 5))`
  answered **24883200000** (120^5) instead of 120, and the Basel sum answered
  **`oo`** instead of `pi^2/6`. The operator is now applied exactly once.
- **`verify_identity` never returned on a binomial sum.** Sampling substituted a
  rational into the upper bound of `Sum(binomial(n, k), (k, 0, n))`, leaving a
  summation with a fractional limit, and `sp.N` then attempted a symbolic
  summation that never finished: `Sum(binomial(n,k),(k,0,n)) = 2^n` was still
  running after 25s and had to be killed. Sampling now adds such a sum up
  explicitly over its concrete integer bounds (and skips the sample when the
  bounds are not integers), so the identity is decided. Sums are also closed
  before the difference is simplified, which is what makes the binomial
  identities provable at all instead of merely "inconclusive".
- **Declared domains were not enforced during sampling, so a true identity could
  be "refuted".** `symbolic.py` defined `_is_admissible_sub` twice; the second
  definition shadowed the first and its integer-domain check was dead code
  (`if ... if False else False`), so `assumptions=["n: integer"]` admitted
  `n = 3/2`. There is one definition now, and it enforces `integer`, `natural`,
  `even` and `odd`. Sampling also no longer feeds a `Sum` an upper bound below
  its lower bound, where the sum is empty and an identity that holds for
  `n >= 0` would look false.
- **`2^n` froze the solver, ignoring its own timeout.** An integer base raised to
  a symbolic exponent was lifted to the reals, so z3 saw `2 ** ToReal(n)` and
  entered the transcendental power theory: measured directly, the query
  `forall n in N: n >= 5 -> 2^n > n^2` with `solver.set("timeout", 2000)` was
  still running at 40s. An ordinary exercise hung the whole server. Integers
  raised to an integer exponent now stay in the integers (`2^n > 0` is proved,
  and the `n >= 5` claim answers "unknown" in 8s); a *constant* base with a
  symbolic real exponent is refused with a message that points at
  `verify_induction`.
- **A refutation could rest on reinterpreting an uninterpreted predicate.**
  `prime` has no theory in z3, so the solver falsified Euclid's theorem
  (`forall n in N: exists p in N: p > n & prime(p)`) by taking the extension of
  `prime` to be empty, and the audit then reported the theorem as **REFUTED**
  with the witness `n = 0`. Unsat is interpretation-independent and remains a
  proof; sat over an applied uninterpreted symbol describes the solver's freedom,
  not the mathematics, so it is reported as undecided. Pure arithmetic claims
  (`forall x in R: x^2 >= x`) are still refuted as before.
- **A false step could be laundered by relabelling it.** The 0.2.3 fix refuted
  premiseless `arithmetic`/`algebra`/`computation` steps, but `premise`,
  `definition`, `machine_verified` and `theorem_citation` still granted their
  statement outright, so `2 + 2 = 5` labelled `premise` audited as
  `sound_with_gaps` — "structurally sound, nothing refuted" — for a session whose
  only step was arithmetic nonsense. Every premiseless step now gets one short
  machine check; a refutation is recorded, and silence still leaves it
  unchecked.
- **`diff arctan(x)` answered `Derivative(arctan(x), x)`.** The `arc…` spellings
  were missing from the function table, so the name became an undefined sympy
  function and the unevaluated derivative was returned as if it were the result.
  `arcsin`, `arccos`, `arctan`, `arctg`, `arcsinh`, `arccosh`, `arctanh`, `lg`
  and `tg` are now recognised.

### Changed

- **Divisibility claims are proved about ten times faster.** A 20s direct query
  ran before the residue split, and — because z3 only escalates to the expensive
  nonlinear tactics once the cheap ones have failed — a *larger* budget made the
  same question slower, not better: `forall n in Z: 6 | n^3 - n` took 40s with a
  20s query budget and 2s with a 1s one. The order is now a short probe (1.5s),
  then the residue split with a capped share per case, then the long query, which
  is also capped when the split has already covered every integer variable.
  Measured: `6 | n^3 - n` 30s → 3.1s, `30 | n^5 - n` 30s → 3.1s, the false
  `sqrt(2)` statement 44s → 17.5s (still honestly `inconclusive`).

### Tests

- `tests/test_real_projects.py` (new, 79 checks) is the workload this release was
  found with: divisibility and parity lemmas, AM-GM and Cauchy-Schwarz, closed
  forms for sums and products, the binomial identities, textbook derivatives,
  integrals, limits and series, exact integer facts, logic, and four complete
  proofs driven through the session audit (a fully machine-checked lemma chain,
  a planted error, an undischarged assumption, a disclosed gap, and the
  laundering case). It runs in about 20s.

## 0.2.3 — concurrent tool calls no longer kill the server

### Fixed

- **A decimal literal silently became an integer, which produced false proofs.**
  Numeric literals were handed to z3py as Python `float`s, and z3py *casts* a
  float to the domain of whatever it is applied to — casting `1.5` to `Int`
  yields `1`. So `forall x in Z: P(x)` came back as entailing `P(1.5)` (the goal
  was encoded as `P(1)`), `forall n in Z: even(n)` as entailing `even(1.5)`, and
  `forall n in Z: 2 | n` as entailing `2 | 1.5`: four false `proven` verdicts in
  a five-case sweep. Decimal literals are now translated to the exact rational
  they denote (`1.5` → `3/2`, `0.125` → `1/8`) instead of a float, and a
  statement that cannot be encoded — an integer predicate applied to `1.5` — is
  reported as `error`/`inconclusive` with the reason, never as `proven`.
- **Pipelined requests corrupted or aborted the server process.** z3's Python
  bindings share one global context, and an MCP transport may dispatch several
  requests at once, so two tool calls could enter the solver together. Measured
  against 0.2.2, a client that wrote its requests without waiting for replies saw
  the process abort with `0xC0000374` (heap corruption, from z3's own
  `Z3 fatal error ... concurrent`) in 2 of 3 trials, and in the third every z3
  call after the first returned `Z3Exception: Context mismatch` or
  `Value cannot be converted into a Z3 Boolean value` — a wrong answer, not an
  error, for statements the server had already answered correctly in isolation.
  Request-by-request traffic was clean, which is why this was invisible before.
  `rigor/engine.py` now exposes one process-wide `RLock`; the SMT entry points
  and the server's tool guard both take it. Proof sessions, the symbolic tools
  and every non-z3 tool are unaffected.
- **`P(a) |- forall x: P(x)` crashed inside z3py.** A free variable used only as a
  predicate argument took the numeric default sort while its bound counterpart
  stayed uninterpreted, and z3py's coercion path answers that combination with
  `AttributeError: 'SortRef' object has no attribute 'is_int'` instead of a
  `Z3Exception`. Sort inference now unifies a predicate's argument sort across
  every occurrence of that argument position, so the two occurrences agree; a
  statement with no free variable to fix the domain still keeps its
  uninterpreted sort rather than inventing a numeric one.
- **A false step that cited no premises was never refuted.** `arithmetic`,
  `algebra` and `computation` assert their statement outright, but the audit only
  re-derived a step when it had premises, so `2 + 2 = 5` justified by
  `arithmetic` was filed as "unchecked" instead of being refuted. Premiseless
  steps of those rules are now re-derived too, under a short budget so a hard
  symbolic rewrite cannot stall the audit.
- **`symbolic_numeric` on a large finite sum did not terminate.** Closing
  `Sum(1/k^2, (k, 1, 1000000))` exactly means adding a million terms over a
  common denominator: measured, `(k, 1, 20000)` cost 48s and 166MB and then died
  on CPython's 4300-digit integer-to-string limit, and the million-term case took
  a server process past 1.2GB without ever answering. Exact closure is now
  attempted only when it is bounded work (about 2500 terms); beyond that the
  value is computed numerically in under a second and `exactness` is reported as
  `not_computed` rather than guessed.
- **`symbolic_eval` demanded `lower`/`upper` for a sum that stated them.** The
  bounds are now read out of `Sum(k, (k, 1, n))` when they are not passed as
  arguments, and the error message names the alternative when they are absent.

### Changed

- A failure that comes out of the native solver (an `OSError`, an access
  violation, a context mismatch) is no longer answered with the notation hint.
  That hint sent callers to check their `|` usage for problems that were not
  about notation.

### Tests

- `tests/test_regressions.py` (new, 38 checks) pins each fix above, including the
  decimal-literal sweep and the `1.5` entailment that used to answer `proven`.
  The concurrency case runs in a subprocess because the pre-0.2.3 failure mode
  was a native abort, and it is bounded so that a build without the lock reports
  failures instead of hanging the runner.

## 0.2.2 — large expressions no longer hit the recursion limit

### Fixed

- **Expressions with a few hundred terms were rejected.** The parser recurses once
  per nesting level and once per right-hand operand, and the AST helpers recurse
  over the tree, so CPython's default recursion limit of 1000 put the practical
  ceiling at roughly 300 terms or 100 levels of nesting: a 500-term sum, a
  300-level nesting and a 2,000-term quantified claim all came back as a bare
  `RecursionError` ("maximum recursion depth exceeded"). `rigor/__init__.py` now
  raises the limit to 20,000 on import — pure-Python frames in CPython 3.11+ live
  on the heap, so this costs memory rather than stack safety. Measured after the
  change: a 6,000-term sum and 1,000 levels of nesting parse, and the 3,000-term
  simplify that used to fail completes in under a second.
- **The remaining failure mode is now actionable.** Anything beyond that still
  cannot be parsed, but the server turns `RecursionError` into an
  `ExpressionTooLarge` result that names the practical limit and suggests a
  factored or closed form, instead of leaking the interpreter's message.

### Tests

- `tests/test_parse.py` parses a 1,000-term and a 3,000-term sum, a 1,000-level
  nesting, and a 2,000-term quantified claim.
- `tests/test_mcp_stdio.py` simplifies a 2,000-term expression over the real
  stdio transport, handles a 300-level nesting, and asserts that an absurd
  60,000-term expression produces the sized `ExpressionTooLarge` error rather
  than a recursion message.

## 0.2.1 — corrected build

This repository is the corrected build of the `math-rigor` plugin
(`bauerelizabeth07139/math-rigor`), renamed to match its package name.
Nothing about the tool surface changed: the same 23 MCP tools, the same
`math-rigor` skill, the same two commands.

### Fixed

- **`find_counterexample` ignored a domain declared in the quantifier.**
  Freeing the leading `forall` binders also dropped the sorts they carried, so
  the negation was handed to the SMT solver with the variables sorted by
  inference alone. A claim about the integers was therefore decided over the
  reals, and `forall n in Z: n^2 >= n` — true for every integer — came back
  `refuted` with the witness `n = 1/2`. The domains now travel with the freed
  variables into the SMT search, the explicit-range scan and the sampler, so
  `find_counterexample` agrees with `verify_forall` on the same statement.
- **`number_theory` rejected JSON numbers.** `numbers`, `residues` and `moduli`
  were declared as arrays of strings, so the natural call
  `number_theory("gcd", numbers=[48, 18])` failed with a raw pydantic
  validation error instead of computing `6`. Integers are now accepted
  alongside strings.

### Tests

- `tests/test_verify.py` covers the binder-only domains (integer, natural,
  real), asserts the reported sort is `int`, and asserts a genuine integer
  failure still yields an integral witness.
- `tests/test_mcp_stdio.py` covers both defects through the real MCP stdio
  transport, and the previously wrong expectation
  (`find_counterexample("forall n in Z: n^2 >= n") == "refuted"`) is corrected
  to `proven`.

## 0.2.0 and earlier

See the git history of `bauerelizabeth07139/math-rigor`.
