# Bugfix Requirements Document

## Introduction

The Fortress app's `/health` endpoint reports `"bedrock": "disconnected"` even though AWS Bedrock is reachable and functional from inside the Docker container. The root cause is multi-faceted: the `BedrockClient` forces a named AWS profile (`fortress`) for credential resolution instead of using the default credential chain, the `is_available()` method creates a separate session with the same broken profile logic and uses invalid API parameters, the configured model IDs don't match what's actually enabled in the account, and the `docker-compose.yml` doesn't pass through ENV-based AWS credentials. Together, these issues cause every Bedrock connectivity check to fail silently and report "disconnected."

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN AWS credentials are provided via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) and no `~/.aws/credentials` profile named "fortress" exists THEN the system fails to authenticate with AWS because `BedrockClient.__init__` forces `boto3.Session(profile_name="fortress")` which ignores ENV-based credentials

1.2 WHEN `is_available()` is called THEN the system creates a new `boto3.Session(profile_name=self.profile)` with the same broken profile logic, and calls `bedrock.list_foundation_models(byProvider="Anthropic", maxResults=1)` where `maxResults` is not a valid parameter for that API, causing the check to fail

1.3 WHEN the configured model ID is `anthropic.claude-3-5-haiku-20241022-v1:0` but only `anthropic.claude-3-haiku-20240307-v1:0` is enabled in the AWS account THEN the system attempts to invoke a model that is not available, causing generation requests to fail

1.4 WHEN `generate()` is called THEN the system sends `anthropic_version: "bedrock-2023-05-31"` instead of the current `"bedrock-2023-10-16"`, which may cause request failures or unexpected behavior

1.5 WHEN the Docker container starts THEN the system does not receive `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` environment variables from `docker-compose.yml`, and instead receives `AWS_PROFILE=fortress` and a mounted `~/.aws` directory that may not contain the expected profile

1.6 WHEN a developer references `.env.example` to configure the app THEN the system encourages profile-based auth (`AWS_PROFILE=fortress`) without documenting ENV-based credential variables, leading to misconfiguration

### Expected Behavior (Correct)

2.1 WHEN AWS credentials are provided via environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) THEN the system SHALL use the default boto3 credential chain (which checks ENV vars first, then instance profiles, then config files) so that ENV-based credentials are resolved automatically

2.2 WHEN `is_available()` is called THEN the system SHALL reuse the existing boto3 session and bedrock-runtime client, perform a lightweight API call with valid parameters only, and return `(True, "haiku")` when Bedrock is reachable

2.3 WHEN the model ID is configurable via environment variable THEN the system SHALL default to a model ID that matches commonly enabled models, and the `.env.example` SHALL document the correct default model IDs

2.4 WHEN `generate()` is called THEN the system SHALL use `anthropic_version: "bedrock-2023-10-16"` in the request payload

2.5 WHEN the Docker container starts THEN the system SHALL receive `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` environment variables from `docker-compose.yml`, and SHALL NOT depend on a mounted `~/.aws` directory or a named AWS profile

2.6 WHEN a developer references `.env.example` THEN the system SHALL document `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` as the primary credential mechanism, and SHALL NOT include `AWS_PROFILE`

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `generate()` is called with a valid prompt and Bedrock is reachable THEN the system SHALL CONTINUE TO return the model's response text

3.2 WHEN `generate()` fails due to a Bedrock API error THEN the system SHALL CONTINUE TO return the Hebrew fallback message (`HEBREW_FALLBACK`)

3.3 WHEN `is_available()` determines Bedrock is unreachable THEN the system SHALL CONTINUE TO return `(False, None)`

3.4 WHEN the `/health` endpoint is called THEN the system SHALL CONTINUE TO return a JSON response with `status`, `service`, `version`, `database`, `ollama`, `ollama_model`, `bedrock`, and `bedrock_model` fields

3.5 WHEN Bedrock is connected THEN the `/health` endpoint SHALL CONTINUE TO report `"bedrock": "connected"` and a model name

3.6 WHEN Bedrock is disconnected THEN the `/health` endpoint SHALL CONTINUE TO report `"bedrock": "disconnected"` and `"bedrock_model": "not available"`

3.7 WHEN all 91 existing tests are run THEN the system SHALL CONTINUE TO pass all tests without modification to test logic (tests may need mock updates to match new constructor signatures)
