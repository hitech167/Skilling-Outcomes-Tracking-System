"""
Follow-up routes — Phase 3.

POST  /api/followups                          -> schedule a follow-up
GET   /api/followups/{followup_id}             -> get one follow-up
GET   /api/trainees/{trainee_id}/followups     -> list a trainee's follow-ups
PATCH /api/followups/{followup_id}             -> record the result of a follow-up
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import FollowUp, Outcome
from routes._shared import get_outcome_or_404, get_trainee_or_404, get_training_record_or_404
from schemas.followup import FollowUpCreate, FollowUpResponse, FollowUpUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Follow-ups"])


def generate_followup_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('followup_id_seq')")).scalar()
    return f"FUP{next_number:06d}"


def get_followup_or_404(followup_id: str, db: Session) -> FollowUp:
    followup = (
        db.query(FollowUp)
        .filter(FollowUp.followup_id == followup_id.strip().upper())
        .first()
    )
    if followup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No follow-up found with ID {followup_id}",
        )
    return followup


def to_response(
    followup: FollowUp, trainee_public_id: str, training_public_id: str, outcome_public_id: str | None
) -> FollowUpResponse:
    return FollowUpResponse(
        followup_id=followup.followup_id,
        trainee_id=trainee_public_id,
        training_id=training_public_id,
        followup_type=followup.followup_type,
        scheduled_date=followup.scheduled_date,
        completed_date=followup.completed_date,
        status=followup.status,
        outcome_id=outcome_public_id,
        notes=followup.notes,
    )


@router.post(
    "/api/followups",
    response_model=FollowUpResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a follow-up for a trainee's training",
)
def create_followup(payload: FollowUpCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(payload.trainee_id, db)
    training_record = get_training_record_or_404(payload.training_id, db)

    if training_record.trainee_pk_id != trainee.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Training record {training_record.record_id} does not belong "
                f"to trainee {trainee.trainee_id}"
            ),
        )
    if not trainee.consent_given:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trainee {trainee.trainee_id} has not given (or has withdrawn) consent to follow-up contact",
        )
    # One follow-up of each type per training (same rule as
    # POST /api/followups/generate/{training_id}).
    duplicate = (
        db.query(FollowUp.followup_id)
        .filter(
            FollowUp.training_record_pk_id == training_record.id,
            FollowUp.followup_type == payload.followup_type,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A {payload.followup_type} follow-up ({duplicate[0]}) already exists "
                f"for training {training_record.record_id}"
            ),
        )

    try:
        followup = FollowUp(
            followup_id=generate_followup_id(db),
            trainee_pk_id=trainee.id,
            training_record_pk_id=training_record.id,
            followup_type=payload.followup_type,
            scheduled_date=payload.scheduled_date,
            status="Scheduled",
            notes=payload.notes,
        )
        db.add(followup)
        db.commit()
        db.refresh(followup)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating a follow-up")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the follow-up right now. Please try again.",
        )

    logger.info("Scheduled follow-up %s (%s) for %s", followup.followup_id, followup.followup_type, trainee.trainee_id)

    return to_response(followup, trainee.trainee_id, training_record.record_id, None)


@router.get(
    "/api/followups/{followup_id}",
    response_model=FollowUpResponse,
    summary="Get a single follow-up",
)
def get_followup(followup_id: str, db: Session = Depends(get_db)):
    followup = get_followup_or_404(followup_id, db)

    trainee_id = _trainee_id_lookup(db, followup.trainee_pk_id)
    training_id = _training_id_lookup(db, followup.training_record_pk_id)
    outcome_public_id = None
    if followup.outcome_pk_id is not None:
        outcome = db.query(Outcome).filter(Outcome.id == followup.outcome_pk_id).first()
        outcome_public_id = outcome.outcome_id if outcome else None

    return to_response(followup, trainee_id, training_id, outcome_public_id)


def _trainee_id_lookup(db: Session, trainee_pk_id: int) -> str:
    from database.models import Trainee

    trainee = db.query(Trainee).filter(Trainee.id == trainee_pk_id).first()
    return trainee.trainee_id


def _training_id_lookup(db: Session, training_record_pk_id: int) -> str:
    from database.models import TrainingRecord

    record = db.query(TrainingRecord).filter(TrainingRecord.id == training_record_pk_id).first()
    return record.record_id


@router.get(
    "/api/trainees/{trainee_id}/followups",
    response_model=list[FollowUpResponse],
    summary="List all follow-ups for a trainee",
)
def list_trainee_followups(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)

    followups = (
        db.query(FollowUp)
        .filter(FollowUp.trainee_pk_id == trainee.id)
        .order_by(FollowUp.scheduled_date)
        .all()
    )

    results = []
    for followup in followups:
        training_id = _training_id_lookup(db, followup.training_record_pk_id)
        outcome_public_id = None
        if followup.outcome_pk_id is not None:
            outcome = db.query(Outcome).filter(Outcome.id == followup.outcome_pk_id).first()
            outcome_public_id = outcome.outcome_id if outcome else None
        results.append(to_response(followup, trainee.trainee_id, training_id, outcome_public_id))

    return results


@router.patch(
    "/api/followups/{followup_id}",
    response_model=FollowUpResponse,
    summary="Record the result of a follow-up (Completed / Missed / Not Reachable)",
)
def update_followup(followup_id: str, payload: FollowUpUpdate, db: Session = Depends(get_db)):
    followup = get_followup_or_404(followup_id, db)

    updates = payload.model_dump(exclude_unset=True)

    outcome_pk_id = None
    if "outcome_id" in updates and updates["outcome_id"] is not None:
        outcome = get_outcome_or_404(updates.pop("outcome_id"), db)
        # The outcome, if given, must belong to the same trainee as the follow-up
        if outcome.trainee_pk_id != followup.trainee_pk_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Outcome {outcome.outcome_id} does not belong to the same trainee as this follow-up",
            )
        outcome_pk_id = outcome.id
        followup.outcome_pk_id = outcome_pk_id
    elif "outcome_id" in updates:
        updates.pop("outcome_id")

    for field, value in updates.items():
        setattr(followup, field, value)

    try:
        db.commit()
        db.refresh(followup)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while updating a follow-up")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update the follow-up right now. Please try again.",
        )

    logger.info("Updated follow-up %s -> status=%s", followup.followup_id, followup.status)

    trainee_id = _trainee_id_lookup(db, followup.trainee_pk_id)
    training_id = _training_id_lookup(db, followup.training_record_pk_id)
    outcome_public_id = None
    if followup.outcome_pk_id is not None:
        outcome = db.query(Outcome).filter(Outcome.id == followup.outcome_pk_id).first()
        outcome_public_id = outcome.outcome_id if outcome else None

    return to_response(followup, trainee_id, training_id, outcome_public_id)
