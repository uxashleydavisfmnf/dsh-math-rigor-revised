# Changelog

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
