"""
Training record routes — Phase 2.

POST   /api/trainees/{trainee_id}/training-records   -> add a training record
GET    /api/trainees/{trainee_id}/training-records    -> list a trainee's records
GET    /api/training-records/{record_id}              -> get one record
PATCH  /api/training-records/{record_id}               -> update one record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Trainee, TrainingRecord
from schemas.training_record import (
    TrainingRecordCreate,
    TrainingRecordResponse,
    TrainingRecordUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Training Records"])


def generate_record_id(db: Session) -> str:
    """Next number from training_record_id_seq, formatted as TRC000001."""
    next_number = db.execute(
        text("SELECT nextval('training_record_id_seq')")
    ).scalar()
    return f"TRC{next_number:06d}"


def get_trainee_or_404(trainee_id: str, db: Session) -> Trainee:
    trainee = (
        db.query(Trainee)
        .filter(Trainee.trainee_id == trainee_id.strip().upper())
        .first()
    )
    if trainee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trainee found with ID {trainee_id}",
        )
    return trainee


def get_record_or_404(record_id: str, db: Session) -> TrainingRecord:
    record = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.record_id == record_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No training record found with ID {record_id}",
        )
    return record


def to_response(record: TrainingRecord) -> TrainingRecordResponse:
    """Build the API response, pulling the public trainee_id via the relationship."""
    return TrainingRecordResponse(
        record_id=record.record_id,
        trainee_id=record.trainee.trainee_id,
        program_name=record.program_name,
        course_name=record.course_name,
        provider_name=record.provider_name,
        start_date=record.start_date,
        end_date=record.end_date,
        status=record.status,
        attendance_percentage=record.attendance_percentage,
        assessment_score=record.assessment_score,
        assessment_status=record.assessment_status,
        certification_issued=record.certification_issued,
        certification_id=record.certification_id,
    )


@router.post(
    "/api/trainees/{trainee_id}/training-records",
    response_model=TrainingRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a training record for a trainee",
)
def create_training_record(
    trainee_id: str, payload: TrainingRecordCreate, db: Session = Depends(get_db)
):
    trainee = get_trainee_or_404(trainee_id, db)

    try:
        record = TrainingRecord(
            record_id=generate_record_id(db),
            trainee_pk_id=trainee.id,
            program_name=payload.program_name,
            course_name=payload.course_name,
            provider_name=payload.provider_name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            status=payload.status,
            attendance_percentage=payload.attendance_percentage,
            assessment_score=payload.assessment_score,
            assessment_status=payload.assessment_status,
            certification_issued=payload.certification_issued,
            certification_id=payload.certification_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating a training record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )

    logger.info("Created training record %s for %s", record.record_id, trainee.trainee_id)

    return to_response(record)


@router.get(
    "/api/trainees/{trainee_id}/training-records",
    response_model=list[TrainingRecordResponse],
    summary="List all training records for a trainee",
)
def list_training_records(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)

    records = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.trainee_pk_id == trainee.id)
        .order_by(TrainingRecord.start_date)
        .all()
    )

    return [to_response(r) for r in records]


@router.get(
    "/api/training-records/{record_id}",
    response_model=TrainingRecordResponse,
    summary="Get a single training record",
)
def get_training_record(record_id: str, db: Session = Depends(get_db)):
    record = get_record_or_404(record_id, db)
    return to_response(record)


@router.patch(
    "/api/training-records/{record_id}",
    response_model=TrainingRecordResponse,
    summary="Update a training record (e.g. mark it Completed)",
)
def update_training_record(
    record_id: str, payload: TrainingRecordUpdate, db: Session = Depends(get_db)
):
    record = get_record_or_404(record_id, db)

    updates = payload.model_dump(exclude_unset=True)

    # Re-validate the same cross-field rules as on create, using the record's
    # values merged with whatever is being changed.
    new_status = updates.get("status", record.status)
    new_end_date = updates.get("end_date", record.end_date)
    new_cert_issued = updates.get("certification_issued", record.certification_issued)

    if new_end_date is not None and new_end_date < record.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date cannot be before start_date",
        )

    # status and certification_issued are NOT NULL columns
    for field in ("status", "certification_issued"):
        if field in updates and updates[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be null",
            )

    if new_cert_issued and new_status != "Completed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="certification_issued can only be true when status is 'Completed'",
        )

    for field, value in updates.items():
        setattr(record, field, value)

    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while updating a training record")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not update the record right now. Please try again.",
        )

    logger.info("Updated training record %s", record.record_id)

    return to_response(record)


class TrainingRecordCreateStandalone(TrainingRecordCreate):
    trainee_id: str


@router.post(
    "/api/trainees/{trainee_id}/training",
    response_model=TrainingRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a training record for a trainee (alias)",
)
def create_training_record_alias(
    trainee_id: str, payload: TrainingRecordCreate, db: Session = Depends(get_db)
):
    return create_training_record(trainee_id, payload, db)


@router.post(
    "/api/training",
    response_model=TrainingRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training record (standalone)",
)
def create_training_standalone(
    payload: TrainingRecordCreateStandalone, db: Session = Depends(get_db)
):
    return create_training_record(payload.trainee_id, payload, db)


@router.get(
    "/api/training/{record_id}",
    response_model=TrainingRecordResponse,
    summary="Get a single training record (alias)",
)
def get_training_record_alias(record_id: str, db: Session = Depends(get_db)):
    return get_training_record(record_id, db)


@router.get(
    "/api/trainees/{trainee_id}/training",
    response_model=list[TrainingRecordResponse],
    summary="List all training records for a trainee (alias)",
)
def list_training_records_alias(trainee_id: str, db: Session = Depends(get_db)):
    return list_training_records(trainee_id, db)

