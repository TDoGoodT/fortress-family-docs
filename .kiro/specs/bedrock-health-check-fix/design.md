# Bedrock Health Check Fix — Bugfix Design

## Overview

The `BedrockClient` class fails to connect to AWS Bedrock due to six compounding issues: forced profile-based auth ignoring ENV credentials, a broken `is_available()` method with invalid API params, wrong model IDs, outdated anthropic_version, missing Docker ENV passthrough, and misleading `.env.example`. The fix rewrites credential resolution to use the default boto3 chain, fixes the health check method, corrects model defaults, and updates Docker/env configuration.

## Glossary

- **Bug_Condition (C)**: The set of conditions where BedrockClient fails to authenticate or perform API calls despite valid AWS credentials being available via environment variables
- **Property (P)**: BedrockClient authenticates via default credential chain, `is_available()` returns `(True, "haiku")` when Bedrock is reachable, `generate()` uses correct anthropic_version and model IDs
- **Preservation**: All 91 existing tests pass, `generate()` still returns responses or Hebrew fallback, `/health` endpoint response shape unchanged
- **BedrockClient**: The class in `fortress/src/services/bedrock_client.py` that wraps boto3 Bedrock API calls
- **Default credential chain**: boto3's built-in resolution order: ENV vars → instance profile → config files

## Bug Details

### Bug Condition

The bug manifests when AWS credentials are provided via environment variables but `BedrockClient` forces a named profile, or when `is_available()` uses invalid API parameters, or when model IDs don't match enabled models.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type BedrockClientCall
  OUTPUT: boolean

  profileForced := session uses explicit profile_name instead of default chain
  invalidParam := is_available() passes maxResults to list_foundation_models
  wrongModel := configured model ID not enabled in AWS account
  wrongVersion := anthropic_version != "bedrock-2023-10-16"
  noEnvPassthrough := Docker container missing AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY

  RETURN profileForced OR invalidParam OR wrongModel OR wrongVersion OR noEnvPassthrough
END FUNCTION
```

### Examples

- ENV has `AWS_ACCESS_KEY_ID=AKIA...` but `boto3.Session(profile_name="fortress")` ignores it → `NoCredentialsError`
- `is_available()` calls `list_foundation_models(byProvider="Anthropic", maxResults=1)` → `ParamValidationError` because `maxResults` is not a valid param
- `generate()` invokes `anthropic.claude-3-5-haiku-20241022-v1:0` but only `anthropic.claude-3-haiku-20240307-v1:0` is enabled → `AccessDeniedException`
- `generate()` sends `anthropic_version: "bedrock-2023-05-31"` → potential request failures
- Docker container has `AWS_PROFILE=fortress` but no `~/.aws/credentials` with that profile → auth failure

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `generate()` returns model response text on success, Hebrew fallback on any error
- `is_available()` returns `(False, None)` when Bedrock is unreachable
- `/health` endpoint returns JSON with all existing fields: `status`, `service`, `version`, `database`, `ollama`, `ollama_model`, `bedrock`, `bedrock_model`
- All 91 existing tests continue to pass
- `OllamaClient` behavior completely unaffected
- `health.py` router logic unchanged

**Scope:**
All code paths that do NOT involve BedrockClient credential resolution, model invocation, or Docker credential passthrough are unaffected. No changes to health.py, model_router.py, or any other service file.

## Hypothesized Root Cause

Based on code analysis, the confirmed root causes are:

1. **Forced profile-based auth**: `BedrockClient.__init__` calls `boto3.Session(profile_name=self.profile)` which skips ENV-based credentials entirely. Should use `boto3.Session()` with no profile to let the default chain resolve.

2. **Broken is_available()**: Creates a new session (same broken profile), creates a separate `bedrock` management client (not `bedrock-runtime`), and passes `maxResults=1` which is not a valid parameter for `list_foundation_models`. Should reuse the existing runtime client with a lightweight call.

3. **Wrong model ID default**: `BEDROCK_HAIKU_MODEL` defaults to `anthropic.claude-3-5-haiku-20241022-v1:0` but the account has `anthropic.claude-3-haiku-20240307-v1:0` enabled.

4. **Outdated anthropic_version**: `generate()` uses `"bedrock-2023-05-31"` instead of `"bedrock-2023-10-16"`.

5. **Docker ENV gap**: `docker-compose.yml` passes `AWS_PROFILE` and mounts `~/.aws` instead of passing `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

6. **Misleading .env.example**: Documents `AWS_PROFILE=fortress` without mentioning ENV-based credentials.

