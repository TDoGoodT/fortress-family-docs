"""Fortress 2.0 scheduler router — manual trigger and status endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.services.scheduler import get_status, run_daily_schedule

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/run")
async def trigger_run(db: Session = Depends(get_db)) -> dict:
    """Trigger a scheduler run. Returns tasks_created and notifications_sent."""
    result = await run_daily_schedule(db)
    return {
        "tasks_created": result.tasks_created,
        "notifications_sent": result.notifications_sent,
    }


@router.get("/status")
async def get_scheduler_status() -> dict:
    """Return last_run timestamp and tasks_created_last_run."""
    return get_status()
