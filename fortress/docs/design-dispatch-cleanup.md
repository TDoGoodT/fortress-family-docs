# Design Doc: Dispatch Cleanup — Intent Detector, LLM Dispatch, Async Bridge

## A. Goal

Eliminate three sources of internal duplication in the Fortress dispatch layer:

1. A dead-code module (`intent_detector.py`) with one surviving 5-line function
2. Two structurally identical Bedrock→Ollama fallback implementations
   (`llm_dispatch.llm_generate` vs `ChatSkill._dispatch_llm`)
3. Five copy-pasted async-to-sync bridging blocks across two skill files

Constraints:
- Preserve all external behavior (message responses, error handling, logging)
- Do not modify the agent loop (`agent_loop.py`)
- Do not modify tool registration (`tool_registry.py`, `tool_router.py`)
- Every change must pass the existing test suite before and after

---

## B. Current State

### B1. Intent Detector

**File:** `src/services/intent_detector.py` (60 lines)

Two public functions:
- `detect_intent(message)` → returns intent string. **Zero callers.** Dead code.
- `should_fallback_to_chat(message)` → returns bool. **One caller:**
  `message_handler.py` line 14 (import), line 55 (call inside `_run_regex_path`)

`should_fallback_to_chat` checks 5 regex patterns (`בדיחה|translate|תרגם|מה זה|who is|what is`)
and returns True if any match. It gates whether `_run_regex_path` routes to
`ChatSkill.respond()` or returns `TEMPLATES["cant_understand"]`.

### B2. LLM Dispatch Duplication

**Path A — `src/services/llm_dispatch.py` function `llm_generate()`** (lines 18-58)
- Signature: `async def llm_generate(prompt, system_prompt, model_tier="lite") -> str`
- Model resolution: `get_model_id(resolve_tier(model_tier))`
- Fallback chain: `BedrockClient.generate()` → `OllamaClient.generate()` → `""`
- Callers: `document_classifier.py`, `document_fact_extractor.py`,
  `document_summarizer.py`, `document_query_service.py`, `document_namer.py`

**Path B — `src/skills/chat_skill.py` method `ChatSkill._dispatch_llm()`** (lines 129-170)
- Signature: `async def _dispatch_llm(self, prompt, system_prompt, intent, context=None, session_tier=None) -> str`
- Model resolution: `select_model(intent, session_tier=session_tier)`
- Fallback chain: `BedrockClient.generate()` → `OllamaClient.generate()` → `HEBREW_FALLBACK`
- Callers: only `ChatSkill.respond()` (line 107)
- Extra: timing logs, `_is_valid_response()` helper (lines 172-178)

**Behavioral differences:**
| Aspect              | Path A (`llm_generate`)       | Path B (`_dispatch_llm`)       |
|---------------------|-------------------------------|--------------------------------|
| Return on failure   | `""` (empty string)           | `HEBREW_FALLBACK` constant     |
| Model selection     | `resolve_tier(model_tier)`    | `select_model(intent, session_tier)` |
| Validation          | `!= HEBREW_FALLBACK`          | `_is_valid_response()` (len>2) |
| Timing logs         | No                            | Yes                            |
| Session tier        | Not supported                 | Supported via param            |

The caller `ChatSkill.respond()` already handles both failure modes:
```python
if not raw or raw == HEBREW_FALLBACK:
    return TEMPLATES["error_fallback"]
```
So switching to `llm_generate` (which returns `""`) is safe — `if not raw` catches it.

### B3. Async Bridging

**Pattern:** sync skill `execute()` needs to call an async function.
Current approach: detect running loop → ThreadPoolExecutor + `asyncio.run()` in thread.

**5 sites using this pattern:**

| # | File                    | Method              | Async function called              |
|---|-------------------------|---------------------|------------------------------------|
| 1 | `dev_skill.py:334`      | `_query_llm`        | `bedrock.converse()`               |
| 2 | `dev_skill.py:367`      | `_handle_plan`      | `generate_plan()`                  |
| 3 | `document_skill.py:~540`| `_query`            | `answer_document_question()`       |
| 4 | `document_skill.py:~621`| `_contextual_query` | `answer_document_question()`       |
| 5 | `document_skill.py:~850`| `_doc_search_fallback`| `answer_document_question()`     |

Sites 3-5 are identical 10-line blocks. Sites 1-2 are 4-line variants
(no loop detection, always use ThreadPoolExecutor).

---

## C. Proposed Design

### C1. Delete intent_detector.py, inline the surviving function

