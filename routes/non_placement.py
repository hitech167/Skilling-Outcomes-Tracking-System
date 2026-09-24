"""
Non-placement routes — Phase 3.

POST /api/non-placement                          -> add detail for an outcome
GET  /api/non-placement/{non_placement_id}        -> get one record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import NonPlacementRecord, Outcome, Trainee
from routes._shared import get_outcome_or_404, get_trainee_or_404
from schemas.non_placement import NonPlacementCreate, NonPlacementResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Non-Placement"])


def generate_non_placement_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('non_placement_id_seq')")).scalar()
    return f"NPL{next_number:06d}"


def to_response(
    record: NonPlacementRecord, trainee_public_id: str, outcome_public_id: str
) -> NonPlacementResponse:
    return NonPlacementResponse(
        non_placement_id=record.non_placement_id,
        outcome_id=outcome_public_id,
        trainee_id=trainee_public_id,
        reason_category=record.reason_category,
        reason_details=record.reason_details,
    )


@router.post(
    "/api/non-placement",
    response_model=NonPlacementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add non-placement detail for an 'Unemployed' outcome",
)
def create_non_placement(payload: NonPlacementCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    outcome = get_outcome_or_404(payload.outcome_id, db)

    if outcome.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Outcome {outcome.outcome_id} does not belong to trainee {trainee.trainee_id}",
        )

    if outcome.outcome_type != "Unemployed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Outcome {outcome.outcome_id} is of type '{outcome.outcome_type}', "
                "not 'Unemployed'. This detail can only be added to an Unemployed outcome."
            ),
        )

    try:
        record = NonPlacementRecord(
            non_placement_id=generate_non_placement_id(db),
            outcome_pk_id=outcome.id,
            trainee_pk_id=trainee.id,
            reason_category=payload.reason_category,
            reason_details=payload.reason_details,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating a non-placement record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Created non-placement record %s for %s", record.non_placement_id, trainee.trainee_id
    )

    return to_response(record, trainee.trainee_id, outcome.outcome_id)


@router.get(
    "/api/non-placement/{non_placement_id}",
    response_model=NonPlacementResponse,
    summary="Get a single non-placement record",
)
def get_non_placement(non_placement_id: str, db: Session = Depends(get_db)):
    record = (
        db.query(NonPlacementRecord)
        .filter(NonPlacementRecord.non_placement_id == non_placement_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No non-placement record found with ID {non_placement_id}",
        )

    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()
    outcome = db.query(Outcome).filter(Outcome.id == record.outcome_pk_id).first()

    return to_response(record, trainee.trainee_id, outcome.outcome_id)
