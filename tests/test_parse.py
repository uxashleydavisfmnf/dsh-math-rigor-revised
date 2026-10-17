import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from rigor.ast_nodes import parse  # noqa: E402

CASES = [
    "x**2 + 2*x - 1",
    "x^2 + 2x - 1",
    "-x^2",
    "2^3^2",
    r"\frac{x^2+1}{x-1}",
    r"\sqrt{x+1}",
    r"\sqrt[3]{x}",
    "|x| + 1",
    "a < b < c",
    "P & Q -> R",
    "P -> Q -> R",
    "~(P || Q) <-> (~P & ~Q)",
    "forall n: n > 0 -> n + 1 > 0",
    r"\forall x \in \mathbb{R}: x^2 \geq 0",
    r"\exists n \in \mathbb{Z}: n^2 = 4",
    "forall x, y: P(x) & P(y) -> Q(x,y)",
    "Sum(k, (k, 1, n)) = n*(n+1)/2",
    r"\sum_{k=1}^{n} k = \frac{n(n+1)}{2}",
    r"\prod_{i=1}^{n} i",
    "Abs(x) + sqrt(y)",
    "n^3 - n",
    "3 | n",
    "x % 2 = 0",
    "exp(x) > 1",
    "a and b or not c",
    "f(g(x))",
    r"\mathbb{Z}",
    "forall n in Z: 6 | n^3 - n",
    "sin(x)^2 + cos(x)^2 = 1",
    "n(n+1)",
    "a(x-1)",
    "(x+1)(x-1)",
    "2(x+1)",
    "P(x) & Q(x,y)",
]

# names pre-declared as functions must beat the juxtaposition heuristic
DECLARED = [
    ("f(x+1)", ["f"]),
    ("g(2*x)", ["g"]),
]

fail = 0
for src, fns in [(c, ()) for c in CASES] + DECLARED:
    try:
        node = parse(src, functions=fns)
        print(f"OK   {src!r}\n  -> text : {node.text()}\n  -> latex: {node.latex()}")
    except Exception as exc:  # noqa: BLE001
        fail += 1
        print(f"FAIL {src!r}\n  -> {type(exc).__name__}: {exc}")

total = len(CASES) + len(DECLARED)
print(f"\n{total - fail}/{total} parsed")

# Regression: the parser recurses per nesting level and per right-hand operand,
# so CPython's default limit of 1000 used to reject a ~300-term polynomial and
# a ~100-deep nesting with a bare RecursionError.  rigor/__init__.py raises the
# limit; these sizes must parse.
print("\n=== deep and wide expressions ===")
BIG = [
    ("a 1,000-term sum", " + ".join(["x"] * 1000)),
    ("a 3,000-term sum", " + ".join(["x"] * 3000)),
    ("a 1,000-level nesting", "(" * 1000 + "x" + ")" * 1000),
    ("a 2,000-term sum inside a quantifier",
     "forall n in Z: " + " + ".join(["n"] * 2000) + " = 0"),
]
for label, src in BIG:
    try:
        node = parse(src, functions=())
        rendered = node.text()
        ok = len(rendered) > 0
        print(f"{'OK  ' if ok else 'FAIL'} {label}  -> {len(rendered)} chars of AST text")
        if not ok:
            fail += 1
    except Exception as exc:  # noqa: BLE001
        fail += 1
        print(f"FAIL {label}\n  -> {type(exc).__name__}: {exc}")

TOTAL = total + len(BIG)
print(f"\n{TOTAL - fail}/{TOTAL} parsed")
sys.exit(1 if fail else 0)
