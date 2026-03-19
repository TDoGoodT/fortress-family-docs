"""Fortress 2.0 application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import uvicorn
from fastapi import FastAPI

from src.config import LOG_LEVEL
from src.database import test_connection
from src.routers import health, whatsapp

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    if test_connection():
        logger.info("Database connection OK")
    else:
        logger.warning("Database connection FAILED — running without DB")
    yield


app = FastAPI(title="Fortress", version="2.0.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(whatsapp.router)

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000)
