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

WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")

ADMIN_PHONE: str = os.getenv("ADMIN_PHONE", "972542364393")

OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# AWS Bedrock
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_HAIKU_MODEL: str = os.getenv("BEDROCK_HAIKU_MODEL", "anthropic.claude-3-haiku-20240307-v1:0")
BEDROCK_HAIKU_PROFILE_ARN: str = os.getenv("BEDROCK_HAIKU_PROFILE_ARN", "")
BEDROCK_SONNET_MODEL: str = os.getenv("BEDROCK_SONNET_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")

# OpenRouter
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct:free")
OPENROUTER_FALLBACK_MODEL: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "google/gemma-2-9b-it:free")

# Phone identity
SYSTEM_PHONE: str = os.getenv("SYSTEM_PHONE", "")
