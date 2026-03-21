# Pipeline Resilience Hotfix — Bugfix Design

## Overview

The Fortress LLM pipeline discards valid responses due to brittle JSON parsing in `unified_handler.py`, weak response validation in `model_dispatch.py`, and state-overwrite bugs in `workflow_engine.py`. The fix introduces a multi-strategy JSON healing function, raw-text fallback, stricter dispatcher validation, workflow state protection, a JSON-only prompt hint, `response_format` for OpenRouter payloads, and structured logging at every decision point. Files `routing_policy.py` and `bedrock_client.py` are explicitly out of scope.

## Glossary

- **Bug_Condition (C)**: The set of inputs where the LLM returns non-strict-JSON (markdown-wrapped, prefixed, embedded, or plain text) causing `json.loads()` to throw, OR where empty/whitespace responses pass validation, OR where workflow nodes overwrite the LLM response in state.
- **Property (P)**: The desired behavior — valid content is extracted via healing strategies or used as raw text; empty/whitespace responses trigger fallback; workflow nodes never overwrite the `"response"` key.
- **Preservation**: Clean JSON parsing, genuine-failure fallback, valid Hebrew text responses, routing policy order, Bedrock client behavior, and all 150 existing tests must remain unchanged.
- **`_heal_json(raw)`**: New function in `unified_handler.py` that attempts 4 strategies to extract a JSON dict from a raw LLM string.
- **`_is_valid_response(result)`**: New function in `model_dispatch.py` that rejects empty, whitespace-only, too-short, and known-fallback strings.
- **HEBREW_FALLBACK**: The constant `"מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."` used as the last-resort response.

## Bug Details

### Bug Condition

The bug manifests across three subsystems:

1. **JSON Parsing** (`unified_handler.py`): When the LLM returns valid content that is not strict JSON (wrapped in markdown fences, prefixed with explanatory text, or containing embedded JSON), `json.loads(raw)` throws `JSONDecodeError` and the handler returns `HEBREW_FALLBACK_MSG`, discarding the valid answer.

2. **Response Validation** (`model_dispatch.py`): When a provider returns an empty string `""` or whitespace-only string `"   "`, the check `result != HEBREW_FALLBACK` passes, so the dispatcher treats it as a valid response and does not fall back to the next provider.

3. **State Overwrite** (`workflow_engine.py`): When `memory_save_node` or `conversation_save_node` returns a dict containing a `"response"` key, LangGraph merges it into state, overwriting the real LLM response.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {raw_llm_output: str, provider_result: str, node_return: dict}
  OUTPUT: boolean

  json_bug := (
    raw_llm_output is not empty
    AND json.loads(raw_llm_output) raises JSONDecodeError
    AND (containsMarkdownFences(raw_llm_output)
         OR containsPrefixedJSON(raw_llm_output)
         OR containsEmbeddedJSON(raw_llm_output)
         OR isPlainTextWithContent(raw_llm_output))
  )

  validation_bug := (
    provider_result.strip() == ""
    OR len(provider_result.strip()) < 2
  )

  overwrite_bug := (
    "response" IN node_return.keys()
    AND node_return originates from memory_save_node or conversation_save_node
  )

  RETURN json_bug OR validation_bug OR overwrite_bug
