"""Async-to-sync bridge for calling async functions from sync skill code.

Skills execute synchronously (via executor.execute()), but some operations
require async functions (document QA, LLM calls, feature planning).
This utility provides a single, tested bridge pattern instead of repeating
the ThreadPoolExecutor + asyncio.run() boilerplate at each call site.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)


def run_async(coro, timeout: float | None = None):
    """Run an async coroutine from synchronous code.

    If an event loop is already running (e.g. inside a FastAPI request or
    the agent loop), executes the coroutine in a worker thread with its own
    fresh event loop to avoid nested-loop errors.

    If no loop is running, uses asyncio.run() directly.

    Args:
        coro: An awaitable coroutine to execute.
        timeout: Optional timeout in seconds. Raises TimeoutError if exceeded.
                 None means no timeout (default).

    Returns:
        The return value of the coroutine.

    Raises:
        Any exception raised by the coroutine.
        concurrent.futures.TimeoutError if timeout is exceeded.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=timeout)
    else:
        if timeout is not None:
            # asyncio.run doesn't support timeout directly; wrap with wait_for
            async def _with_timeout():
                return await asyncio.wait_for(coro, timeout=timeout)
            return asyncio.run(_with_timeout())
        return asyncio.run(coro)
