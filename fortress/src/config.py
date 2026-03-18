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

ADMIN_PHONE: str = os.getenv("ADMIN_PHONE", "972542364393")
