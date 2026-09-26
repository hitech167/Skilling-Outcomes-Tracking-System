"""
External employment signals (admin only).

POST /api/employment-signals/import  -> upload a CSV of placements from an outside source
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from database.connection import get_db
from services import employment_signal_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/employment-signals", tags=["Employment signals"])

MAX_FILE_BYTES = 2_000_000


@router.post(
    "/import",
    summary="Import employment signals from an outside source (CSV)",
)
async def import_employment_signals(
    file: UploadFile = File(..., description="CSV: trainee_id | phone | external_id (TYPE:VALUE), employer_name, start_date (YYYY-MM-DD), optional job_role, monthly_salary, reference"),
    source: str = Form(..., min_length=2, max_length=60, description="Where the data comes from, e.g. EPFO, NCS portal"),
    dry_run: bool = Form(False, description="Check the file and report, without saving anything"),
    db: Session = Depends(get_db),
):
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is larger than 2 MB.")
    try:
        rows = employment_signal_service.parse_csv(raw)
    except employment_signal_service.SignalFileError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    summary = employment_signal_service.import_signals(db, rows, source.strip(), dry_run)
    logger.info(
        "Employment signal import (%s%s): %s rows, %s created",
        source, ", dry run" if dry_run else "", summary["rows"], summary["created"],
    )
    return summary