## Correctness Properties

Property 1: Bug Condition — Credential Resolution and Health Check

_For any_ BedrockClient instantiation where AWS credentials are available via environment variables, the fixed client SHALL authenticate using the default boto3 credential chain (no forced profile), and `is_available()` SHALL return `(True, "haiku")` when Bedrock is reachable, using only valid API parameters.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Existing Behavior Unchanged

_For any_ call to `generate()` or `is_available()` where the bug condition does NOT hold (Bedrock is unreachable, invalid credentials, API errors), the fixed code SHALL produce the same result as the original code: `generate()` returns Hebrew fallback on error, `is_available()` returns `(False, None)` on failure, and the `/health` endpoint response shape is unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

**File**: `fortress/src/services/bedrock_client.py`

1. **Remove profile parameter**: Remove `profile` param from `__init__`, use `boto3.Session()` with no `profile_name` so default credential chain resolves ENV vars automatically
2. **Remove AWS_PROFILE import**: Stop importing `AWS_PROFILE` from config
3. **Fix is_available()**: Remove separate session/client creation. Use a lightweight `invoke_model` call or `list_foundation_models` with valid params only (no `maxResults`). Reuse existing session.
4. **Fix anthropic_version**: Change from `"bedrock-2023-05-31"` to `"bedrock-2023-10-16"` in `generate()`
5. **Add bedrock management client**: Create both `bedrock-runtime` (for invoke) and `bedrock` (for list_foundation_models) clients in `__init__`, or use runtime client for health check

**File**: `fortress/src/config.py`

1. **Remove AWS_PROFILE**: Delete the `AWS_PROFILE` config variable
2. **Fix BEDROCK_HAIKU_MODEL default**: Change from `anthropic.claude-3-5-haiku-20241022-v1:0` to `anthropic.claude-3-haiku-20240307-v1:0`

**File**: `fortress/docker-compose.yml`

1. **Add credential ENV vars**: Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` passthrough
2. **Remove AWS_PROFILE**: Remove the `AWS_PROFILE` env var
3. **Remove ~/.aws mount**: Remove the `~/.aws:/root/.aws:ro` volume mount

**File**: `fortress/.env.example`

1. **Add credential vars**: Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` placeholders
2. **Remove AWS_PROFILE**: Delete the `AWS_PROFILE=fortress` line

**File**: `fortress/requirements.txt`

1. **Relax boto3 pin**: Change `boto3==1.35.0` to `boto3>=1.35.0` to allow compatible updates

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause analysis.

**Test Plan**: Write tests that instantiate `BedrockClient` with mocked boto3 and verify the session creation behavior. Run on unfixed code to observe failures.

**Test Cases**:
1. **Profile Override Test**: Verify `BedrockClient()` creates session with `profile_name="fortress"` even when ENV credentials exist (will fail on unfixed code — confirms forced profile)
2. **Invalid Param Test**: Verify `is_available()` passes `maxResults=1` to `list_foundation_models` (will fail on unfixed code — confirms invalid param)
3. **Wrong Version Test**: Verify `generate()` sends `anthropic_version: "bedrock-2023-05-31"` (will fail on unfixed code — confirms wrong version)

**Expected Counterexamples**:
- `boto3.Session` called with `profile_name="fortress"` instead of no profile
- `list_foundation_models` called with invalid `maxResults` parameter

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := BedrockClient_fixed()
  ASSERT session created without profile_name
  ASSERT is_available() uses valid API params
  ASSERT generate() uses anthropic_version "bedrock-2023-10-16"
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT BedrockClient_fixed.generate(error_input) == HEBREW_FALLBACK
  ASSERT BedrockClient_fixed.is_available(unreachable) == (False, None)
  ASSERT health_endpoint response shape unchanged
END FOR
```

**Testing Approach**: Property-based testing with Hypothesis to generate random error scenarios and verify fallback behavior is preserved.

### Unit Tests

- Test `BedrockClient.__init__` creates session without profile_name
- Test `is_available()` returns `(True, "haiku")` with mocked successful API call
- Test `is_available()` returns `(False, None)` on any exception
- Test `generate()` uses correct anthropic_version in request body
- Test `generate()` returns Hebrew fallback on error

### Property-Based Tests

- Generate random exception types and verify `generate()` always returns Hebrew fallback
- Generate random exception types and verify `is_available()` always returns `(False, None)`

### Integration Tests

- Run all 91 existing tests to verify no regressions
- Verify `/health` endpoint response shape with mocked Bedrock client