**Files changed:**
- DELETE: `src/services/intent_detector.py`
- MODIFY: `src/services/message_handler.py`

**After the change:**
- `message_handler.py` owns `_should_fallback_to_chat()` as a private function
- The 5 regex patterns move into `message_handler.py` as a module-level constant
- `detect_intent()` and all its patterns are deleted (zero callers)

**What is deleted:**
- `intent_detector.py` entirely (60 lines)
- The import `from src.services.intent_detector import should_fallback_to_chat`

**What is introduced:**
- In `message_handler.py`, after the existing `_COMPLETION_PHRASES` block:
  ```python
  _NON_SYSTEM_PATTERNS = [
      _re.compile(r"(בדיחה|translate|תרגם|מה זה|who is|what is)", _re.IGNORECASE),
  ]

  def _should_fallback_to_chat(message: str) -> bool:
      text = (message or "").strip()
      if not text:
          return False
      return any(p.search(text) for p in _NON_SYSTEM_PATTERNS)
  ```
- The call on line 55 changes from `should_fallback_to_chat(message_text)`
  to `_should_fallback_to_chat(message_text)`

**Compatibility:** Identical behavior. The function body is unchanged.
The only difference is the import path, which no external code depends on.

### C2. Unify non-agent LLM dispatch

**Files changed:**
- MODIFY: `src/services/llm_dispatch.py` — add `task_type` param for `select_model` routing
- MODIFY: `src/skills/chat_skill.py` — delete `_dispatch_llm`, `_is_valid_response`, use `llm_generate`
- MODIFY: `tests/test_chat_skill.py` — update 2 tests that mock `_dispatch_llm`
- MODIFY: `tests/test_pii_integration.py` — update 3 tests that mock `_dispatch_llm`

**After the change:**
- `llm_dispatch.llm_generate()` is the single non-agent LLM entry point
- `ChatSkill` has no LLM dispatch logic — it calls `llm_generate()` and
  handles the empty-string return
- All document services continue calling `llm_generate()` unchanged

**Changes to `llm_dispatch.py`:**

New signature:
```python
async def llm_generate(
    prompt: str,
    system_prompt: str,
    model_tier: str = "lite",
    task_type: str | None = None,  # NEW — for select_model routing
) -> str:
```

New model resolution logic (replaces lines 31-32):
```python
from src.services.model_selector import get_model_id, resolve_tier, select_model
if task_type:
    model_id = select_model(task_type)
else:
    model_id = get_model_id(resolve_tier(model_tier))
```

This preserves backward compatibility: existing callers pass `model_tier`
and get the same behavior. ChatSkill passes `task_type="chat"` to get
`select_model("chat")` routing (which maps to "standard" tier by default).

**Changes to `chat_skill.py`:**

Delete methods:
- `_dispatch_llm()` (lines 129-170, ~42 lines)
- `_is_valid_response()` (lines 172-178, ~7 lines)

Delete unused imports (after removing _dispatch_llm):
- `from src.services.bedrock_client import HEBREW_FALLBACK, BedrockClient` — keep `HEBREW_FALLBACK` only
- `from src.services.llm_client import OllamaClient` — delete entirely
- `import time` — delete (no longer used)
- `from typing import Any` — delete (no longer used)

Add import:
- `from src.services.llm_dispatch import llm_generate`

Change in `respond()` (replace lines 107-112):
```python
# Before:
raw = await self._dispatch_llm(
    prompt=prompt,
    system_prompt=CHAT_SYSTEM_PROMPT,
    intent="needs_llm",
)
if not raw or raw == HEBREW_FALLBACK:
    return TEMPLATES["error_fallback"]

# After:
raw = await llm_generate(prompt, CHAT_SYSTEM_PROMPT, task_type="chat")
if not raw:
    return TEMPLATES["error_fallback"]
```

**Why `if not raw` is sufficient:** `llm_generate` returns `""` on failure.
`""` is falsy. The `HEBREW_FALLBACK` check is no longer needed because
`llm_generate` already filters it out internally (line 41 of llm_dispatch.py:
`if result != HEBREW_FALLBACK`).

**Test changes:**

`test_chat_skill.py` — 2 tests:
- `test_respond_calls_llm` (line 116): change mock target from
  `patch.object(ChatSkill, "_dispatch_llm", ...)` to
  `patch("src.skills.chat_skill.llm_generate", ...)`
- `test_respond_fallback_on_llm_failure` (line 134): same mock target change,
  return value changes from `HEBREW_FALLBACK` to `""` (empty string)

