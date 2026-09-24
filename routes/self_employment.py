"""
Self-employment routes — Phase 3.

POST /api/self-employment                        -> add detail for an outcome
GET  /api/self-employment/{self_employment_id}    -> get one record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Outcome, SelfEmploymentRecord, Trainee
from routes._shared import get_outcome_or_404, get_trainee_or_404
from schemas.self_employment import SelfEmploymentCreate, SelfEmploymentResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Self-Employment"])


def generate_self_employment_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('self_employment_id_seq')")).scalar()
    return f"SEM{next_number:06d}"


def to_response(
    record: SelfEmploymentRecord, trainee_public_id: str, outcome_public_id: str
) -> SelfEmploymentResponse:
    return SelfEmploymentResponse(
        self_employment_id=record.self_employment_id,
        outcome_id=outcome_public_id,
        trainee_id=trainee_public_id,
        business_name=record.business_name,
        business_type=record.business_type,
        start_date=record.start_date,
        monthly_income=record.monthly_income,
        location=record.location,
        number_of_workers=record.number_of_workers,
    )


@router.post(
    "/api/self-employment",
    response_model=SelfEmploymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add self-employment detail for a 'Self-employed' outcome",
)
def create_self_employment(payload: SelfEmploymentCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    outcome = get_outcome_or_404(payload.outcome_id, db)

    if outcome.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outcome {outcome.outcome_id} does not belong to trainee {trainee.trainee_id}",
        )

    if outcome.outcome_type != "Self-employed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Outcome {outcome.outcome_id} is of type '{outcome.outcome_type}', "
                "not 'Self-employed'. This detail can only be added to a Self-employed outcome."
            ),
        )

    try:
        record = SelfEmploymentRecord(
            self_employment_id=generate_self_employment_id(db),
            outcome_pk_id=outcome.id,
            trainee_pk_id=trainee.id,
            business_name=payload.business_name,
            business_type=payload.business_type,
            start_date=payload.start_date,
            monthly_income=payload.monthly_income,
            location=payload.location,
            number_of_workers=payload.number_of_workers,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating a self-employment record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Created self-employment record %s for %s", record.self_employment_id, trainee.trainee_id
    )

    return to_response(record, trainee.trainee_id, outcome.outcome_id)


@router.get(
    "/api/self-employment/{self_employment_id}",
    response_model=SelfEmploymentResponse,
    summary="Get a single self-employment record",
)
def get_self_employment(self_employment_id: str, db: Session = Depends(get_db)):
    record = (
        db.query(SelfEmploymentRecord)
        .filter(SelfEmploymentRecord.self_employment_id == self_employment_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No self-employment record found with ID {self_employment_id}",
        )

    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()
    outcome = db.query(Outcome).filter(Outcome.id == record.outcome_pk_id).first()

    return to_response(record, trainee.trainee_id, outcome.outcome_id)
