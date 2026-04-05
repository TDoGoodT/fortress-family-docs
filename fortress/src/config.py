"""Fortress 2.0 configuration — loads environment variables with sensible defaults."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://fortress:fortress_dev@localhost:5432/fortress",
)

STORAGE_PATH: str = os.getenv("STORAGE_PATH", "/data/documents")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

WAHA_API_URL: str = os.getenv("WAHA_API_URL", "http://localhost:3000")
WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")

ADMIN_PHONE: str = os.getenv("ADMIN_PHONE", "972542364393")

OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# AWS Bedrock — OpenAI-compatible API
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN: str = os.getenv("AWS_SESSION_TOKEN", "")

BEDROCK_API_KEY: str = os.getenv("BEDROCK_API_KEY", "")
BEDROCK_API_BASE_URL: str = os.getenv("BEDROCK_API_BASE_URL", "https://bedrock.us-east-1.amazonaws.com/v1")

# Model tiers: cheap→expensive
BEDROCK_MICRO_MODEL: str = os.getenv("BEDROCK_MICRO_MODEL", "amazon.nova-micro-v1:0")   # intent/classify
BEDROCK_LITE_MODEL: str = os.getenv("BEDROCK_LITE_MODEL", "amazon.nova-lite-v1:0")      # chat/Hebrew
BEDROCK_HAIKU_MODEL: str = os.getenv("BEDROCK_HAIKU_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")   # complex Hebrew
BEDROCK_SONNET_MODEL: str = os.getenv("BEDROCK_SONNET_MODEL", "us.anthropic.claude-sonnet-4-5-20251001-v1:0") # reasoning/code

# Scheduler
SCHEDULER_HOUR: int = int(os.getenv("SCHEDULER_HOUR", "7"))

# Phone identity
SYSTEM_PHONE: str = os.getenv("SYSTEM_PHONE", "")

# Deploy Listener
DEPLOY_SECRET: str = os.getenv("DEPLOY_SECRET", "")
DEPLOY_LISTENER_URL: str = os.getenv("DEPLOY_LISTENER_URL", "http://host.docker.internal:9111")

# Editable personality file
SOUL_MD_PATH: str = os.getenv("SOUL_MD_PATH", "config/SOUL.md")

# Agent loop (LLM-based routing)
AGENT_ENABLED: bool = os.getenv("AGENT_ENABLED", "true").lower() == "true"
AGENT_MAX_TOOL_ITERATIONS: int = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "5"))
AGENT_MODEL_TIER: str = os.getenv("AGENT_MODEL_TIER", "haiku")
AGENT_HISTORY_DEPTH: int = int(os.getenv("AGENT_HISTORY_DEPTH", "10"))
