"""
Outcome routes — Phase 3.

POST /api/outcomes                          -> record an outcome
GET  /api/outcomes/{outcome_id}              -> get one outcome
GET  /api/trainees/{trainee_id}/outcomes     -> list a trainee's outcomes
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Outcome
from routes._shared import get_outcome_or_404, get_trainee_or_404, get_training_record_or_404
from schemas.outcome import (
    OutcomeCreate,
    OutcomeResponse,
    OutcomeSummary,
    TraineeOutcomesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Outcomes"])


def generate_outcome_id(db: Session) -> str:
    """Next number from outcome_id_seq, formatted as OUT000001."""
    next_number = db.execute(text("SELECT nextval('outcome_id_seq')")).scalar()
    return f"OUT{next_number:06d}"


def to_response(outcome: Outcome) -> OutcomeResponse:
    return OutcomeResponse(
        outcome_id=outcome.outcome_id,
        trainee_id=outcome.trainee.trainee_id,
        training_id=outcome.training_record.record_id,
        outcome_type=outcome.outcome_type,
        status_date=outcome.status_date,
        notes=outcome.notes,
    )


@router.post(
    "/api/outcomes",
    response_model=OutcomeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an outcome for a trainee's training",
)
def create_outcome(payload: OutcomeCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    training_record = get_training_record_or_404(payload.training_id, db)

    # The training must actually belong to this trainee
    if training_record.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Training record {training_record.record_id} does not belong "
                f"to trainee {trainee.trainee_id}"
            ),
        )

    try:
        outcome = Outcome(
            outcome_id=generate_outcome_id(db),
            trainee_pk_id=trainee.id,
            training_record_pk_id=training_record.id,
            outcome_type=payload.outcome_type,
            status_date=payload.status_date,
            notes=payload.notes,
        )
        db.add(outcome)
        db.commit()
        db.refresh(outcome)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating an outcome")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the outcome right now. Please try again.",
        )

    logger.info("Recorded outcome %s (%s) for %s", outcome.outcome_id, outcome.outcome_type, trainee.trainee_id)

    return to_response(outcome)


@router.get(
    "/api/outcomes/{outcome_id}",
    response_model=OutcomeResponse,
    summary="Get a single outcome",
)
def get_outcome(outcome_id: str, db: Session = Depends(get_db)):
    outcome = get_outcome_or_404(outcome_id, db)
    return to_response(outcome)


@router.get(
    "/api/trainees/{trainee_id}/outcomes",
    response_model=TraineeOutcomesResponse,
    summary="List all outcomes for a trainee",
)
def list_trainee_outcomes(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)

    outcomes = (
        db.query(Outcome)
        .filter(Outcome.trainee_pk_id == trainee.id)
        .order_by(Outcome.status_date)
        .all()
    )

    return TraineeOutcomesResponse(
        trainee_id=trainee.trainee_id,
        outcomes=[
            OutcomeSummary(
                outcome_id=o.outcome_id,
                training_id=o.training_record.record_id,
                outcome_type=o.outcome_type,
                status_date=o.status_date,
            )
            for o in outcomes
        ],
    )
