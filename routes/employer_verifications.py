"""
Employer verification routes — Phase 4.

POST /api/employer-verifications                    -> create a verification record
GET  /api/employer-verifications/{verification_id}  -> get one verification record
GET  /api/employment/{employment_id}/verification    -> get the latest verification for an employment

No employer portal exists yet — this just stores verification
information so a future portal can use it (see PROJECT_LOG "DO NOT
BUILD YET"). Multiple verification attempts per employment are
supported and kept as history; nothing is overwritten (design note is
on database/models.py:EmployerVerification).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import EmployerVerification
from routes._shared import get_employment_or_404, get_trainee_or_404
from schemas.employer_verification import (
    EmployerVerificationCreate,
    EmployerVerificationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Employer Verification"])


def generate_verification_id(db: Session) -> str:
    next_number = db.execute(
        text("SELECT nextval('employer_verification_id_seq')")
    ).scalar()
    return f"VER{next_number:06d}"


def to_response(
    record: EmployerVerification, employment_public_id: str, trainee_public_id: str
) -> EmployerVerificationResponse:
    return EmployerVerificationResponse(
        verification_id=record.verification_id,
        employment_id=employment_public_id,
        trainee_id=trainee_public_id,
        employer_name=record.employer_name,
        employer_contact=record.employer_contact,
        verification_status=record.verification_status,
        verification_method=record.verification_method,
        verified_date=record.verified_date,
        verified_by=record.verified_by,
        verification_notes=record.verification_notes,
    )


@router.post(
    "/api/employer-verifications",
    response_model=EmployerVerificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employer verification record for an employment",
)
def create_employer_verification(
    payload: EmployerVerificationCreate, db: Session = Depends(get_db)
):
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
        record = EmployerVerification(
            verification_id=generate_verification_id(db),
            employment_pk_id=employment.id,
            trainee_pk_id=trainee.id,
            employer_name=payload.employer_name,
            employer_contact=payload.employer_contact,
            verification_status=payload.verification_status,
            verification_method=payload.verification_method,
            verified_date=payload.verified_date,
            verified_by=payload.verified_by,
            verification_notes=payload.verification_notes,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating an employer verification")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info(
        "Created employer verification %s for employment %s",
        record.verification_id,
        employment.employment_id,
    )

    return to_response(record, employment.employment_id, trainee.trainee_id)


@router.get(
    "/api/employer-verifications/{verification_id}",
    response_model=EmployerVerificationResponse,
    summary="Get a single employer verification record",
)
def get_employer_verification(verification_id: str, db: Session = Depends(get_db)):
    from database.models import EmploymentRecord, Trainee

    record = (
        db.query(EmployerVerification)
        .filter(EmployerVerification.verification_id == verification_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verification record found with ID {verification_id}",
        )

    employment = (
        db.query(EmploymentRecord)
        .filter(EmploymentRecord.id == record.employment_pk_id)
        .first()
    )
    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()

    return to_response(record, employment.employment_id, trainee.trainee_id)


@router.get(
    "/api/employment/{employment_id}/verification",
    response_model=EmployerVerificationResponse,
    summary="Get the latest verification record for an employment",
)
def get_verification_for_employment(employment_id: str, db: Session = Depends(get_db)):
    from database.models import Trainee

    employment = get_employment_or_404(employment_id, db)

    record = (
        db.query(EmployerVerification)
        .filter(EmployerVerification.employment_pk_id == employment.id)
        .order_by(EmployerVerification.id.desc())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No verification record found for employment {employment_id}",
        )

    trainee = db.query(Trainee).filter(Trainee.id == record.trainee_pk_id).first()

    return to_response(record, employment.employment_id, trainee.trainee_id)
