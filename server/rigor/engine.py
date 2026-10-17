"""Serialisation of the native solver engine.

z3's Python bindings share one global context, and that context is **not**
thread-safe: two threads inside `z3.Solver.check()` at the same time corrupt the
solver's reference counts.  The failure is not a Python exception that a caller
could catch -- z3 5.1.0 aborts the interpreter with

    Z3 fatal error ... concurrent
    OSError: exception: access violation reading 0x0000000000000000
    (process exit 0xC0000374, STATUS_HEAP_CORRUPTION)

or, more quietly, raises `Z3Exception: Context mismatch` / `Value cannot be
converted into a Z3 Boolean value` from a *later, unrelated* call, because a
freed solver handle was collected on another thread.

An MCP server does issue concurrent tool calls: a client may pipeline requests,
and the transport dispatches each one on its own worker.  Measured against the
0.2.2 build, pipelined requests killed the server process in 2 of 3 trials and
corrupted the result of every z3 call in the third, while one-request-at-a-time
traffic was clean 3/3 -- so the engine has to be serialised explicitly.

``RLock`` (not ``Lock``) is required: the entry points nest (a proof step check
calls the entailment checker, the residue split calls the refutation core), and
re-entrancy keeps that free.  The cost is bounded and honest -- a long solver
query delays another solver query instead of corrupting the process.
"""

from __future__ import annotations

import threading

__all__ = ["ENGINE_LOCK", "serialised"]

ENGINE_LOCK = threading.RLock()


def serialised(function):
    """Run ``function`` with the native engine held for this process.

    Apply to every entry point that touches z3 (directly or through a helper
    that does).  Because the lock is re-entrant, nesting is harmless.
    """
    import functools

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with ENGINE_LOCK:
            return function(*args, **kwargs)

    wrapper.__serialised__ = True  # type: ignore[attr-defined]
    return wrapper
