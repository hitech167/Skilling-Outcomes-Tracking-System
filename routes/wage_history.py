"""
Wage history routes — Phase 4.

POST /api/wage-history                          -> add a wage record
GET  /api/wage-history                          -> list wage records across trainees, newest first
GET  /api/employment/{employment_id}/wage-history -> list wage history, oldest first

The original salary on employment_records is never overwritten; every
new figure is a new row here, so full progression is reconstructable
later without any ML classification (per PROJECT_LOG's Phase 4 spec).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import EmploymentRecord, Trainee, WageHistory
from routes._shared import get_employment_or_404, get_trainee_or_404
from schemas.wage_history import (
    ALLOWED_WAGE_SOURCES,
    ALLOWED_WAGE_VERIFICATION_STATUSES,
    WageHistoryCreate,
    WageHistoryListResponse,
    WageHistoryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Wage History"])


def generate_wage_record_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('wage_history_id_seq')")).scalar()
    return f"WAGE{next_number:06d}"


def to_response(
    record: WageHistory, employment_public_id: str, trainee_public_id: str
) -> WageHistoryResponse:
    return WageHistoryResponse(
        wage_record_id=record.wage_record_id,
        employment_id=employment_public_id,
        trainee_id=trainee_public_id,
        salary=float(record.salary),
        salary_period=record.salary_period,
        effective_date=record.effective_date,
        source=record.source,
        verification_status=record.verification_status,
        notes=record.notes,
    )


@router.post(
    "/api/wage-history",
    response_model=WageHistoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a wage record for an employment",
)
def create_wage_record(payload: WageHistoryCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    employment = get_employment_or_404(payload.employment_id, db)

    if employment.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Employment record {employment.employment_id} does not belong "
                f"to trainee {trainee.trainee_id}"
            ),
        )

    try:
        record = WageHistory(
            wage_record_id=generate_wage_record_id(db),
            employment_pk_id=employment.id,
            trainee_pk_id=trainee.id,
            salary=payload.salary,
            salary_period=payload.salary_period,
            effective_date=payload.effective_date,
            source=payload.source,
            verification_status=payload.verification_status,
            notes=payload.notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating a wage record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Created wage record %s for employment %s",
        record.wage_record_id,
        employment.employment_id,
    )

    return to_response(record, employment.employment_id, trainee.trainee_id)


@router.get(
    "/api/wage-history",
    response_model=list[WageHistoryResponse],
    summary="List wage records across trainees, newest effective date first",
)
def list_all_wage_history(
    source: Optional[str] = Query(None, description="Trainee | Employer | Document | Admin"),
    verification_status: Optional[str] = Query(None, description="Unverified | Verified"),
    trainee_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    query = (
        db.query(WageHistory, EmploymentRecord, Trainee)
        .join(EmploymentRecord, EmploymentRecord.id == WageHistory.employment_pk_id)
        .join(Trainee, Trainee.id == WageHistory.trainee_pk_id)
    )
    if source:
        cleaned = source.strip().capitalize()
        if cleaned not in ALLOWED_WAGE_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"source must be one of: {', '.join(sorted(ALLOWED_WAGE_SOURCES))}",
            )
        query = query.filter(WageHistory.source == cleaned)
    if verification_status:
        cleaned = verification_status.strip().capitalize()
        if cleaned not in ALLOWED_WAGE_VERIFICATION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "verification_status must be one of: "
                    f"{', '.join(sorted(ALLOWED_WAGE_VERIFICATION_STATUSES))}"
                ),
            )
        query = query.filter(WageHistory.verification_status == cleaned)
    if trainee_id:
        query = query.filter(Trainee.trainee_id == trainee_id.strip().upper())

    rows = (
        query.order_by(WageHistory.effective_date.desc(), WageHistory.id.desc())
        .limit(limit)
        .all()
    )
    return [
        to_response(record, employment.employment_id, trainee.trainee_id).model_copy(
            update={
                "trainee_name": trainee.full_name,
                "company_name": employment.company_name,
                "job_role": employment.job_role,
            }
        )
        for record, employment, trainee in rows
    ]


@router.get(
    "/api/employment/{employment_id}/wage-history",
    response_model=WageHistoryListResponse,
    summary="List wage history for an employment, oldest first",
)
def list_wage_history(employment_id: str, db: Session = Depends(get_db)):
    employment = get_employment_or_404(employment_id, db)
    trainee = db.query(Trainee).filter(Trainee.id == employment.trainee_pk_id).first()

    records = (
        db.query(WageHistory)
        .filter(WageHistory.employment_pk_id == employment.id)
        .order_by(WageHistory.effective_date.asc(), WageHistory.id.asc())
        .all()
    )

    return WageHistoryListResponse(
        employment_id=employment.employment_id,
        wage_history=[
            to_response(record, employment.employment_id, trainee.trainee_id)
            for record in records
        ],
    )
