"""
Wage history routes — Phase 4.

POST /api/wage-history                          -> add a wage record
GET  /api/employment/{employment_id}/wage-history -> list wage history, oldest first

The original salary on employment_records is never overwritten; every
new figure is a new row here, so full progression is reconstructable
later without any ML classification (per PROJECT_LOG's Phase 4 spec).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import WageHistory
from routes._shared import get_employment_or_404, get_trainee_or_404
from schemas.wage_history import (
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
    "/api/employment/{employment_id}/wage-history",
    response_model=WageHistoryListResponse,
    summary="List wage history for an employment, oldest first",
)
def list_wage_history(employment_id: str, db: Session = Depends(get_db)):
    from database.models import Trainee

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