END FUNCTION
```

### Examples

- **Markdown fences**: LLM returns `` ```json\n{"intent":"greeting","response":"שלום!"}\n``` `` → current code throws `JSONDecodeError`, returns fallback. Expected: parse inner JSON, return `("greeting", "שלום!", None)`.
- **Prefixed text**: LLM returns `"Here is the response: {"intent":"greeting","response":"שלום!"}"` → current code throws `JSONDecodeError`. Expected: extract JSON via regex, return `("greeting", "שלום!", None)`.
- **Embedded JSON**: LLM returns `"I'll respond now.\n{"intent":"unknown","response":"לא ברור"}\nHope that helps."` → current code throws. Expected: extract via first-brace-to-last-brace, return `("unknown", "לא ברור", None)`.
- **Plain Hebrew text**: LLM returns `"שלום, מה שלומך היום?"` (no JSON at all) → current code returns fallback. Expected: use raw text as response with `intent="unknown"`.
- **Empty provider result**: Provider returns `""` → current code accepts it as valid. Expected: treat as failure, try next provider.
- **Whitespace provider result**: Provider returns `"   \n  "` → current code accepts it. Expected: treat as failure.
- **Node overwrite**: `memory_save_node` returns `{"response": "memory saved"}` → overwrites LLM response in state. Expected: node returns `{}`, LLM response preserved.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Clean, valid JSON from the LLM must continue to be parsed directly via `json.loads()` on the first strategy attempt
- When all providers genuinely fail (network errors, timeouts, server errors), the system must continue to return `HEBREW_FALLBACK` as the final safety net
- Valid Hebrew text responses from the LLM must never be discarded just because they are not JSON or match a fallback-like pattern
- `routing_policy.py` must not be modified — provider ordering is unchanged
- `bedrock_client.py` must not be modified — Bedrock communication is unchanged
- All 150 existing tests must continue to pass without modification
- Memory extraction and conversation saving failures must continue to be logged and silently swallowed, never affecting the user-facing response

**Scope:**
All inputs where the LLM returns clean JSON, all genuine provider failures, and all non-LLM interactions (task CRUD, document handling, permission checks) are completely unaffected by this fix.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **No JSON Healing in `unified_handler.py`**: The `handle_with_llm()` function calls `json.loads(raw)` directly with no preprocessing. Any non-strict-JSON wrapper (markdown fences, prefix text, embedded JSON) causes immediate failure and fallback. The `except (json.JSONDecodeError, ...)` block discards the raw text entirely instead of using it as a response.

2. **No Raw-Text Fallback**: When JSON healing fails but the raw string contains meaningful content (e.g., a Hebrew sentence), the code returns `HEBREW_FALLBACK_MSG` instead of using the raw text as the response with `intent="unknown"`.

3. **Weak Validation in `model_dispatch.py`**: The dispatcher only checks `result != HEBREW_FALLBACK`. Empty strings, whitespace-only strings, and very short strings (e.g., `"."`) pass this check and are treated as valid responses, preventing fallback to the next provider.

4. **State Overwrite in Workflow Nodes**: `memory_save_node` and `conversation_save_node` return `{}` today, but there is no guard preventing them from returning a `"response"` key. If any future change or exception path causes them to return `{"response": ...}`, LangGraph's state merge will overwrite the real LLM response.

5. **No `response_format` in OpenRouter Payloads**: The `openrouter_client.py` payload does not include `response_format: {"type": "json_object"}`, so models that support structured output still return free-form text, increasing the likelihood of non-JSON responses.

6. **No JSON Hint in Unified Prompt**: The `UNIFIED_CLASSIFY_AND_RESPOND` prompt says "return JSON only" in Hebrew but does not use a strong, explicit JSON-only instruction that models reliably follow.

## Correctness Properties

Property 1: Bug Condition — JSON Healing Extracts Valid Content

_For any_ raw LLM output that contains valid JSON wrapped in markdown fences, prefixed with explanatory text, or embedded within other text, the `_heal_json()` function SHALL extract and return the parsed JSON dict using progressive strategies (direct parse → strip markdown → regex extraction → first-brace-to-last-brace).

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Bug Condition — Raw Text Fallback Preserves Content

_For any_ raw LLM output that contains no extractable JSON but is non-empty meaningful text, `handle_with_llm()` SHALL return the raw text as the response with `intent="unknown"` instead of returning the Hebrew fallback message.

**Validates: Requirements 2.4**

Property 3: Bug Condition — Dispatcher Rejects Invalid Responses

_For any_ provider result that is empty, whitespace-only, or shorter than a minimum viable length, `_is_valid_response()` SHALL return `False` and the dispatcher SHALL fall back to the next provider.

**Validates: Requirements 2.6**

Property 4: Bug Condition — Workflow Nodes Never Overwrite Response

_For any_ execution of `memory_save_node` or `conversation_save_node`, the returned dict SHALL NOT contain a `"response"` key, ensuring the LLM response in workflow state is never overwritten.

**Validates: Requirements 2.5**

Property 5: Preservation — Clean JSON Parsing Unchanged

_For any_ raw LLM output that is already valid strict JSON, the system SHALL parse it on the first `_heal_json` strategy (direct `json.loads`) and return the correct intent, response, and task_data, producing the same result as the original code.

**Validates: Requirements 3.1, 3.3**

Property 6: Preservation — Genuine Failures Still Return Fallback

_For any_ scenario where all providers genuinely fail (network errors, timeouts, server errors), the system SHALL continue to return `HEBREW_FALLBACK` as the final safety net, preserving existing failure behavior.

**Validates: Requirements 3.2, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `fortress/src/services/unified_handler.py`

**Function**: New `_heal_json(raw: str) -> dict | None`

**Specific Changes**:
1. **Add `_heal_json()` function** with 4 ordered strategies:
   - Strategy 1: Direct `json.loads(raw)` — handles clean JSON
   - Strategy 2: Strip markdown code fences (```` ```json ... ``` ````) and parse
   - Strategy 3: Regex extraction — find `{...}` pattern with `re.search(r'\{.*\}', raw, re.DOTALL)`
   - Strategy 4: First-brace-to-last-brace — `raw[raw.index('{'):raw.rindex('}')+1]` and parse
   - Return `None` if all strategies fail
   - Log which strategy succeeded at DEBUG level

2. **Update `handle_with_llm()`** to call `_heal_json(raw)` instead of `json.loads(raw)`:
   - If `_heal_json` returns a dict → extract intent, response, task_data as before
   - If `_heal_json` returns `None` AND `raw.strip()` is non-empty → return `("unknown", raw.strip(), None)` (raw text fallback)
   - If `_heal_json` returns `None` AND `raw.strip()` is empty → return `("unknown", HEBREW_FALLBACK_MSG, None)`
   - Log the decision path (healed, raw-fallback, or empty-fallback)

**File**: `fortress/src/services/model_dispatch.py`

**Function**: New `_is_valid_response(result: str) -> bool`

**Specific Changes**:
3. **Add `_is_valid_response()` function** that returns `False` for:
   - `result` equals `HEBREW_FALLBACK`
   - `result.strip()` is empty
   - `len(result.strip()) < 2` (too short to be meaningful)
   - Log invalid responses at WARNING level
4. **Replace** `if result != HEBREW_FALLBACK:` with `if _is_valid_response(result):` in the dispatch loop

**File**: `fortress/src/services/workflow_engine.py`

**Functions**: `memory_save_node`, `conversation_save_node`

**Specific Changes**:
5. **Guard return values**: Ensure both nodes always return `{}` — add explicit filtering to strip any `"response"` key from the return dict before returning. Add a defensive check: if the return dict contains `"response"`, log a warning and remove it.

**File**: `fortress/src/services/openrouter_client.py`

**Function**: `generate()`

**Specific Changes**:
6. **Add `response_format`** to the payload: `"response_format": {"type": "json_object"}`. If the API returns an error indicating the model doesn't support it, retry once without `response_format`.

**File**: `fortress/src/prompts/system_prompts.py`

**Constant**: `UNIFIED_CLASSIFY_AND_RESPOND`

**Specific Changes**:
7. **Add JSON-only hint**: Append a stronger instruction line to the prompt, e.g., `"חשוב מאוד: החזר JSON תקין בלבד. אל תעטוף ב-markdown, אל תוסיף הסברים לפני או אחרי ה-JSON."` (Very important: return valid JSON only. Do not wrap in markdown, do not add explanations before or after the JSON.)

**All modified files**:
8. **Add structured logging** at every decision point: JSON healing strategy attempts/results, raw-text fallback decisions, dispatcher validation rejections, node return filtering, OpenRouter `response_format` retry.

## Testing Strategy

### Validation Approach

The testing strategy uses unit tests only (no property-based tests per user constraint). Tests first surface counterexamples on unfixed code, then verify the fix works correctly and preserves existing behavior. All 150 existing tests must continue to pass.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Write unit tests that feed markdown-wrapped, prefixed, embedded, and plain-text LLM outputs to `handle_with_llm()` and assert the current code returns fallback (confirming the bug). Run on UNFIXED code to observe failures.

**Test Cases**:
1. **Markdown Fence Test**: Feed `` ```json\n{"intent":"greeting","response":"שלום!"}\n``` `` → will return fallback on unfixed code
2. **Prefixed Text Test**: Feed `"Here is: {"intent":"greeting","response":"שלום!"}"` → will return fallback on unfixed code
3. **Embedded JSON Test**: Feed `"text before {"intent":"unknown","response":"test"} text after"` → will return fallback on unfixed code
4. **Plain Hebrew Text Test**: Feed `"שלום, מה שלומך?"` → will return fallback on unfixed code instead of using raw text
5. **Empty String Dispatch Test**: Feed `""` as provider result → will pass validation on unfixed code

**Expected Counterexamples**:
- `handle_with_llm` returns `HEBREW_FALLBACK_MSG` for all non-strict-JSON inputs
- `model_dispatch` accepts empty strings as valid responses

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handle_with_llm_fixed(input)
  ASSERT result.response != HEBREW_FALLBACK_MSG OR input.raw is genuinely empty
  ASSERT result.intent is valid
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handle_with_llm_fixed(input) == handle_with_llm_original(input)
END FOR
```

