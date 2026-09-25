"""
Trainee routes.

POST  /api/trainees               -> register a trainee, return the generated ID
GET   /api/trainees/{id}          -> fetch a trainee's basic public profile
GET   /api/trainees/{id}/contact  -> contact details for assisted follow-ups
PATCH /api/trainees/{id}          -> update phone / email / location (ID is stable)
POST  /api/trainees/{id}/consent  -> withdraw or re-grant consent
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Trainee, TraineeConsentHistory, TraineeContactHistory
from services import consent_service, contact_service, identity_service
from schemas.trainee import (
    ConsentUpdate,
    TraineeContact,
    TraineeContactUpdate,
    TraineeCreate,
    TraineeCreateResponse,
    TraineePublic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trainees", tags=["Trainees"])


def generate_trainee_id(db: Session) -> str:
    """
    Ask PostgreSQL for the next number in trainee_id_seq and format it
    as TRN000001, TRN000002, ...

    Using a database sequence (instead of counting rows) means two people
    registering at the same second can never get the same ID.
    """
    next_number = db.execute(text("SELECT nextval('trainee_id_seq')")).scalar()
    return f"TRN{next_number:06d}"


@router.post(
    "",
    response_model=TraineeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new trainee",
)
def register_trainee(payload: TraineeCreate, db: Session = Depends(get_db)):
    # Pydantic has already checked consent_given is True, but we check again
    # here so the rule is obvious to anyone reading the route.
    if not payload.consent_given:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent is required to register a trainee.",
        )

    # Reject an obvious duplicate before we burn a number from the sequence.
    existing = (
        db.query(Trainee.trainee_id).filter(Trainee.phone == payload.phone).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A trainee is already registered with this contact number.",
        )

    # Same person already registered under another programme? An external
    # ID that is already linked means this is a duplicate registration.
    for ext in payload.external_ids:
        owner = identity_service.existing_owner(db, ext.id_type, ext.id_value)
        if owner is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{ext.id_type} {ext.id_value} is already linked to trainee {owner.trainee_id}",
            )
    # Same name + DOB is only a warning: two different people can share both.
    possible_duplicates = identity_service.find_possible_duplicates(
        db, payload.full_name, payload.dob
    )

    try:
        trainee = Trainee(
            trainee_id=generate_trainee_id(db),
            full_name=payload.full_name,
            dob=payload.dob,
            gender=payload.gender,
            district=payload.district,
            current_location=payload.current_location,
            phone=payload.phone,
            email=str(payload.email) if payload.email else None,
            preferred_contact=payload.preferred_contact,
        )
        db.add(trainee)
        db.flush()
        consent_service.set_consent(
            db, trainee, payload.consent_given, source="registration",
            method=payload.consent_method, recorded_by=payload.consent_recorded_by,
        )
        for ext in payload.external_ids:
            identity_service.link_external_id(
                db, trainee, ext.id_type, ext.id_value, ext.source_programme
            )
        db.commit()
        db.refresh(trainee)

    except IntegrityError:
        db.rollback()
        # Unique constraint hit (duplicate phone, email or trainee_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A trainee with these details already exists.",
        )

    except SQLAlchemyError:
        db.rollback()
        # Log the type of failure, never the trainee's personal data
        logger.exception("Database error while registering a trainee")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    # Safe to log: the ID carries no personal information
    logger.info("Registered trainee %s", trainee.trainee_id)

    return TraineeCreateResponse(
        trainee_id=trainee.trainee_id, possible_duplicates=possible_duplicates
    )


@router.get(
    "/{trainee_id}",
    response_model=TraineePublic,
    summary="Get a trainee's basic profile",
)
def get_trainee(trainee_id: str, db: Session = Depends(get_db)):
    try:
        trainee = (
            db.query(Trainee)
            .filter(Trainee.trainee_id == trainee_id.strip().upper())
            .first()
        )
    except SQLAlchemyError:
        logger.exception("Database error while fetching a trainee")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not read the record right now. Please try again.",
        )

    if trainee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trainee found with ID {trainee_id}",
        )

    # TraineePublic controls exactly which fields go out — phone, email and
    # date of birth are not included.
    return trainee


def _get_trainee_or_404(trainee_id: str, db: Session) -> Trainee:
    trainee = (
        db.query(Trainee).filter(Trainee.trainee_id == trainee_id.strip().upper()).first()
    )
    if trainee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trainee found with ID {trainee_id}",
        )
    return trainee


def _commit(db: Session, action: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another trainee is already registered with this phone number or email.",
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while %s", action)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update the record right now. Please try again.",
        )


@router.get(
    "/{trainee_id}/contact",
    response_model=TraineeContact,
    summary="Contact details for assisted follow-ups (admin only)",
)
def get_trainee_contact(trainee_id: str, db: Session = Depends(get_db)):
    return _get_trainee_or_404(trainee_id, db)


@router.patch(
    "/{trainee_id}",
    response_model=TraineePublic,
    summary="Update a trainee's contact details or location (trainee_id never changes)",
)
def update_trainee_contact(
    trainee_id: str, payload: TraineeContactUpdate, db: Session = Depends(get_db)
):
    trainee = _get_trainee_or_404(trainee_id, db)
    updates = payload.model_dump(exclude_unset=True)
    changed = contact_service.apply_contact_update(db, trainee, updates, source="admin")

    _commit(db, "updating trainee contact details")
    db.refresh(trainee)
    logger.info("Updated contact details for %s (%s)", trainee.trainee_id, ", ".join(changed))
    return trainee


@router.post(
    "/{trainee_id}/consent",
    response_model=TraineePublic,
    summary="Record that a trainee has withdrawn (false) or re-granted (true) consent",
)
def update_consent(trainee_id: str, payload: ConsentUpdate, db: Session = Depends(get_db)):
    """
    Withdrawn consent stops new follow-up schedules, contact attempts and
    automated messages, and removes the trainee from every analytics /
    insights figure (see services/consent_scope.py). Records are kept,
    not deleted, so re-granting consent restores them.
    consent_date records when the current consent state was set.
    """
    trainee = _get_trainee_or_404(trainee_id, db)
    consent_service.set_consent(
        db, trainee, payload.consent_given, source="admin",
        method=payload.method, recorded_by=payload.recorded_by, notes=payload.notes,
    )
    _commit(db, "updating trainee consent")
    db.refresh(trainee)
    logger.info("Consent for %s set to %s", trainee.trainee_id, trainee.consent_given)
    return trainee


@router.get(
    "/{trainee_id}/contact-history",
    summary="Previous phone / email / district values, newest first",
)
def contact_history(trainee_id: str, db: Session = Depends(get_db)):
    trainee = _get_trainee_or_404(trainee_id, db)
    rows = (
        db.query(TraineeContactHistory)
        .filter(TraineeContactHistory.trainee_pk_id == trainee.id)
        .order_by(TraineeContactHistory.id.desc())
        .all()
    )
    return [
        {
            "field": r.field,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "source": r.source,
            "changed_at": r.changed_at,
        }
        for r in rows
    ]


@router.get(
    "/{trainee_id}/consent-history",
    summary="Every consent grant / withdrawal with who recorded it and how, newest first",
)
def consent_history(trainee_id: str, db: Session = Depends(get_db)):
    trainee = _get_trainee_or_404(trainee_id, db)
    rows = (
        db.query(TraineeConsentHistory)
        .filter(TraineeConsentHistory.trainee_pk_id == trainee.id)
        .order_by(TraineeConsentHistory.id.desc())
        .all()
    )
    return [
        {
            "consent_given": r.consent_given,
            "source": r.source,
            "method": r.method,
            "recorded_by": r.recorded_by,
            "notes": r.notes,
            "changed_at": r.changed_at,
        }
        for r in rows
    ]
