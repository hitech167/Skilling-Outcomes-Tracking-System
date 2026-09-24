"""
Follow-up tracking routes — Phase 5 (automated + assisted follow-up system).

This file only ADDS new endpoints on top of the existing Phase 3
`followups` table and routes/followup.py (schedule / get / list / PATCH).
Nothing in Phase 1-4 is modified.

    POST /api/followups/generate/{training_id}   -> generate the 4-follow-up schedule
    GET  /api/followups/pending                  -> due now, still Scheduled
    GET  /api/followups/upcoming                 -> due within N days (default 7)
    GET  /api/followups/overdue                   -> Scheduled + scheduled_date < today
    GET  /api/followups/summary                   -> admin counts

    POST /api/followups/{followup_id}/complete
    POST /api/followups/{followup_id}/missed
    POST /api/followups/{followup_id}/not-reachable

    POST /api/followups/{followup_id}/attempt      -> log a contact attempt
    GET  /api/followups/{followup_id}/attempts     -> attempt history
    POST /api/followups/{followup_id}/outcome-update -> trainee's current situation
    GET  /api/followups/{followup_id}/summary       -> everything about one follow-up

    GET  /api/trainees/{trainee_id}/followup-timeline

IMPORTANT (route ordering): the GET routes with fixed paths (`pending`,
`upcoming`, `overdue`, `summary`) must be registered BEFORE
routes/followup.py's `GET /api/followups/{followup_id}` — otherwise
FastAPI would match e.g. "pending" as a followup_id and return 404. This
is handled in main.py by including this router first.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import (
    FollowUp,
    FollowUpAttempt,
    FollowUpOutcomeUpdate,
    Outcome,
    Trainee,
    TrainingRecord,
)
from routes._shared import get_outcome_or_404, get_trainee_or_404, get_training_record_or_404
from routes.followup import get_followup_or_404
from schemas.followup_tracking import (
    AdminFollowUpSummaryResponse,
    FollowUpAttemptCreate,
    FollowUpAttemptResponse,
    FollowUpCompleteRequest,
    FollowUpGenerateResponse,
    FollowUpListItem,
    FollowUpMissedRequest,
    FollowUpNotReachableRequest,
    FollowUpOutcomeUpdateCreate,
    FollowUpOutcomeUpdateResponse,
    FollowUpSummaryResponse,
    OverdueFollowUpItem,
    TraineeFollowupTimelineItem,
    TraineeFollowupTimelineResponse,
)
from services import followup_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Follow-up Tracking (Phase 5)"])


# ---------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------


def generate_attempt_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('followup_attempt_id_seq')")).scalar()
    return f"ATT{next_number:06d}"


def generate_outcome_update_id(db: Session) -> str:
    next_number = db.execute(
        text("SELECT nextval('followup_outcome_update_id_seq')")
    ).scalar()
    return f"FOU{next_number:06d}"


# ---------------------------------------------------------------------
# 1. Schedule generation
# ---------------------------------------------------------------------


@router.post(
    "/api/followups/generate/{training_id}",
    response_model=FollowUpGenerateResponse,
    summary="Generate the 30/90-day and 6/12-month follow-up schedule for a completed training",
)
def generate_followup_schedule(training_id: str, db: Session = Depends(get_db)):
    training_record = get_training_record_or_404(training_id, db)
    trainee = get_trainee_or_404_by_pk(training_record.trainee_pk_id, db)

    if training_record.status != "Completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Training {training_record.record_id} is not marked Completed yet",
        )
    if training_record.end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Training {training_record.record_id} has no end/completion date",
        )
    _require_consent(trainee)

    try:
        # Lock the training row so two simultaneous generate calls can't
        # both see "no follow-ups yet" and insert duplicates.
        db.query(TrainingRecord).filter(TrainingRecord.id == training_record.id).with_for_update().one()
        created = followup_scheduler.generate_schedule_for_training(
            db,
            trainee_pk_id=trainee.id,
            training_record_pk_id=training_record.id,
            completion_date=training_record.end_date,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while generating follow-up schedule")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not generate the follow-up schedule right now. Please try again.",
        )

    if created:
        message = "Follow-up schedule created successfully"
    else:
        message = "Follow-up schedule already exists"

    logger.info(
        "Follow-up schedule generation for %s: %d created", training_record.record_id, len(created)
    )

    return FollowUpGenerateResponse(
        success=True,
        training_id=training_record.record_id,
        followups_created=len(created),
        message=message,
    )


def _require_consent(trainee: Trainee) -> None:
    """No new follow-up scheduling or contact once a trainee has withdrawn consent."""
    if not trainee.consent_given:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trainee {trainee.trainee_id} has not given (or has withdrawn) consent to follow-up contact",
        )


def get_trainee_or_404_by_pk(trainee_pk_id: int, db: Session):
    trainee = db.query(Trainee).filter(Trainee.id == trainee_pk_id).first()
    if trainee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trainee not found")
    return trainee


def _trainee_public_id(db: Session, trainee_pk_id: int) -> str:
    trainee = db.query(Trainee).filter(Trainee.id == trainee_pk_id).first()
    return trainee.trainee_id if trainee else None


def _training_public_id(db: Session, training_record_pk_id: int) -> str:
    record = db.query(TrainingRecord).filter(TrainingRecord.id == training_record_pk_id).first()
    return record.record_id if record else None


# ---------------------------------------------------------------------
# 2. Pending / upcoming / overdue / admin summary
#    (fixed-path routes — must stay registered ahead of
#    GET /api/followups/{followup_id} in routes/followup.py)
# ---------------------------------------------------------------------


def _to_list_item(followup: FollowUp, db: Session) -> FollowUpListItem:
    return FollowUpListItem(
        followup_id=followup.followup_id,
        trainee_id=_trainee_public_id(db, followup.trainee_pk_id),
        training_id=_training_public_id(db, followup.training_record_pk_id),
        followup_type=followup.followup_type,
        scheduled_date=followup.scheduled_date,
        status=followup.status,
    )


@router.get(
    "/api/followups/pending",
    response_model=list[FollowUpListItem],
    summary="Follow-ups that are due now (Scheduled, scheduled_date <= today)",
)
def list_pending_followups(db: Session = Depends(get_db)):
    followups = followup_scheduler.get_pending_followups(db)
    return [_to_list_item(f, db) for f in followups]


@router.get(
    "/api/followups/upcoming",
    response_model=list[FollowUpListItem],
    summary="Scheduled follow-ups due within the next N days (default 7)",
)
def list_upcoming_followups(
    days: int = Query(7, ge=1, le=1000), db: Session = Depends(get_db)
):
    followups = followup_scheduler.get_upcoming_followups(db, days)
    return [_to_list_item(f, db) for f in followups]


@router.get(
    "/api/followups/overdue",
    response_model=list[OverdueFollowUpItem],
    summary="Scheduled follow-ups whose scheduled date has already passed",
)
def list_overdue_followups(db: Session = Depends(get_db)):
    today = date.today()
    followups = followup_scheduler.get_overdue_followups(db)
    return [
        OverdueFollowUpItem(
            followup_id=f.followup_id,
            trainee_id=_trainee_public_id(db, f.trainee_pk_id),
            training_id=_training_public_id(db, f.training_record_pk_id),
            followup_type=f.followup_type,
            scheduled_date=f.scheduled_date,
            days_overdue=(today - f.scheduled_date).days,
        )
        for f in followups
    ]


@router.get(
    "/api/followups/summary",
    response_model=AdminFollowUpSummaryResponse,
    summary="Dynamically calculated follow-up counts for administrators",
)
def admin_followup_summary(db: Session = Depends(get_db)):
    counts = followup_scheduler.get_admin_summary_counts(db)
    return AdminFollowUpSummaryResponse(**counts)


# ---------------------------------------------------------------------
# 3. Complete / missed / not-reachable
# ---------------------------------------------------------------------


@router.post(
    "/api/followups/{followup_id}/complete",
    response_model=FollowUpListItem,
    summary="Mark a follow-up Completed (keeps the original scheduled_date)",
)
def complete_followup(
    followup_id: str, payload: FollowUpCompleteRequest, db: Session = Depends(get_db)
):
    followup = get_followup_or_404(followup_id, db)

    if payload.completed_date < followup.scheduled_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="completed_date cannot be before scheduled_date",
        )

    if payload.outcome_id:
        outcome = get_outcome_or_404(payload.outcome_id, db)
        if outcome.trainee_pk_id != followup.trainee_pk_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Outcome {outcome.outcome_id} does not belong to the same trainee",
            )
        followup.outcome_pk_id = outcome.id

    followup.status = "Completed"
    followup.completed_date = payload.completed_date
    if payload.notes is not None:
        followup.notes = payload.notes

    try:
        db.commit()
        db.refresh(followup)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while completing a follow-up")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not complete the follow-up right now. Please try again.",
        )

    return _to_list_item(followup, db)


@router.post(
    "/api/followups/{followup_id}/missed",
    response_model=FollowUpListItem,
    summary="Mark a follow-up Missed",
)
def mark_followup_missed(
    followup_id: str, payload: FollowUpMissedRequest, db: Session = Depends(get_db)
):
    followup = get_followup_or_404(followup_id, db)
    followup.status = "Missed"
    if payload.notes is not None:
        followup.notes = payload.notes

    try:
        db.commit()
        db.refresh(followup)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while marking a follow-up missed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update the follow-up right now. Please try again.",
        )

    return _to_list_item(followup, db)


@router.post(
    "/api/followups/{followup_id}/not-reachable",
    response_model=FollowUpListItem,
    summary="Mark a follow-up Not Reachable",
)
def mark_followup_not_reachable(
    followup_id: str, payload: FollowUpNotReachableRequest, db: Session = Depends(get_db)
):
    followup = get_followup_or_404(followup_id, db)
    followup.status = "Not Reachable"
    if payload.notes is not None:
        followup.notes = payload.notes

    try:
        db.commit()
        db.refresh(followup)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while marking a follow-up not reachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update the follow-up right now. Please try again.",
        )

    return _to_list_item(followup, db)


# ---------------------------------------------------------------------
# 4. Contact attempts
# ---------------------------------------------------------------------


@router.post(
    "/api/followups/{followup_id}/attempt",
    response_model=FollowUpAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a contact attempt for a follow-up",
)
def add_followup_attempt(
    followup_id: str, payload: FollowUpAttemptCreate, db: Session = Depends(get_db)
):
    followup = get_followup_or_404(followup_id, db)
    _require_consent(get_trainee_or_404_by_pk(followup.trainee_pk_id, db))

    try:
        attempt = FollowUpAttempt(
            attempt_id=generate_attempt_id(db),
            followup_pk_id=followup.id,
            attempt_date=payload.attempt_date,
            contact_method=payload.contact_method,
            attempt_status=payload.attempt_status,
            notes=payload.notes,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while recording a follow-up attempt")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the attempt right now. Please try again.",
        )

    return FollowUpAttemptResponse(
        attempt_id=attempt.attempt_id,
        followup_id=followup.followup_id,
        attempt_date=attempt.attempt_date,
        contact_method=attempt.contact_method,
        attempt_status=attempt.attempt_status,
        notes=attempt.notes,
    )


@router.get(
    "/api/followups/{followup_id}/attempts",
    response_model=list[FollowUpAttemptResponse],
    summary="Full contact-attempt history for a follow-up",
)
def list_followup_attempts(followup_id: str, db: Session = Depends(get_db)):
    followup = get_followup_or_404(followup_id, db)
    attempts = (
        db.query(FollowUpAttempt)
        .filter(FollowUpAttempt.followup_pk_id == followup.id)
        .order_by(FollowUpAttempt.attempt_date.asc(), FollowUpAttempt.id.asc())
        .all()
    )
    return [
        FollowUpAttemptResponse(
            attempt_id=a.attempt_id,
            followup_id=followup.followup_id,
            attempt_date=a.attempt_date,
            contact_method=a.contact_method,
            attempt_status=a.attempt_status,
            notes=a.notes,
        )
        for a in attempts
    ]


# ---------------------------------------------------------------------
# 5. Outcome update (trainee's current situation)
# ---------------------------------------------------------------------


@router.post(
    "/api/followups/{followup_id}/outcome-update",
    response_model=FollowUpOutcomeUpdateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record the trainee's current situation during a follow-up",
)
def add_followup_outcome_update(
    followup_id: str, payload: FollowUpOutcomeUpdateCreate, db: Session = Depends(get_db)
):
    followup = get_followup_or_404(followup_id, db)

    try:
        update = FollowUpOutcomeUpdate(
            update_id=generate_outcome_update_id(db),
            followup_pk_id=followup.id,
            trainee_pk_id=followup.trainee_pk_id,
            employment_status=payload.employment_status,
            training_relevance=payload.training_relevance,
            skill_gap=payload.skill_gap,
            additional_training_needed=payload.additional_training_needed,
            unemployment_reason_category=payload.unemployment_reason_category,
            unemployment_reason_details=payload.unemployment_reason_details,
            notes=payload.notes,
        )
        db.add(update)
        db.commit()
        db.refresh(update)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while recording a follow-up outcome update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the outcome update right now. Please try again.",
        )

    return FollowUpOutcomeUpdateResponse(
        update_id=update.update_id,
        followup_id=followup.followup_id,
        employment_status=update.employment_status,
        training_relevance=update.training_relevance,
        skill_gap=update.skill_gap,
        additional_training_needed=update.additional_training_needed,
        unemployment_reason_category=update.unemployment_reason_category,
        unemployment_reason_details=update.unemployment_reason_details,
        notes=update.notes,
    )


# ---------------------------------------------------------------------
# 6. Follow-up summary (single follow-up, everything about it)
# ---------------------------------------------------------------------


@router.get(
    "/api/followups/{followup_id}/summary",
    response_model=FollowUpSummaryResponse,
    summary="Everything about one follow-up: attempts, latest attempt, current outcome",
)
def followup_summary(followup_id: str, db: Session = Depends(get_db)):
    followup = get_followup_or_404(followup_id, db)

    attempt_count = (
        db.query(FollowUpAttempt).filter(FollowUpAttempt.followup_pk_id == followup.id).count()
    )
    latest_attempt_row = (
        db.query(FollowUpAttempt)
        .filter(FollowUpAttempt.followup_pk_id == followup.id)
        .order_by(FollowUpAttempt.attempt_date.desc(), FollowUpAttempt.id.desc())
        .first()
    )
    latest_attempt = None
    if latest_attempt_row is not None:
        latest_attempt = FollowUpAttemptResponse(
            attempt_id=latest_attempt_row.attempt_id,
            followup_id=followup.followup_id,
            attempt_date=latest_attempt_row.attempt_date,
            contact_method=latest_attempt_row.contact_method,
            attempt_status=latest_attempt_row.attempt_status,
            notes=latest_attempt_row.notes,
        )

    latest_update_row = (
        db.query(FollowUpOutcomeUpdate)
        .filter(FollowUpOutcomeUpdate.followup_pk_id == followup.id)
        .order_by(FollowUpOutcomeUpdate.id.desc())
        .first()
    )
    current_outcome = None
    if latest_update_row is not None:
        current_outcome = FollowUpOutcomeUpdateResponse(
            update_id=latest_update_row.update_id,
            followup_id=followup.followup_id,
            employment_status=latest_update_row.employment_status,
            training_relevance=latest_update_row.training_relevance,
            skill_gap=latest_update_row.skill_gap,
            additional_training_needed=latest_update_row.additional_training_needed,
            unemployment_reason_category=latest_update_row.unemployment_reason_category,
            unemployment_reason_details=latest_update_row.unemployment_reason_details,
            notes=latest_update_row.notes,
        )

    return FollowUpSummaryResponse(
        followup_id=followup.followup_id,
        trainee_id=_trainee_public_id(db, followup.trainee_pk_id),
        training_id=_training_public_id(db, followup.training_record_pk_id),
        followup_type=followup.followup_type,
        scheduled_date=followup.scheduled_date,
        completed_date=followup.completed_date,
        status=followup.status,
        attempt_count=attempt_count,
        latest_attempt=latest_attempt,
        current_outcome=current_outcome,
    )


# ---------------------------------------------------------------------
# 7. Trainee follow-up timeline
# ---------------------------------------------------------------------


@router.get(
    "/api/trainees/{trainee_id}/followup-timeline",
    response_model=TraineeFollowupTimelineResponse,
    summary="All follow-ups for a trainee, in chronological order",
)
def trainee_followup_timeline(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)

    followups = (
        db.query(FollowUp)
        .filter(FollowUp.trainee_pk_id == trainee.id)
        .order_by(FollowUp.scheduled_date.asc())
        .all()
    )

    return TraineeFollowupTimelineResponse(
        trainee_id=trainee.trainee_id,
        followups=[
            TraineeFollowupTimelineItem(
                followup_id=f.followup_id,
                training_id=_training_public_id(db, f.training_record_pk_id),
                followup_type=f.followup_type,
                scheduled_date=f.scheduled_date,
                completed_date=f.completed_date,
                status=f.status,
            )
            for f in followups
        ],
    )