**Test Plan**: Verify that clean JSON parsing, genuine failure fallback, valid Hebrew responses, and all existing test assertions continue to work identically after the fix.

**Test Cases**:
1. **Clean JSON Preservation**: Verify `{"intent":"greeting","response":"שלום!"}` still parses correctly
2. **Genuine Failure Preservation**: Verify all-providers-fail still returns `HEBREW_FALLBACK`
3. **Hebrew Text Preservation**: Verify valid Hebrew text from LLM is never discarded just because it's not JSON
4. **Existing Test Suite**: All 150 tests pass without modification

### Unit Tests

**New file: `fortress/tests/test_json_healing.py`**
- `test_heal_json_clean_json` — direct parse succeeds on first strategy
- `test_heal_json_markdown_fences` — strips `` ```json ... ``` `` and parses
- `test_heal_json_markdown_fences_no_lang` — strips `` ``` ... ``` `` without language tag
- `test_heal_json_prefixed_text` — regex extracts JSON after prefix text
- `test_heal_json_embedded_json` — first-brace-to-last-brace extracts embedded JSON
- `test_heal_json_plain_text_returns_none` — returns `None` for non-JSON text
- `test_heal_json_empty_string_returns_none` — returns `None` for empty input
- `test_heal_json_nested_braces` — correctly handles nested `{}` in JSON
- `test_heal_json_hebrew_text_returns_none` — returns `None` for Hebrew-only text (not discarded, used as raw fallback by caller)

