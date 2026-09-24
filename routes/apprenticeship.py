"""
Apprenticeship routes — Phase 3.

POST /api/apprenticeships                        -> add detail for an outcome
GET  /api/apprenticeships/{apprenticeship_id}     -> get one record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import ApprenticeshipRecord, Outcome, Trainee
from routes._shared import get_outcome_or_404, get_trainee_or_404
from schemas.apprenticeship import ApprenticeshipCreate, ApprenticeshipResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Apprenticeship"])


def generate_apprenticeship_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('apprenticeship_id_seq')")).scalar()
    return f"APR{next_number:06d}"


def to_response(
    record: ApprenticeshipRecord, trainee_public_id: str, outcome_public_id: str
) -> ApprenticeshipResponse:
    return ApprenticeshipResponse(
        apprenticeship_id=record.apprenticeship_id,
        outcome_id=outcome_public_id,
        trainee_id=trainee_public_id,
        organization_name=record.organization_name,
        role=record.role,
        start_date=record.start_date,
        end_date=record.end_date,
        monthly_stipend=record.monthly_stipend,
        location=record.location,
    )


@router.post(
    "/api/apprenticeships",
    response_model=ApprenticeshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add apprenticeship detail for an 'Apprenticeship' outcome",
)
def create_apprenticeship(payload: ApprenticeshipCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    outcome = get_outcome_or_404(payload.outcome_id, db)

    if outcome.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outcome {outcome.outcome_id} does not belong to trainee {trainee.trainee_id}",
        )

    if outcome.outcome_type != "Apprenticeship":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Outcome {outcome.outcome_id} is of type '{outcome.outcome_type}', "
                "not 'Apprenticeship'. This detail can only be added to an Apprenticeship outcome."
            ),
        )

    try:
        record = ApprenticeshipRecord(
            apprenticeship_id=generate_apprenticeship_id(db),
            outcome_pk_id=outcome.id,
            trainee_pk_id=trainee.id,
            organization_name=payload.organization_name,
            role=payload.role,
            start_date=payload.start_date,
            end_date=payload.end_date,
            monthly_stipend=payload.monthly_stipend,
            location=payload.location,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating an apprenticeship record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Created apprenticeship record %s for %s", record.apprenticeship_id, trainee.trainee_id
    )

    return to_response(record, trainee.trainee_id, outcome.outcome_id)


@router.get(
    "/api/apprenticeships/{apprenticeship_id}",
    response_model=ApprenticeshipResponse,
    summary="Get a single apprenticeship record",
)
def get_apprenticeship(apprenticeship_id: str, db: Session = Depends(get_db)):
    record = (
        db.query(ApprenticeshipRecord)
        .filter(ApprenticeshipRecord.apprenticeship_id == apprenticeship_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No apprenticeship record found with ID {apprenticeship_id}",
        )

    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()
    outcome = db.query(Outcome).filter(Outcome.id == record.outcome_pk_id).first()

    return to_response(record, trainee.trainee_id, outcome.outcome_id)
