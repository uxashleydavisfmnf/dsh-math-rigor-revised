"""Symbolic manipulation and identity verification built on sympy.

The guiding rule is that a symbolic result is *evidence*, not a proof, unless the
difference actually collapses to zero under stated assumptions.  When sympy
cannot collapse it, the verdict is ``inconclusive`` and the residual difference
is reported -- the workflow then has to supply assumptions or a different route.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import mpmath
import sympy as sp

from .ast_nodes import App, BigOp, Node, Num, Sym, collect_symbols, parse
from .translate import (
    SympyContext,
    TranslateError,
    ast_to_sympy,
    make_symbol,
    sympy_to_ast,
)

VERDICT_PROVEN = "proven"
VERDICT_REFUTED = "refuted"
VERDICT_INCONCLUSIVE = "inconclusive"
VERDICT_ERROR = "error"

_DEFAULT_PRECISION = 30
_COMPARISON_OPS = ("<=", ">=", "!=", "==", "<", ">", "=", "∈", "in ")

# Above this many terms, closing a Sum/Product exactly is not bounded work; see
# `_exact_closure_is_cheap` for the measurements behind the number.
_MAX_EXACT_TERMS = 2500


# --------------------------------------------------------------------------- #
# Assumptions
# --------------------------------------------------------------------------- #


@dataclass
class AssumptionSet:
    """Symbol properties (`x positive`) separated from logical constraints (`x > 0`)."""

    properties: dict[str, list[str]] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)

    def symbols(self) -> SympyContext:
        ctx = SympyContext()
        for name, flags in self.properties.items():
            ctx.symbols[name] = make_symbol(name, flags)
        return ctx


def split_assumptions(items: Iterable[str]) -> AssumptionSet:
    """Accept both ``"x: positive"`` and ``"x >= 0"`` in one list."""
    result = AssumptionSet()
    for raw in items:
        text = str(raw).strip()
        if not text:
            continue
        if any(op in text for op in _COMPARISON_OPS):
            result.constraints.append(text)
            continue
        cleaned = text.replace(":", " ").replace(",", " ")
        parts = cleaned.split()
        if len(parts) >= 2:
            name, *flags = parts
            result.properties.setdefault(name, []).extend(flags)
        else:
            raise ValueError(
                f"cannot read the assumption {raw!r}; use `x: positive` for a symbol "
                "property or `x > 0` for a constraint"
            )
    return result


def _symbol_context(variables: Sequence[str], assumptions: AssumptionSet) -> SympyContext:
    ctx = SympyContext()
    for name in variables:
        flags = assumptions.properties.get(name, [])
        ctx.symbols[name] = make_symbol(name, flags)
    for name, flags in assumptions.properties.items():
        if name not in ctx.symbols:
            ctx.symbols[name] = make_symbol(name, flags)
    return ctx


# --------------------------------------------------------------------------- #
# Core conversions
# --------------------------------------------------------------------------- #


def to_sympy(expression: str, assumptions: AssumptionSet | None = None,
             variables: Sequence[str] = ()) -> Any:
    assumptions = assumptions or AssumptionSet()
    ctx = _symbol_context(list(variables), assumptions)
    node = parse(expression, functions=[])
    return ast_to_sympy(node, ctx)


def render(expr: Any) -> dict[str, str]:
    return {"text": sp.sstr(expr), "latex": sp.latex(expr)}


# --------------------------------------------------------------------------- #
# symbolic_eval
# --------------------------------------------------------------------------- #

_SIMPLIFIERS = (
    ("simplify", lambda e: sp.simplify(e)),
    ("trigsimp", lambda e: sp.trigsimp(e)),
    ("cancel", lambda e: sp.cancel(e)),
    ("factor", lambda e: sp.factor(e)),
    ("expand", lambda e: sp.expand(e)),
    ("radsimp", lambda e: sp.radsimp(e)),
    ("powsimp", lambda e: sp.powsimp(e, force=True)),
    ("logcombine", lambda e: sp.logcombine(e, force=True)),
    ("combsimp", lambda e: sp.combsimp(e)),
    ("ratsimp", lambda e: sp.ratsimp(e)),
)


def try_collapse(expr: Any) -> tuple[bool, Any, str]:
    """Try a battery of normalisations; report the first that reaches zero."""
    best = expr
    for name, function in _SIMPLIFIERS:
        try:
            candidate = function(expr)
        except Exception:  # noqa: BLE001 - sympy raises many unrelated types
            continue
        if candidate == 0:
            return True, sp.Integer(0), name
        if sp.count_ops(candidate) < sp.count_ops(best):
            best = candidate
    return False, best, ""


_OPERATIONS = {
    "simplify", "expand", "factor", "collect", "cancel", "apart", "together",
    "trigsimp", "ratsimp", "diff", "integrate", "limit", "series", "solve",
    "roots", "sum", "product", "coeffs", "subs", "numeric", "latex", "domain",
}


def symbolic_eval(
    expression: str,
    operation: str = "simplify",
    variable: str = "",
    *,
    point: str = "",
    direction: str = "+",
    order: int = 1,
    lower: str = "",
    upper: str = "",
    substitutions: Mapping[str, str] | None = None,
    precision: int = _DEFAULT_PRECISION,
    assumptions: Sequence[str] = (),
) -> dict[str, Any]:
    """Perform one symbolic operation and report the result with its LaTeX form."""
    op = operation.strip().lower()
    if op not in _OPERATIONS:
        raise ValueError(f"unknown operation {operation!r}; supported: {', '.join(sorted(_OPERATIONS))}")
    assumption_set = split_assumptions(assumptions)
    variables = [v.strip() for v in re.split(r"[,\s]+", variable) if v.strip()]
    ctx = _symbol_context(variables, assumption_set)
    node = parse(expression, functions=[])
    expr = ast_to_sympy(node, ctx)
    var = ctx.symbol(variables[0]) if variables else None
    notes: list[str] = []

    # `Sum(k, (k, 1, n))` already carries its own bounds, so a caller who wrote
    # the summation out in full should not have to repeat them as arguments.
    if isinstance(node, BigOp) and node.kind in ("sum", "prod") \
            and not variables and not lower and not upper:
        bound_var = ctx.symbol(node.var)
        variables = [node.var]
        var = bound_var
        lower = node.lo.text()
        upper = node.hi.text()
        notes.append(
            f"took the bounds from the expression: {node.var} from "
            f"{node.lo.text()} to {node.hi.text()}"
        )

    result: Any
    if op == "simplify":
        result = sp.simplify(expr)
    elif op == "expand":
        result = sp.expand(expr)
    elif op == "factor":
        result = sp.factor(expr)
    elif op == "collect":
        result = sp.collect(expr, var) if var is not None else sp.collect(expr, expr.free_symbols)
    elif op == "cancel":
        result = sp.cancel(expr)
    elif op == "apart":
        result = sp.apart(expr, var) if var is not None else sp.apart(expr)
    elif op == "together":
        result = sp.together(expr)
    elif op == "trigsimp":
        result = sp.trigsimp(expr)
    elif op == "ratsimp":
        result = sp.ratsimp(expr)
    elif op == "diff":
        if var is None:
            raise ValueError("`diff` needs the `variable` argument")
        result = sp.diff(expr, var, order)
    elif op == "integrate":
        if var is None:
            raise ValueError("`integrate` needs the `variable` argument")
        if lower and upper:
            result = sp.integrate(
                expr, (var, to_sympy(lower, assumption_set), to_sympy(upper, assumption_set))
            )
        else:
            result = sp.integrate(expr, var)
    elif op == "limit":
        if var is None:
            raise ValueError("`limit` needs the `variable` argument")
        if not point:
            raise ValueError("`limit` needs the `point` argument (use `oo` for infinity)")
        result = sp.limit(expr, var, to_sympy(point, assumption_set), dir=direction)
    elif op == "series":
        if var is None:
            raise ValueError("`series` needs the `variable` argument")
        at = to_sympy(point, assumption_set) if point else sp.Integer(0)
        result = sp.series(expr, var, at, order + 1).removeO()
    elif op == "solve":
        if var is None:
            raise ValueError("`solve` needs the `variable` argument")
        target = expr if isinstance(expr, sp.Equality) else sp.Eq(expr, 0)
        solutions = sp.solve(target, var, dict=False)
        if not isinstance(solutions, list):
            solutions = [solutions]
        result_list = [render(_maybe_clean(s)) for s in solutions]
        return {
            "operation": op, "input": render(expr), "solutions": result_list,
            "solution_count": len(result_list),
            "notes": [f"solved for {var}"],
        }
    elif op == "roots":
        if var is None:
            raise ValueError("`roots` needs the `variable` argument")
        found = sp.roots(expr, var)
        return {
            "operation": op, "input": render(expr),
            "roots": [{"root": render(r), "multiplicity": int(m)} for r, m in found.items()],
            "note": "only the roots sympy can express exactly are listed",
        }
    elif op == "sum":
        if var is None or not lower or not upper:
            raise ValueError(
                "`sum` needs `variable`, `lower` and `upper`, or an expression that "
                "already states them, such as Sum(k, (k, 1, n))"
            )
        result = _apply_bigop(expr, "sum", var, lower, upper, assumption_set, notes)
    elif op == "product":
        if var is None or not lower or not upper:
            raise ValueError(
                "`product` needs `variable`, `lower` and `upper`, or an expression that "
                "already states them, such as Product(k, (k, 1, n))"
            )
        result = _apply_bigop(expr, "prod", var, lower, upper, assumption_set, notes)
    elif op == "coeffs":
        if var is None:
            raise ValueError("`coeffs` needs the `variable` argument")
        poly = sp.Poly(expr, var)
        return {
            "operation": op, "input": render(expr), "degree": int(poly.degree()),
            "coefficients": [render(c) for c in poly.all_coeffs()],
            "note": "coefficients are listed from the highest degree downwards",
        }
    elif op == "subs":
        if not substitutions:
            raise ValueError("`subs` needs the `substitutions` argument, e.g. {\"x\": \"2\"}")
        mapping = {ctx.symbol(k): to_sympy(v, assumption_set) for k, v in substitutions.items()}
        result = expr.subs(mapping)
    elif op == "numeric":
        result = sp.N(expr, precision)
    elif op == "latex":
        return {"operation": op, "input": render(expr), "latex": sp.latex(expr)}
    elif op == "domain":
        free = sorted(str(s) for s in expr.free_symbols)
        return {
            "operation": op, "input": render(expr),
            "free_symbols": free,
            "notes": [
                "domain questions are answered by verify_forall or verify_inequality, "
                "which take the domain explicitly",
            ],
        }
    else:  # pragma: no cover - guarded by the membership check above
        raise ValueError(f"unhandled operation {op!r}")

    payload: dict[str, Any] = {
        "operation": op,
        "input": render(expr),
        "result": render(result),
    }
    if notes:
        payload["notes"] = notes
    return payload


def _apply_bigop(expr: Any, kind: str, var: Any, lower: str, upper: str,
                 assumptions: AssumptionSet, notes: list[str]) -> Any:
    """Apply a sum/product exactly once.

    ``Sum(k, (k, 1, 100))`` already *is* a summation, and ``ast_to_sympy`` keeps
    it unevaluated.  Calling ``sp.summation`` on it sums the whole sum again
    over the same index, which is a different -- and silently wrong -- quantity:
    ``Sum(k, (k, 1, 100))`` came back as 505000 instead of 5050, and
    ``Sum(1/k^2, (k, 1, oo))`` as ``oo`` instead of ``pi^2/6``.  When the input
    is already the operator, close it with ``doit`` and leave its own bounds
    alone.
    """
    already = sp.Sum if kind == "sum" else sp.Product
    if isinstance(expr, already):
        notes.append("the expression already states its own bounds; they were used as written")
        try:
            closed = expr.doit()
        except Exception:  # noqa: BLE001 - sympy refuses some formal sums
            notes.append("this sum could not be closed in closed form")
            return expr
        if isinstance(closed, already):
            notes.append("no closed form was found; the sum is reported unevaluated")
        return closed
    lo = to_sympy(lower, assumptions)
    hi = to_sympy(upper, assumptions)
    if kind == "sum":
        return sp.summation(expr, (var, lo, hi))
    return sp.product(expr, (var, lo, hi))


def _maybe_clean(value: Any) -> Any:
    try:
        return sp.simplify(value)
    except Exception:  # noqa: BLE001
        return value


# --------------------------------------------------------------------------- #
# Numeric evaluation
# --------------------------------------------------------------------------- #


def _concrete(value: Any) -> int | None:
    """The integer value of a sympy expression, when it has one."""
    try:
        if value.is_Integer:
            return int(value)
    except Exception:  # noqa: BLE001
        return None
    return None


def _exact_closure_is_cheap(expr: Any) -> tuple[bool, int]:
    """Whether closing every Sum/Product exactly is bounded work.

    ``Sum(1/k**2, (k, 1, 1000000))`` has a *closed* numeric value, but asking
    sympy for the exact rational means adding a million terms over a common
    denominator: measured on this code base, ``(k, 1, 20000)`` already costs 48s
    and 166MB and then dies on the 4300-digit integer-to-string limit, and a
    million terms took the server process past 1.2GB without ever answering.  The
    bound below keeps that from being reachable from a tool call; a numerical
    evaluation gives the caller the value they asked for in milliseconds.
    """
    worst = 0
    for node in sp.preorder_traversal(expr):
        if isinstance(node, (sp.Sum, sp.Product)):
            for limit in node.limits:
                if len(limit) != 3:
                    continue  # an indefinite sum has no term count to estimate
                lo, hi = _concrete(limit[1]), _concrete(limit[2])
                if lo is None or hi is None:
                    continue  # symbolic bounds close by formula, not by expansion
                worst = max(worst, abs(hi - lo) + 1)
        elif isinstance(node, (sp.Integral, sp.Limit)):
            return False, worst
    return worst <= _MAX_EXACT_TERMS, worst


def numeric_eval(
    expression: str,
    substitutions: Mapping[str, str] | None = None,
    *,
    precision: int = _DEFAULT_PRECISION,
) -> dict[str, Any]:
    """Evaluate an expression at high precision and report how exact the value is."""
    assumption_set = split_assumptions([])
    ctx = SympyContext()
    node = parse(expression, functions=[])
    expr = ast_to_sympy(node, ctx)
    for name in sorted(expr.free_symbols, key=str):
        ctx.symbols.setdefault(name.name, name)
    mapping = {}
    for key, value in (substitutions or {}).items():
        symbol = ctx.symbols.get(key) or sp.Symbol(key)
        mapping[symbol] = to_sympy(value)
    if mapping:
        expr = expr.subs(mapping)
    remaining = sorted(str(s) for s in expr.free_symbols)
    # `doit` closes any Sum/Product with concrete bounds so exactness is judged
    # on the value rather than on the unevaluated form -- but only when that
    # closure is bounded work (see `_exact_closure_is_cheap`).
    affordable, term_count = _exact_closure_is_cheap(expr)
    exact: Any = None
    if affordable:
        try:
            exact = sp.simplify(expr.doit())
        except Exception:  # noqa: BLE001 - an exact form that cannot be built is not an error
            exact = None
    with mpmath.workdps(precision):
        value = sp.N(expr, precision)
        out: dict[str, Any] = {
            "expression": sp.sstr(expr),
            "value": sp.sstr(value),
            "precision_digits": precision,
            "is_exact_integer": bool(exact is not None and exact.is_Integer),
            "is_exact_rational": bool(exact is not None and exact.is_Rational
                                      and not exact.is_Integer),
        }
        if exact is not None and exact.is_Rational:
            try:
                out["exact_fraction"] = sp.sstr(sp.Rational(exact))
            except Exception:  # noqa: BLE001 - a huge exact rational is still a value
                out["exact_fraction"] = None
                out["exact_fraction_note"] = (
                    "the exact fraction exists but is too large to render as text"
                )
        try:
            out["decimal"] = mpmath.nstr(mpmath.mpf(str(value)), precision)
        except Exception:  # noqa: BLE001
            pass
    if not affordable:
        out["exactness"] = "not_computed"
        out["note"] = (
            f"the expression was evaluated numerically: closing it exactly would mean "
            f"expanding about {term_count:,} terms, which is not bounded work. The "
            f"{precision}-digit value above is accurate to that many digits, and "
            f"`is_exact_*` is false because exactness was not established."
        )
    if remaining:
        out["unsubstituted_symbols"] = remaining
        out["note"] = "the value is not a number until these symbols are substituted"
    return out


# --------------------------------------------------------------------------- #
# Identity verification
# --------------------------------------------------------------------------- #

_SAMPLE_RATIONALS = [(1, 2), (-1, 2), (3, 2), (2, 1), (-2, 1),
                     (1, 3), (5, 7), (-3, 4), (4, 1), (7, 5)]
_IRRATIONAL_SAMPLES = ["sqrt(2)", "pi", "e", "sqrt(3)/2"]


def _sample_values(include_irrational: bool) -> list[Any]:
    values: list[Any] = [sp.Rational(n, d) for n, d in _SAMPLE_RATIONALS]
    if include_irrational:
        values += [sp.sqrt(2), sp.pi, sp.E, sp.sqrt(3) / 2]
    return values


def verify_identity(
    lhs: str,
    rhs: str,
    *,
    variables: Sequence[str] = (),
    assumptions: Sequence[str] = (),
    precision: int = _DEFAULT_PRECISION,
    samples_per_symbol: int = 12,
) -> dict[str, Any]:
    """Decide whether two expressions are the same function.

    Returns ``proven`` when the difference collapses to zero under the stated
    assumptions, ``refuted`` with a witness when a sample falsifies it, and
    ``inconclusive`` otherwise -- in that case the residual difference is
    reported so the caller can see what is still unproved.
    """
    assumption_set = split_assumptions(assumptions)
    names = [v.strip() for v in variables if str(v).strip()]
    try:
        left_node = parse(lhs, functions=[])
        right_node = parse(rhs, functions=[])
    except Exception as exc:  # noqa: BLE001
        return {"verdict": VERDICT_ERROR, "reason": f"{type(exc).__name__}: {exc}"}

    # A summation index and its bounds are integers whether or not the caller
    # said so, and sympy needs that fact: without it the closed form comes back
    # wrapped in a `Piecewise` over `re(n)`, the difference never collapses, and
    # the identity that should have been proved is merely "inconclusive".
    forced = _bound_symbols(left_node) | _bound_symbols(right_node)
    forced_notes: list[str] = []
    for name in sorted(forced):
        if name in names and assumption_set.properties.get(name):
            continue
        if "integer" not in assumption_set.properties.get(name, []):
            assumption_set.properties.setdefault(name, []).append("integer")
            forced_notes.append(
                f"`{name}` is a summation bound, so it was taken to be an integer"
            )

    ctx = _symbol_context(names, assumption_set)
    try:
        left = ast_to_sympy(left_node, ctx)
        right = ast_to_sympy(right_node, ctx)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": VERDICT_ERROR, "reason": f"{type(exc).__name__}: {exc}"}

    for name in sorted({str(s) for s in (left.free_symbols | right.free_symbols)}):
        ctx.symbols.setdefault(name, sp.Symbol(name))

    # Close any definite Sum/Product once, before comparing: an unevaluated sum
    # is opaque to `simplify`, and sampling it at non-integer bounds used to hang
    # the process outright (see `_finite_closure`).
    raw_left, raw_right = left, right
    left = _close_bigops(left)
    right = _close_bigops(right)

    difference = sp.simplify(left - right)
    collapsed, residual, how = try_collapse(difference)

    # A sum `Sum(f, (k, 0, n))` only denotes anything for n >= 0, but sympy
    # cannot know that from `integer` alone: it hands back a `Piecewise` in
    # `re(n)` and the difference never collapses.  Rather than assume it up
    # front, retry with the bounds taken as non-negative, and say so.
    if not collapsed and forced:
        widened = AssumptionSet(properties={k: list(v) for k, v in
                                            assumption_set.properties.items()},
                                constraints=list(assumption_set.constraints))
        for name in sorted(forced):
            flags = widened.properties.setdefault(name, [])
            if "nonnegative" not in flags:
                flags.append("nonnegative")
        widened_ctx = _symbol_context(names, widened)
        try:
            wide_left = _close_bigops(ast_to_sympy(left_node, widened_ctx))
            wide_right = _close_bigops(ast_to_sympy(right_node, widened_ctx))
            wide_difference = sp.simplify(wide_left - wide_right)
            wide_collapsed, wide_residual, wide_how = try_collapse(wide_difference)
        except Exception:  # noqa: BLE001 - keep the original attempt
            wide_collapsed = False
        if wide_collapsed:
            forced_notes.append(
                "this only holds with the summation bounds non-negative, so the identity "
                "was proved for n >= 0: state that with assumptions=['n: nonnegative'] "
                "when quoting the result"
            )
            payload = {
                "verdict": VERDICT_PROVEN,
                "method": f"the difference reduces to zero by {wide_how}, with the "
                          "summation bounds taken as non-negative",
                "assumptions_used": sorted(widened.properties),
                "lhs": sp.sstr(wide_left),
                "rhs": sp.sstr(wide_right),
                "notes": forced_notes,
            }
            return payload

    if collapsed:
        payload = {
            "verdict": VERDICT_PROVEN,
            "method": f"the difference reduces to zero by {how}",
            "assumptions_used": sorted(assumption_set.properties) or None,
            "lhs": sp.sstr(left),
            "rhs": sp.sstr(right),
        }
        if forced_notes:
            payload["notes"] = forced_notes
        return payload

    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    witness = _search_counterexample(left, right, symbols, assumption_set, precision,
                                     samples_per_symbol,
                                     domain=(raw_left, raw_right))
    if witness is not None:
        payload = {
            "verdict": VERDICT_REFUTED,
            "method": "a numerical sample falsifies the identity",
            "counterexample": witness["assignment"],
            "lhs_value": witness["lhs"],
            "rhs_value": witness["rhs"],
            "note": "the two sides are genuinely different functions, not merely hard to simplify",
        }
        if forced_notes:
            payload["notes"] = forced_notes
        return payload

    payload = {
        "verdict": VERDICT_INCONCLUSIVE,
        "method": "sympy could not reduce the difference to zero and no sample falsified it",
        "residual_difference": sp.sstr(residual),
        "residual_latex": sp.latex(residual),
        "hints": [
            "state the assumptions the identity needs, e.g. assumptions=['x: positive']",
            "if the identity only holds on a domain, prove it pointwise with verify_forall",
            "an identity that survives sampling but does not simplify may still be false "
            "on a measure-zero set",
        ],
    }
    if forced_notes:
        payload["notes"] = forced_notes
    return payload


# Names that the translator resolves to constants, never to symbols: declaring
# `oo` an integer (a sum bound!) would shadow the infinity constant.
_RESERVED_SYMBOLS = {
    "oo", "infinity", "inf", "pi", "e", "E", "I", "true", "false",
    "nan", "zoo", "True", "False",
}


def _bound_symbols(node: Node) -> set[str]:
    """Symbols that the notation itself forces to be integers.

    Two sources: the index and the bounds of a `Sum`/`Product`, and the argument
    of `binomial`/`factorial`/`mod`.  A sum from `0` to `n` is only a sum for
    integer (and, after the second pass, non-negative) `n`, and `binomial(x, k)`
    is meant combinatorially rather than as a gamma function.
    """
    found: set[str] = set()
    stack: list[Node] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, BigOp):
            found.add(current.var)
            found |= collect_symbols(current.lo) - _RESERVED_SYMBOLS
            found |= collect_symbols(current.hi) - _RESERVED_SYMBOLS
            stack.append(current.expr)
            continue
        if isinstance(current, App):
            if current.name in ("binomial", "factorial", "mod"):
                for argument in current.args:
                    found |= collect_symbols(argument)
        for child in _children(current):
            stack.append(child)
    return found


def _children(node: Node) -> list[Node]:
    from dataclasses import fields

    out: list[Node] = []
    for field_info in fields(node):
        value = getattr(node, field_info.name)
        if isinstance(value, Node):
            out.append(value)
        elif isinstance(value, tuple):
            out.extend(v for v in value if isinstance(v, Node))
    return out


def _close_bigops(expr: Any) -> Any:
    """Replace each `Sum`/`Product` by its closed form when sympy finds one."""
    for big in list(expr.atoms(sp.Sum)) + list(expr.atoms(sp.Product)):
        try:
            closed = big.doit()
        except Exception:  # noqa: BLE001 - leave unclosable sums as they are
            continue
        if isinstance(closed, (sp.Sum, sp.Product)):
            continue
        expr = expr.subs(big, closed)
    return expr


def _finite_closure(big: Any, budget: int = _MAX_EXACT_TERMS) -> Any | None:
    """The value of a `Sum`/`Product` with concrete integer bounds, or None.

    This is what keeps sampling finite.  Substituting a rational into
    ``Sum(binomial(n, k), (k, 0, n))`` leaves a sum with a fractional upper
    bound, and ``sp.N`` then attempts a symbolic summation that never returns;
    measured, `verify_identity("Sum(binomial(n,k),(k,0,n))", "2^n")` hung past
    25s on that path.  Adding the terms by hand is both bounded and exact.
    """
    if len(big.limits) != 1:
        return None
    index, lower, upper = big.limits[0]
    try:
        lo = sp.Integer(lower)
        hi = sp.Integer(upper)
    except Exception:  # noqa: BLE001 - a bound that is not an integer
        return None
    count = int(hi - lo) + 1
    if count < 0:
        return sp.Integer(1) if isinstance(big, sp.Product) else sp.Integer(0)
    if count > budget:
        return None
    total = sp.Integer(1) if isinstance(big, sp.Product) else sp.Integer(0)
    for step in range(count):
        term = big.function.subs(index, lo + step)
        total = total * term if isinstance(big, sp.Product) else total + term
    return total


def _numeric_value(expr: Any, substitutions: Mapping[Any, Any], precision: int) -> Any:
    """Evaluate numerically with every concrete `Sum`/`Product` added up by hand."""
    evaluated = expr.subs(substitutions)
    for big in list(evaluated.atoms(sp.Sum)) + list(evaluated.atoms(sp.Product)):
        closed = _finite_closure(big)
        if closed is None:
            raise ValueError("the sample leaves a sum that cannot be added up finitely")
        evaluated = evaluated.subs(big, closed)
    return sp.N(evaluated, precision)


def _bigop_bounds_ok(exprs: Sequence[Any], substitution: Mapping[Any, Any]) -> bool:
    """True when every `Sum`/`Product` in ``exprs`` has a non-empty range here."""
    for expr in exprs:
        for big in list(expr.atoms(sp.Sum)) + list(expr.atoms(sp.Product)):
            if len(big.limits) != 1:
                continue
            _index, lower, upper = big.limits[0]
            try:
                lo = complex(lower.subs(substitution).evalf())
                hi = complex(upper.subs(substitution).evalf())
            except Exception:  # noqa: BLE001 - a symbolic bound says nothing
                continue
            if lo.imag or hi.imag:
                continue
            if hi.real < lo.real:
                return False
    return True


def _is_admissible_sub(assignment: Mapping[str, Any], assumption_set: AssumptionSet) -> bool:
    """Reject samples that violate a stated symbol property.

    This has to hold, or a sample that is outside the declared domain becomes a
    "counterexample": the identity `sin(pi*n) = 0` is true on the integers and
    false at ``n = 3/2``, so sampling an integer symbol at a rational produces a
    refutation of a true statement.  (An earlier duplicate definition of this
    function shadowed the integer check with dead code; there is one now.)
    """
    for name, value in assignment.items():
        flags = assumption_set.properties.get(name, [])
        if "positive" in flags and not (value > 0):
            return False
        if "negative" in flags and not (value < 0):
            return False
        if ("nonzero" in flags or "positive" in flags or "negative" in flags) and value == 0:
            return False
        if "integer" in flags or "natural" in flags:
            try:
                if not sp.Rational(value).is_Integer:
                    return False
            except Exception:  # noqa: BLE001 - a non-numeric sample is not admissible
                return False
        if "even" in flags or "odd" in flags:
            try:
                number = sp.Rational(value)
            except Exception:  # noqa: BLE001
                return False
            if not number.is_Integer:
                return False
            if "even" in flags and int(number) % 2 != 0:
                return False
            if "odd" in flags and int(number) % 2 == 0:
                return False
    return True


def _search_counterexample(
    left: sp.Expr,
    right: sp.Expr,
    symbols: Sequence[sp.Symbol],
    assumption_set: AssumptionSet,
    precision: int,
    samples_per_symbol: int,
    domain: Sequence[sp.Expr] = (),
) -> dict[str, Any] | None:
    import itertools

    if not symbols:
        return None
    pool: list[list[Any]] = []
    per_symbol = min(samples_per_symbol, len(_SAMPLE_RATIONALS) + len(_IRRATIONAL_SAMPLES))
    for index, symbol in enumerate(symbols):
        values = _sample_values(include_irrational=index == 0)
        pool.append(values[:per_symbol])
    checked = 0
    for combination in itertools.product(*pool):
        if len(symbols) > 3 and checked > 4000:
            break
        assignment = dict(zip((s.name for s in symbols), combination))
        if not _is_admissible_sub(assignment, assumption_set):
            continue
        if not _bigop_bounds_ok(domain, dict(zip(symbols, combination))):
            # `Sum(f, (k, 0, n))` at n = -1 is not this identity's domain, it is
            # an empty sum; sampling there refutes a true identity.
            continue
        checked += 1
        try:
            with mpmath.workdps(precision):
                lhs_value = _numeric_value(left, dict(zip(symbols, combination)), precision)
                rhs_value = _numeric_value(right, dict(zip(symbols, combination)), precision)
                if not (lhs_value.is_finite and rhs_value.is_finite):
                    continue
                lhs_float = mpmath.mpf(str(lhs_value))
                rhs_float = mpmath.mpf(str(rhs_value))
                scale = max(1, abs(lhs_float), abs(rhs_float))
                if abs(lhs_float - rhs_float) > mpmath.mpf(10) ** (-(precision - 10)) * scale:
                    return {
                        "assignment": {k: sp.sstr(v) for k, v in assignment.items()},
                        "lhs": sp.sstr(lhs_value),
                        "rhs": sp.sstr(rhs_value),
                    }
        except Exception:  # noqa: BLE001 - singular samples are simply skipped
            continue
    return None
