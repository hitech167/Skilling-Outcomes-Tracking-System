"""
Employment status (job retention) routes — Phase 4.

POST /api/employment-status                              -> record a status change
GET  /api/employment/{employment_id}/status-history        -> list status history, oldest first
GET  /api/employment/{employment_id}/summary                -> combined employment view
GET  /api/trainees/{trainee_id}/employment-history          -> all employments for a trainee
GET  /api/trainees/{trainee_id}/wage-progression            -> every job with its summary + wage records

Old status rows are never deleted — the sequence over time is the
retention timeline (Active -> Active -> Left Job, etc).
"""

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import (
    EmployerVerification,
    EmploymentRecord,
    EmploymentStatusHistory,
    Trainee,
    WageHistory,
)
from routes._shared import get_employment_or_404, get_trainee_or_404
from schemas.employment_status import (
    EmploymentStatusCreate,
    EmploymentStatusHistoryListResponse,
    EmploymentStatusResponse,
)
from routes.wage_history import to_response as wage_to_response
from schemas.employment_summary import (
    EmploymentHistoryItem,
    EmploymentSummaryResponse,
    EmploymentWageProgression,
    SalarySummary,
    TraineeEmploymentHistoryResponse,
    TraineeWageProgressionResponse,
    VerificationSummary,
)

from services.analytics_service import wage_progression_for

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Employment Status & Retention"])


def generate_status_record_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('employment_status_id_seq')")).scalar()
    return f"EST{next_number:06d}"


def to_response(
    record: EmploymentStatusHistory, employment_public_id: str, trainee_public_id: str
) -> EmploymentStatusResponse:
    return EmploymentStatusResponse(
        status_record_id=record.status_record_id,
        employment_id=employment_public_id,
        trainee_id=trainee_public_id,
        employment_status=record.employment_status,
        status_date=record.status_date,
        reason=record.reason,
        notes=record.notes,
    )


def _round(value):
    return None if value is None else round(value, 2)


def _current_statuses(db: Session, employments: list) -> dict:
    """
    employment pk -> its "current" status: the most recent status-history
    row if one exists, otherwise the status already stored on the Phase 3
    employment_records row (so employments predating Phase 4 still work).
    One query for all the given employments, not one per employment.
    """
    ids = [e.id for e in employments]
    current = {e.id: e.employment_status for e in employments}
    if ids:
        rows = (
            db.query(EmploymentStatusHistory.employment_pk_id, EmploymentStatusHistory.employment_status)
            .filter(EmploymentStatusHistory.employment_pk_id.in_(ids))
            .order_by(EmploymentStatusHistory.status_date.asc(), EmploymentStatusHistory.id.asc())
        )
        for employment_pk_id, status_value in rows:
            current[employment_pk_id] = status_value  # ascending, so the last one wins
    return current


@router.post(
    "/api/employment-status",
    response_model=EmploymentStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an employment status change",
)
def create_employment_status(payload: EmploymentStatusCreate, db: Session = Depends(get_db)):
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
        record = EmploymentStatusHistory(
            status_record_id=generate_status_record_id(db),
            employment_pk_id=employment.id,
            trainee_pk_id=trainee.id,
            employment_status=payload.employment_status,
            status_date=payload.status_date,
            reason=payload.reason,
            notes=payload.notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating an employment status record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Recorded employment status %s -> %s for employment %s",
        record.status_record_id,
        record.employment_status,
        employment.employment_id,
    )

    return to_response(record, employment.employment_id, trainee.trainee_id)


@router.get(
    "/api/employment/{employment_id}/status-history",
    response_model=EmploymentStatusHistoryListResponse,
    summary="List employment status history, oldest first",
)
def list_status_history(employment_id: str, db: Session = Depends(get_db)):
    employment = get_employment_or_404(employment_id, db)
    trainee = db.query(Trainee).filter(Trainee.id == employment.trainee_pk_id).first()

    records = (
        db.query(EmploymentStatusHistory)
        .filter(EmploymentStatusHistory.employment_pk_id == employment.id)
        .order_by(EmploymentStatusHistory.status_date.asc(), EmploymentStatusHistory.id.asc())
        .all()
    )

    return EmploymentStatusHistoryListResponse(
        employment_id=employment.employment_id,
        status_history=[
            to_response(record, employment.employment_id, trainee.trainee_id)
            for record in records
        ],
    )


@router.get(
    "/api/employment/{employment_id}/summary",
    response_model=EmploymentSummaryResponse,
    summary="Combined employment view: verification, salary, status history",
)
def get_employment_summary(employment_id: str, db: Session = Depends(get_db)):
    employment = get_employment_or_404(employment_id, db)

    latest_verification = (
        db.query(EmployerVerification)
        .filter(EmployerVerification.employment_pk_id == employment.id)
        .order_by(EmployerVerification.id.desc())
        .first()
    )
    wage_records = (
        db.query(WageHistory)
        .filter(WageHistory.employment_pk_id == employment.id)
        .order_by(WageHistory.effective_date.asc(), WageHistory.id.asc())
        .all()
    )
    # Count and latest status from one query instead of two
    statuses = [
        s
        for (s,) in db.query(EmploymentStatusHistory.employment_status)
        .filter(EmploymentStatusHistory.employment_pk_id == employment.id)
        .order_by(EmploymentStatusHistory.status_date.asc(), EmploymentStatusHistory.id.asc())
    ]
    return _build_summary(employment, latest_verification, wage_records, statuses)


