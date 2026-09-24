"""
Employment routes — Phase 3.

POST /api/employment                 -> add employment detail for an outcome
GET  /api/employment/{employment_id} -> get one employment record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import EmploymentRecord, Outcome, Trainee
from routes._shared import get_outcome_or_404, get_trainee_or_404
from schemas.employment import EmploymentCreate, EmploymentResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Employment"])


def generate_employment_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('employment_id_seq')")).scalar()
    return f"EMP{next_number:06d}"


def to_response(
    record: EmploymentRecord, trainee_public_id: str, outcome_public_id: str
) -> EmploymentResponse:
    return EmploymentResponse(
        employment_id=record.employment_id,
        outcome_id=outcome_public_id,
        trainee_id=trainee_public_id,
        company_name=record.company_name,
        job_role=record.job_role,
        joining_date=record.joining_date,
        salary=record.salary,
        employment_status=record.employment_status,
        job_location=record.job_location,
        job_relevance=record.job_relevance,
    )


@router.post(
    "/api/employment",
    response_model=EmploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add employment detail for an 'Employed' outcome",
)
def create_employment(payload: EmploymentCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    outcome = get_outcome_or_404(payload.outcome_id, db)

    if outcome.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outcome {outcome.outcome_id} does not belong to trainee {trainee.trainee_id}",
        )

    if outcome.outcome_type != "Employed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Outcome {outcome.outcome_id} is of type '{outcome.outcome_type}', "
                "not 'Employed'. Employment detail can only be added to an Employed outcome."
            ),
        )

    try:
        record = EmploymentRecord(
            employment_id=generate_employment_id(db),
            outcome_pk_id=outcome.id,
            trainee_pk_id=trainee.id,
            company_name=payload.company_name,
            job_role=payload.job_role,
            joining_date=payload.joining_date,
            salary=payload.salary,
            employment_status=payload.employment_status,
            job_location=payload.job_location,
            job_relevance=payload.job_relevance,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating an employment record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info("Created employment record %s for %s", record.employment_id, trainee.trainee_id)

    return to_response(record, trainee.trainee_id, outcome.outcome_id)


@router.get(
    "/api/employment/{employment_id}",
    response_model=EmploymentResponse,
    summary="Get a single employment record",
)
def get_employment(employment_id: str, db: Session = Depends(get_db)):
    record = (
        db.query(EmploymentRecord)
        .filter(EmploymentRecord.employment_id == employment_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No employment record found with ID {employment_id}",
        )

    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()
    outcome = db.query(Outcome).filter(Outcome.id == record.outcome_pk_id).first()

    return to_response(record, trainee.trainee_id, outcome.outcome_id)
