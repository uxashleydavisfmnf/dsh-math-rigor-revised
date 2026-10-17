"""Math-rigor toolkit: parsing, logic checking, symbolic verification, proof audit."""

import sys as _sys

from .ast_nodes import Node, ParseError, parse
from .engine import ENGINE_LOCK, serialised

__all__ = ["Node", "ParseError", "parse", "ENGINE_LOCK", "serialised"]

# Expression handling is recursive: the parser walks a parenthesised group or a
# right-hand operand with a Python call per nesting level, and the AST helpers
# (`walk`, `format_node`, the SMT translation) recurse over the tree.  CPython's
# default limit of 1000 therefore caps a plain polynomial at roughly 300 terms
# and a nested expression at roughly 100 levels, which is well below what a
# legitimate call can contain; a 3,000-term expansion was rejected outright with
# a bare RecursionError.  Pure-Python frames in 3.11+ live on the heap rather
# than the C stack, so a higher limit costs memory, not stability: with 20,000
# the parser handles a 6,000-term sum and 1,000 levels of nesting, and anything
# larger still fails cleanly (the server turns RecursionError into an actionable
# message rather than a traceback).  Interactive callers may override this by
# setting a higher limit before importing the toolkit.
_MIN_RECURSION_LIMIT = 20000
if _sys.getrecursionlimit() < _MIN_RECURSION_LIMIT:
    _sys.setrecursionlimit(_MIN_RECURSION_LIMIT)
