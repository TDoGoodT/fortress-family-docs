"""Tests for src/utils/async_bridge.py — run_async utility."""
from __future__ import annotations

import asyncio
import concurrent.futures

import pytest


def test_run_async_returns_result():
    """run_async executes a coroutine and returns its result."""
    from src.utils.async_bridge import run_async

    async def add(a, b):
        return a + b

    assert run_async(add(2, 3)) == 5


def test_run_async_propagates_exception():
    """run_async re-raises exceptions from the coroutine."""
    from src.utils.async_bridge import run_async

    async def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async(fail())


def test_run_async_respects_timeout():
    """run_async raises TimeoutError when coroutine exceeds timeout."""
    from src.utils.async_bridge import run_async

    async def slow():
        await asyncio.sleep(10)

    with pytest.raises((concurrent.futures.TimeoutError, TimeoutError)):
        run_async(slow(), timeout=0.05)


def test_run_async_works_with_no_running_loop():
    """run_async works when called outside any event loop."""
    from src.utils.async_bridge import run_async

    async def greet(name: str) -> str:
        return f"hello {name}"

    result = run_async(greet("world"))
    assert result == "hello world"