`test_pii_integration.py` — 3 tests:
- `test_respond_strips_pii_before_llm` (line 54): change
  `patch.object(skill, "_dispatch_llm", ...)` to
  `patch("src.skills.chat_skill.llm_generate", ...)`
  The side_effect function signature changes from `(prompt, **kwargs)` to
  `(prompt, system_prompt, **kwargs)` to match `llm_generate`'s signature.
- `test_respond_restores_pii_in_llm_response` (line 80): same change.
- `test_respond_fallback_when_strip_pii_fails` (line 136): same change.

**Compatibility:**
- All 5 document service callers are unchanged (they use `model_tier`, not `task_type`)
- `ChatSkill.respond()` returns identical strings for success and failure cases
- The `HEBREW_FALLBACK` import in `chat_skill.py` is still needed by the
  `respond()` method? No — after the change, `respond()` only checks `if not raw`.
  But `HEBREW_FALLBACK` may be imported by tests. Check: `test_chat_skill.py`
  line 7 imports it. Keep the import in `chat_skill.py` for now, or update
  the test import to come from `bedrock_client` directly.

### C3. Centralize async bridging

**Files changed:**
- NEW: `src/utils/async_bridge.py`
- MODIFY: `src/skills/document_skill.py` (3 sites)
- MODIFY: `src/skills/dev_skill.py` (2 sites)

**After the change:**
- `async_bridge.run_async(coro, timeout)` is the single way to call async
  from sync skill code
- All 5 bridging sites are replaced with 1-line calls
- The loop-detection + ThreadPoolExecutor logic exists in exactly one place

**New file `src/utils/async_bridge.py`:**

```python
"""Async-to-sync bridge for calling async functions from sync skill code."""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging

logger = logging.getLogger(__name__)


def run_async(coro, timeout: float = 60.0):
    """Run an async coroutine from synchronous code.

    If an event loop is already running (FastAPI request context),
    executes in a thread with a fresh loop. Otherwise uses asyncio.run().
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
        return asyncio.run(coro)
```

**Changes to `document_skill.py`:**

Add import at top:
```python
from src.utils.async_bridge import run_async
```

Remove imports that become unused:
```python
# These can be removed from document_skill.py:
import asyncio  # only used for the bridging pattern
```

Replace 3 identical blocks. Example for `_query()`:
```python
# Before (~10 lines):
loop = None
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = None
if loop and loop.is_running():
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        qa_result: QAResult = pool.submit(
            asyncio.run,
            answer_document_question(db, member, question, doc),
        ).result()
else:
    qa_result = asyncio.run(answer_document_question(db, member, question, doc))

# After (1 line):
qa_result: QAResult = run_async(answer_document_question(db, member, question, doc))
```

Same replacement in `_contextual_query()` and `_doc_search_fallback()`.

Note: `document_skill.py` also uses `asyncio` in `_save()` and `_save_text()`
for a different pattern (threading.Thread with new_event_loop). Those are NOT
part of this refactor — they use a different mechanism (dedicated thread with
its own loop) and should be left alone in this phase.

**Changes to `dev_skill.py`:**

Add import at top:
```python
from src.utils.async_bridge import run_async
```

Replace in `_query_llm()` (line ~334):
```python
# Before:
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future = pool.submit(asyncio.run, client.converse(
        messages=messages,
        system_prompt=system_prompt,
        model=model_id,
        max_tokens=2048,
    ))
    response = future.result(timeout=60)

# After:
response = run_async(client.converse(
    messages=messages,
    system_prompt=system_prompt,
    model=model_id,
    max_tokens=2048,
), timeout=60)
```

Replace in `_handle_plan()` (line ~367):
```python
# Before:
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future = pool.submit(asyncio.run, generate_plan(feature_request))
    plan = future.result(timeout=120)

# After:
plan = run_async(generate_plan(feature_request), timeout=120)
```

Remove now-unused imports from `dev_skill.py`:
```python
import asyncio  # no longer needed directly
# concurrent.futures — no longer needed (was imported inline)
```

**Compatibility:**
- `run_async()` implements the exact same logic as the inlined blocks
- The `max_workers=1` constraint is preserved in the utility
- Timeout behavior is preserved (dev_skill uses 60s and 120s, document_skill
  had no explicit timeout — `run_async` defaults to 60s which is reasonable)
- The `_save()` and `_save_text()` methods in document_skill.py use a
  different async pattern (threading.Thread) and are NOT touched

---

## D. Risks

### D1. Refactor 1 (intent_detector deletion)

**What could break:** Nothing. `detect_intent()` has zero callers.
`should_fallback_to_chat()` is moved, not changed.

