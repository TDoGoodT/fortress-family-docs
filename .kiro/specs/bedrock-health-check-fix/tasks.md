# Bedrock Health Check Fix — Tasks

## Task List

- [x] 1. Fix BedrockClient credential resolution and health check
  - [x] 1.1 Remove `AWS_PROFILE` from `fortress/src/config.py` and fix `BEDROCK_HAIKU_MODEL` default to `anthropic.claude-3-haiku-20240307-v1:0`
  - [x] 1.2 Rewrite `BedrockClient.__init__` in `fortress/src/services/bedrock_client.py`: remove `profile` param, use `boto3.Session()` without `profile_name`, create both `bedrock-runtime` and `bedrock` clients
  - [x] 1.3 Fix `is_available()`: use the management client created in `__init__`, call `list_foundation_models(byProvider="Anthropic")` without invalid `maxResults` param, return `(True, "haiku")` on success
  - [x] 1.4 Fix `generate()`: change `anthropic_version` from `"bedrock-2023-05-31"` to `"bedrock-2023-10-16"`
- [x] 2. Fix Docker and environment configuration
  - [x] 2.1 Update `fortress/docker-compose.yml`: add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` env passthrough, remove `AWS_PROFILE`, remove `~/.aws:/root/.aws:ro` volume mount
  - [x] 2.2 Update `fortress/.env.example`: add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` placeholders, remove `AWS_PROFILE=fortress`
  - [x] 2.3 Relax `boto3` pin in `fortress/requirements.txt` from `==1.35.0` to `>=1.35.0`
- [x] 3. Verify existing tests pass
  - [x] 3.1 Run all existing tests to confirm no regressions (91 tests should pass)
