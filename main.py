"""
SIH26135 — Longitudinal Skilling Outcomes System
Phase 1: Trainee Registration + Consent
Phase 2: Training Records
Phase 3: Outcome Tracking (outcomes, employment, self-employment,
         apprenticeship, non-placement, follow-ups)
Phase 4: Employer Verification + Wage Progression + Job Retention
Phase 5: Automated + Assisted Follow-up System (schedule generation,
         pending/upcoming/overdue, contact attempts, current-situation
         outcome updates, follow-up + admin summaries)
Phase 6: Analytics & Impact Measurement
Phase 7: Skill Gaps, Attrition & Improvement Insights
Phase 8: Final integration, validation and JWT access control

Run with:  uvicorn main:app --reload
Docs at:   http://127.0.0.1:8000/docs
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from database.connection import SessionLocal, get_db, init_db
from services.auth import require_admin, require_analytics_access
from routes import (
    analytics,
    apprenticeship,
    auth,
    employer_verifications,
    employment,
    employment_signals,
    employment_status,
    followup,
    followup_tracking,
    identity,
    insights,
    non_placement,
    outcomes,
    profile_links,
    self_employment,
    self_service,
    trainees,
    training_records,
    wage_history,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, ID sequences and additive columns on startup."""
    try:
        init_db()
        logger.info("Database ready.")
    except SQLAlchemyError:
        logger.exception(
            "Could not connect to the database. Check DATABASE_URL in your .env"
        )
        raise
    task = None
    interval_hours = _auto_dispatch_hours()
    if interval_hours:
        task = asyncio.create_task(_auto_dispatch_loop(interval_hours))
        logger.info("Automatic follow-up dispatch every %s hour(s).", interval_hours)
    yield
    if task:
        task.cancel()


def _auto_dispatch_hours() -> float:
    """FOLLOWUP_AUTO_DISPATCH_HOURS in .env; 0 / unset = off (use the admin endpoint)."""
    try:
        return max(0.0, float(os.getenv("FOLLOWUP_AUTO_DISPATCH_HOURS", "0")))
    except ValueError:
        return 0.0


async def _auto_dispatch_loop(interval_hours: float) -> None:
    from services.notification_service import dispatch_due_followups

    def run_once():
        db = SessionLocal()
        try:
            summary = dispatch_due_followups(db)
            logger.info(
                "Auto-dispatch: %s due, %s sent, %s queued, %s failed",
                summary["due_followups"], summary["sent"], summary["queued"], summary["failed"],
            )
        except Exception:
            db.rollback()
            logger.exception("Automatic follow-up dispatch failed")
        finally:
            db.close()

    while True:
        await asyncio.to_thread(run_once)
        await asyncio.sleep(interval_hours * 3600)


app = FastAPI(
    title="Skilling Outcomes Tracking System",
    description=(
        "Consent-based trainee registration, training records and outcome "
        "tracking for SIH26135.\n\n"
        "Phase 1: trainee registration + consent. "
        "Phase 2: training records (course, provider, assessment, certification). "
        "Phase 3: outcomes (employment, self-employment, apprenticeship, "
        "non-placement) and longitudinal follow-ups. "
        "Phase 4: employer verification, wage progression and job retention. "
        "Phase 5: automated follow-up scheduling, contact attempts and "
        "assisted follow-up management. "
        "Phase 6: read-only analytics and impact measurement. "
        "Phase 7: skill-gap, attrition and programme-improvement insights, "
        "built on top of Phase 6's analytics. "
        "Phase 8: final integration and SIH validation.\n\n"
        "**Authentication:** log in via `POST /api/auth/token` (or the "
        "Authorize button). `admin` can manage all records; `analyst` can "
        "read aggregated analytics and insights only."
    ),
    version="8.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- CORS ------------------------------------------------------------
# Browser frontends on another address need this. CORS_ORIGINS in .env is a
# comma-separated list of allowed origins; unset = common local dev servers.
# Auth is a bearer header, not cookies, so credentials are not allowed.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in (os.getenv("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)

# ---- Access control ------------------------------------------------
# Record-level routers carry personal data (phone, email, DOB, salary,
# employer contact, employment details) -> admin only.
# Aggregated analytics / insights carry no PII -> admin or analyst.
# Health checks, /docs, /api/auth/token and the signed self-report /
# employer-confirmation links stay public.
ADMIN_ONLY = [Depends(require_admin)]
ANALYTICS_ACCESS = [Depends(require_analytics_access)]

app.include_router(auth.router)
# Signed single-use links for trainees / employers — no login by design.
app.include_router(self_service.public_router)
app.include_router(profile_links.public_router)
app.include_router(identity.router, dependencies=ADMIN_ONLY)
app.include_router(self_service.admin_router, dependencies=ADMIN_ONLY)
app.include_router(trainees.router, dependencies=ADMIN_ONLY)
app.include_router(training_records.router, dependencies=ADMIN_ONLY)
app.include_router(outcomes.router, dependencies=ADMIN_ONLY)
app.include_router(employment.router, dependencies=ADMIN_ONLY)
app.include_router(employment_signals.router, dependencies=ADMIN_ONLY)
app.include_router(self_employment.router, dependencies=ADMIN_ONLY)
app.include_router(apprenticeship.router, dependencies=ADMIN_ONLY)
app.include_router(non_placement.router, dependencies=ADMIN_ONLY)
# followup_tracking's fixed-path routes (pending/upcoming/overdue/summary)
# must be registered BEFORE followup's GET /api/followups/{followup_id},
# otherwise FastAPI would match e.g. "pending" as a followup_id.
app.include_router(followup_tracking.router, dependencies=ADMIN_ONLY)
app.include_router(followup.router, dependencies=ADMIN_ONLY)
app.include_router(employer_verifications.router, dependencies=ADMIN_ONLY)
app.include_router(wage_history.router, dependencies=ADMIN_ONLY)
app.include_router(employment_status.router, dependencies=ADMIN_ONLY)
app.include_router(analytics.router, dependencies=ANALYTICS_ACCESS)
app.include_router(insights.router, dependencies=ANALYTICS_ACCESS)


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request, exc: SQLAlchemyError):
    """
    Catch-all for database problems so raw SQL errors are never sent to the
    API caller. The full traceback goes to the server log instead.
    """
    logger.exception("Unhandled database error at %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={"success": False, "message": "Database is unavailable right now."},
    )


@app.get("/", tags=["Health"], summary="Health check")
def health_check():
    return {"status": "ok", "phase": 8, "docs": "/docs"}


@app.get("/api/system/health", tags=["Health"], summary="System & database health check")
def system_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    return {"status": "ok", "database": db_status}