**How to detect:** `pytest tests/test_message_handler.py -x -q`

**How to roll back:** `git revert` the single commit.

### D2. Refactor 2 (LLM dispatch unification)

**What could break:**
- ChatSkill could return different error messages if the empty-string
  handling differs from HEBREW_FALLBACK handling. Mitigated: `respond()`
  already checks `if not raw or raw == HEBREW_FALLBACK` — after the change,
  `if not raw` catches the empty string.
- Tests that mock `_dispatch_llm` will fail until updated. This is expected
  and the test changes are part of the commit.
- If any code outside the known callers patches `_dispatch_llm` at runtime
  (e.g., a test we haven't found), it will silently stop working. Mitigated:
  grep confirms only `test_chat_skill.py` and `test_pii_integration.py`.

**How to detect:** `pytest tests/test_chat_skill.py tests/test_pii_integration.py tests/test_message_handler.py -x -q`

**How to roll back:** `git revert` the single commit.

### D3. Refactor 3 (async bridge)

**What could break:**
- The `run_async()` utility could behave differently from the inlined blocks
  in edge cases (e.g., nested event loops, thread-local state). Mitigated:
  the implementation is identical to the existing pattern.
- `document_skill.py` `_save()` and `_save_text()` use a DIFFERENT async
  pattern (threading.Thread with new_event_loop). If someone accidentally
  converts those too, it could break. Mitigated: design doc explicitly
  excludes them.
- Timeout default (60s) may be too short for some document queries.
  Mitigated: callers can pass explicit timeout.

**How to detect:** `pytest tests/test_document_skill.py tests/test_dev_skill.py -x -q`

**How to roll back:** `git revert` the single commit.

---

## E. Tests

### E1. Existing tests to rely on (run before AND after each refactor)

| Test file                          | Covers                                    | Count |
|------------------------------------|-------------------------------------------|-------|
| `test_message_handler.py`          | Auth, routing, fallback, intent tracking  | 12    |
| `test_chat_skill.py`              | Greet, respond, LLM dispatch              | ~8    |
| `test_pii_integration.py`         | PII stripping/restoration in ChatSkill    | ~5    |
| `test_executor.py`                | Skill dispatch, verify, audit, confirm    | 10    |
| `test_tool_router.py`             | classify(), tool counts, intent groups    | 18    |
| `test_command_parser.py`          | Regex matching, media, cancel/confirm     | ~10   |
| `test_document_skill.py`          | Document actions                          | ~15   |
| `test_dev_skill.py`               | Dev actions (index, query, plan)          | ~10   |
| `test_agent_planning.py`          | Agent loop with mocked bedrock            | ~5    |

### E2. New tests to add BEFORE starting refactors

**Test 1: Consistency guard for tool registry (add to `test_tool_router.py`)**
```python
def test_all_intent_tools_exist_in_tool_map():
    """Every tool name in _INTENT_TOOLS must exist in _TOOL_MAP."""
    from src.engine.tool_router import _INTENT_TOOLS
    from src.engine.tool_registry import get_tool_map
    tool_map = get_tool_map()
    for group, tools in _INTENT_TOOLS.items():
        for tool_name in tools:
            assert tool_name in tool_map, (
                f"{tool_name} in _INTENT_TOOLS['{group}'] but missing from _TOOL_MAP"
            )
```
Rationale: catches the exact class of silent failures the current scattered
registration enables. Not directly related to Refactors 1-3, but establishes
a safety net before any future tool changes.

**Test 2: Async bridge unit tests (new file `test_async_bridge.py`)**
```python
import asyncio
import pytest
import concurrent.futures

def test_run_async_returns_result():
    from src.utils.async_bridge import run_async
    async def add(a, b):
        return a + b
    assert run_async(add(2, 3)) == 5

def test_run_async_propagates_exception():
    from src.utils.async_bridge import run_async
    async def fail():
        raise ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        run_async(fail())

def test_run_async_respects_timeout():
    from src.utils.async_bridge import run_async
    async def slow():
        await asyncio.sleep(10)
    with pytest.raises((concurrent.futures.TimeoutError, TimeoutError)):
        run_async(slow(), timeout=0.1)
```

**Test 3: LLM dispatch with task_type (add to existing `test_llm_client.py` or new file)**
```python
@pytest.mark.asyncio
async def test_llm_generate_task_type_uses_select_model():
    """When task_type is provided, llm_generate uses select_model() routing."""
    from src.services.llm_dispatch import llm_generate
    with patch("src.services.llm_dispatch.BedrockClient") as mock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate.return_value = "response text"
        mock_cls.return_value = mock_bedrock
        with patch("src.services.llm_dispatch.select_model", return_value="test-model-id") as mock_select:
            result = await llm_generate("prompt", "system", task_type="chat")
            mock_select.assert_called_once_with("chat")
            assert result == "response text"

@pytest.mark.asyncio
async def test_llm_generate_model_tier_backward_compat():
    """Existing callers using model_tier still work."""
    from src.services.llm_dispatch import llm_generate
    with patch("src.services.llm_dispatch.BedrockClient") as mock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate.return_value = "response text"
        mock_cls.return_value = mock_bedrock
        result = await llm_generate("prompt", "system", model_tier="lite")
        assert result == "response text"
```

### E3. Regression cases to cover

| Scenario                                          | Verified by                        |
|---------------------------------------------------|------------------------------------|
| Unknown phone → rejection message                 | `test_message_handler::test_unknown_phone_rejected` |
| Chat fallback for "תן לי בדיחה"                   | `test_message_handler::test_chat_fallback_for_clear_non_system_query` |
| Non-system message without match → cant_understand | `test_message_handler::test_strict_unknown_when_no_match` |
| PII stripped before LLM call                      | `test_pii_integration::test_respond_strips_pii_before_llm` |
| PII restored in LLM response                     | `test_pii_integration::test_respond_restores_pii_in_llm_response` |
| LLM failure → error_fallback template             | `test_chat_skill::test_respond_fallback_on_llm_failure` |
| Task commands bypass agent                        | `test_message_handler::test_task_commands_bypass_agent` |
| Document query via agent tool                     | `test_document_skill.py` (existing) |
| Dev query via sync bridge                         | `test_dev_skill.py` (existing)     |

---

## F. Implementation Sequence

### Commit 1: Add safety-net tests (no production code changes)

Files: `tests/test_tool_router.py`, `tests/test_async_bridge.py`, `tests/test_llm_dispatch.py`

Add the 3 new test groups from section E2. Run full suite. Commit.

This establishes the baseline before any production changes.

### Commit 2: Delete intent_detector.py

Files changed:
1. `src/services/message_handler.py` — add `_NON_SYSTEM_PATTERNS` and
   `_should_fallback_to_chat()` after line 28, update call on line 55,
   remove import on line 14
2. DELETE `src/services/intent_detector.py`

Run: `pytest tests/test_message_handler.py -x -q`
Then: `pytest tests/ -x -q` (full suite)

### Commit 3: Add task_type param to llm_generate

Files changed:
1. `src/services/llm_dispatch.py` — add `task_type` parameter, add
   `select_model` import, add conditional model resolution

Run: `pytest tests/test_llm_dispatch.py -x -q` (new tests from Commit 1)
Then: `pytest tests/ -x -q` (full suite — backward compat)

This is a pure addition. No existing callers change. No behavior changes.

### Commit 4: Switch ChatSkill to llm_generate, delete _dispatch_llm

Files changed:
1. `src/skills/chat_skill.py` — delete `_dispatch_llm` and `_is_valid_response`,
   add `from src.services.llm_dispatch import llm_generate`, update `respond()`
2. `tests/test_chat_skill.py` — update 2 test mock targets
3. `tests/test_pii_integration.py` — update 3 test mock targets

Run: `pytest tests/test_chat_skill.py tests/test_pii_integration.py -x -q`
Then: `pytest tests/ -x -q`

### Commit 5: Create async_bridge utility

Files changed:
1. NEW `src/utils/__init__.py` (empty, if not exists)
2. NEW `src/utils/async_bridge.py`

Run: `pytest tests/test_async_bridge.py -x -q` (tests from Commit 1)

Pure addition. No production code changes yet.

### Commit 6: Apply async_bridge to document_skill.py

Files changed:
1. `src/skills/document_skill.py` — replace 3 bridging blocks with
   `run_async()` calls, add import, remove unused `asyncio` import

Run: `pytest tests/test_document_skill.py -x -q`
Then: `pytest tests/ -x -q`

### Commit 7: Apply async_bridge to dev_skill.py

Files changed:
1. `src/skills/dev_skill.py` — replace 2 bridging blocks with
   `run_async()` calls, add import, remove unused imports

Run: `pytest tests/test_dev_skill.py -x -q`
Then: `pytest tests/ -x -q`

---

**Total: 7 commits, each independently revertible.**

Net result: ~155 lines deleted, ~45 lines added, 1 file deleted, 1 file created.