def _build_summary(
    employment: EmploymentRecord, latest_verification, wage_records: list, statuses: list
) -> EmploymentSummaryResponse:
    """
    The combined employment view, from already-loaded data: the latest
    verification (or None), wage records oldest first, and the status
    history values oldest first.
    """
    verification_summary = None
    if latest_verification is not None:
        verification_summary = VerificationSummary(
            status=latest_verification.verification_status,
            method=latest_verification.verification_method,
        )

    if wage_records:
        first, last = wage_records[0], wage_records[-1]
        progression = wage_progression_for(wage_records)
        salary_summary = SalarySummary(
            initial=float(first.salary),
            latest=float(last.salary),
            period=last.salary_period,
            initial_period=first.salary_period,
            initial_monthly=_round(progression and progression["initial_monthly"]),
            latest_monthly=_round(progression and progression["latest_monthly"]),
            growth_percentage=_round(progression and progression["growth_percentage"]),
        )
    else:
        # No wage history yet: fall back to the salary on the employment
        # record. Its period was never captured, so it is not normalised.
        fallback = float(employment.salary) if employment.salary is not None else None
        salary_summary = SalarySummary(initial=fallback, latest=fallback)

    status_count = len(statuses)
    current_status = statuses[-1] if statuses else employment.employment_status

    return EmploymentSummaryResponse(
        employment_id=employment.employment_id,
        company_name=employment.company_name,
        job_role=employment.job_role,
        joining_date=employment.joining_date,
        verification=verification_summary,
        salary=salary_summary,
        current_status=current_status,
        wage_history_count=len(wage_records),
        status_history_count=status_count,
    )


@router.get(
    "/api/trainees/{trainee_id}/employment-history",
    response_model=TraineeEmploymentHistoryResponse,
    summary="List all employment records for a trainee (a trainee may have multiple jobs over time)",
)
def get_trainee_employment_history(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)

    employments = (
        db.query(EmploymentRecord)
        .filter(EmploymentRecord.trainee_pk_id == trainee.id)
        .order_by(EmploymentRecord.joining_date.asc())
        .all()
    )

    current = _current_statuses(db, employments)

    return TraineeEmploymentHistoryResponse(
        trainee_id=trainee.trainee_id,
        employment_history=[
            EmploymentHistoryItem(
                employment_id=emp.employment_id,
                company_name=emp.company_name,
                job_role=emp.job_role,
                joining_date=emp.joining_date,
                current_status=current[emp.id],
            )
            for emp in employments
        ],
    )


@router.get(
    "/api/trainees/{trainee_id}/wage-progression",
    response_model=TraineeWageProgressionResponse,
    summary="Every job of a trainee with its summary and wage records, in one response",
)
def get_trainee_wage_progression(trainee_id: str, db: Session = Depends(get_db)):
    """
    What the Wage History page's progression view used to assemble from
    1 + 2 x (number of jobs) requests. Loads each kind of record for all the
    trainee's jobs at once, so it is five queries however many jobs there are.
    """
    trainee = get_trainee_or_404(trainee_id, db)
    employments = (
        db.query(EmploymentRecord)
        .filter(EmploymentRecord.trainee_pk_id == trainee.id)
        .order_by(EmploymentRecord.joining_date.asc())
        .all()
    )
    ids = [e.id for e in employments]

    latest_verification, wages, statuses = {}, defaultdict(list), defaultdict(list)
    if ids:
        for v in (
            db.query(EmployerVerification)
            .filter(EmployerVerification.employment_pk_id.in_(ids))
            .order_by(EmployerVerification.id.asc())
        ):
            latest_verification[v.employment_pk_id] = v  # ascending, so the latest wins
        for w in (
            db.query(WageHistory)
            .filter(WageHistory.employment_pk_id.in_(ids))
            .order_by(WageHistory.effective_date.asc(), WageHistory.id.asc())
        ):
            wages[w.employment_pk_id].append(w)
        for employment_pk_id, status_value in (
            db.query(EmploymentStatusHistory.employment_pk_id, EmploymentStatusHistory.employment_status)
            .filter(EmploymentStatusHistory.employment_pk_id.in_(ids))
            .order_by(EmploymentStatusHistory.status_date.asc(), EmploymentStatusHistory.id.asc())
        ):
            statuses[employment_pk_id].append(status_value)

    result = []
    for emp in employments:
        summary = _build_summary(emp, latest_verification.get(emp.id), wages[emp.id], statuses[emp.id])
        result.append(
            EmploymentWageProgression(
                employment=EmploymentHistoryItem(
                    employment_id=emp.employment_id,
                    company_name=emp.company_name,
                    job_role=emp.job_role,
                    joining_date=emp.joining_date,
                    current_status=summary.current_status,
                ),
                summary=summary,
                wage_history=[
                    wage_to_response(w, emp.employment_id, trainee.trainee_id) for w in wages[emp.id]
                ],
            )
        )
    return TraineeWageProgressionResponse(trainee_id=trainee.trainee_id, employments=result)
