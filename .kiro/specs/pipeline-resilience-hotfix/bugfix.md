# Bugfix Requirements Document

## Introduction

The Fortress LLM pipeline silently discards valid responses due to brittle JSON parsing, weak response validation, and state-overwrite bugs. When an LLM returns valid content wrapped in markdown fences, prefixed with explanatory text, or in any non-strict-JSON format, `unified_handler.py` throws a `JSONDecodeError` and returns a Hebrew fallback — even though the actual answer is present in the raw output. Separately, `memory_save_node` and `conversation_save_node` in the workflow engine can return a `"response"` key that overwrites the real LLM response in state. Finally, `model_dispatch.py` only checks `result != HEBREW_FALLBACK` and misses empty/whitespace-only strings, letting invalid responses propagate. These issues combine to make the pipeline unreliable: users receive generic fallback messages instead of the answers the LLM actually produced.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the LLM returns valid JSON wrapped in markdown code fences (e.g. ` ```json ... ``` `) THEN the system throws a `JSONDecodeError` and returns the Hebrew fallback message, discarding the valid response

1.2 WHEN the LLM returns valid JSON preceded by explanatory text (e.g. "Here is the response: {...}") THEN the system throws a `JSONDecodeError` and returns the Hebrew fallback message, discarding the valid response

1.3 WHEN the LLM returns a response that contains valid JSON embedded within other text THEN the system throws a `JSONDecodeError` and returns the Hebrew fallback message, discarding the valid response

1.4 WHEN the LLM returns non-JSON plain text with no extractable JSON structure THEN the system throws a `JSONDecodeError` and returns the Hebrew fallback message, discarding the raw text that could serve as a direct response

1.5 WHEN `memory_save_node` or `conversation_save_node` returns a dict containing a `"response"` key THEN the workflow engine overwrites the actual LLM response in state with the memory/conversation node's return value

1.6 WHEN a provider returns an empty string or whitespace-only string THEN `model_dispatch.py` treats it as a valid response (since it is not equal to `HEBREW_FALLBACK`) and does not fall back to the next provider

1.7 WHEN the OpenRouter payload is sent to a model that supports structured JSON output THEN the system does not request `response_format: {"type": "json_object"}`, increasing the likelihood of non-JSON responses

### Expected Behavior (Correct)

2.1 WHEN the LLM returns valid JSON wrapped in markdown code fences THEN the system SHALL strip the markdown fences and successfully parse the inner JSON, returning the extracted intent and response

2.2 WHEN the LLM returns valid JSON preceded by explanatory text THEN the system SHALL extract the JSON object using regex or brace-matching and successfully parse it, returning the extracted intent and response

2.3 WHEN the LLM returns a response containing valid JSON embedded within other text THEN the system SHALL extract the JSON object using progressive healing strategies (direct parse → strip markdown → regex extraction → first-brace-to-last-brace) and return the extracted intent and response

2.4 WHEN the LLM returns non-JSON plain text with no extractable JSON structure THEN the system SHALL use the raw text as the response with `intent="unknown"` instead of returning the Hebrew fallback message

2.5 WHEN `memory_save_node` or `conversation_save_node` execute THEN the system SHALL ensure these nodes NEVER return a dict containing a `"response"` key, preserving the original LLM response in workflow state

2.6 WHEN a provider returns an empty string, whitespace-only string, or a string shorter than a minimum viable length THEN `model_dispatch.py` SHALL treat it as a failure and fall back to the next provider in the chain

2.7 WHEN sending a payload to OpenRouter THEN the system SHALL include `response_format: {"type": "json_object"}` in the request, with a fallback retry without it if the model returns an error indicating it does not support structured output

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the LLM returns clean, valid JSON without any wrapping or extra text THEN the system SHALL CONTINUE TO parse it directly and return the correct intent, response, and task_data

3.2 WHEN all providers genuinely fail (network errors, timeouts, server errors) THEN the system SHALL CONTINUE TO return the Hebrew fallback message as the final safety net

3.3 WHEN a valid Hebrew text response is returned by the LLM THEN the system SHALL CONTINUE TO treat it as a valid response and never discard it solely because it matches the fallback string pattern or is not JSON

3.4 WHEN `routing_policy.py` determines the provider order for an intent THEN the system SHALL CONTINUE TO follow that routing order without modification (routing_policy.py must not be changed)

3.5 WHEN `bedrock_client.py` sends requests to AWS Bedrock THEN the system SHALL CONTINUE TO use the existing Bedrock client implementation without modification

3.6 WHEN the existing 150 tests are executed THEN the system SHALL CONTINUE TO pass all of them without regression

3.7 WHEN memory extraction or conversation saving fails THEN the system SHALL CONTINUE TO not affect the user-facing response (failures are logged but silently swallowed)
