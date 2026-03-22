"""Fortress 2.0 application entry point."""

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.config import LOG_LEVEL, SCHEDULER_HOUR
from src.database import SessionLocal, test_connection
from src.routers import dashboard, health, scheduler, whatsapp
from src.services.scheduler import run_daily_schedule

APP_START_TIME: float = time.time()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def _scheduled_run() -> None:
    """Create a DB session and run the daily schedule."""
    db = SessionLocal()
    try:
        await run_daily_schedule(db)
    except Exception:
        logger.exception("Scheduled run failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    if test_connection():
        logger.info("Database connection OK")
    else:
        logger.warning("Database connection FAILED — running without DB")

    _scheduler.add_job(
        _scheduled_run,
        CronTrigger(hour=SCHEDULER_HOUR, minute=0),
        id="daily_recurring",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started — daily job at %02d:00", SCHEDULER_HOUR)

    yield

    _scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down")


app = FastAPI(title="Fortress", version="2.0.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(whatsapp.router)
app.include_router(scheduler.router)
app.include_router(dashboard.router)

app.mount("/static", StaticFiles(directory="src/static"), name="static")

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000)