**Updated file: `fortress/tests/test_unified_handler.py`**
- `test_markdown_wrapped_json_healed` — markdown-fenced JSON returns correct intent/response
- `test_prefixed_json_healed` — prefixed JSON returns correct intent/response
- `test_embedded_json_healed` — embedded JSON returns correct intent/response
- `test_plain_text_raw_fallback` — plain text returns `("unknown", raw_text, None)` not fallback
- `test_hebrew_plain_text_preserved_as_response` — Hebrew text used as response, not discarded
- `test_empty_raw_returns_fallback` — empty LLM output still returns `HEBREW_FALLBACK_MSG`
- `test_logging_on_heal_success` — logs which healing strategy succeeded
- `test_logging_on_raw_fallback` — logs raw-text fallback decision

**Updated file: `fortress/tests/test_model_dispatch.py`**
- `test_empty_string_treated_as_failure` — `""` triggers fallback to next provider
- `test_whitespace_only_treated_as_failure` — `"   "` triggers fallback
- `test_too_short_treated_as_failure` — `"."` triggers fallback
- `test_valid_hebrew_not_rejected` — valid Hebrew response accepted (not confused with fallback)

**Updated file: `fortress/tests/test_workflow_engine.py`**
- `test_memory_save_node_never_returns_response_key` — assert `"response"` not in return dict
- `test_conversation_save_node_never_returns_response_key` — assert `"response"` not in return dict
- `test_memory_save_failure_does_not_affect_response` — exception in memory save preserves LLM response
- `test_conversation_save_failure_does_not_affect_response` — exception in conversation save preserves LLM response

### Integration Tests

- Full workflow run with markdown-wrapped LLM output verifies end-to-end healing
- Full workflow run with plain Hebrew text verifies raw-text fallback through the entire pipeline
- Full workflow run with empty provider result verifies dispatcher fallback chain works correctly
