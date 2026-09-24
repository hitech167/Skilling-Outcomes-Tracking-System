"""
Shared lookup helpers for Phase 3 routes.

Phase 1's routes/trainees.py and Phase 2's routes/training_records.py
already define their own local versions of "get X or 404" — this module
exists so the five new Phase 3 route files don't each re-implement the
same lookups, without touching those earlier files.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import EmploymentRecord, Outcome, Trainee, TrainingRecord


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


def get_training_record_or_404(training_id: str, db: Session) -> TrainingRecord:
    record = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.record_id == training_id.strip().upper())
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No training record found with ID {training_id}",
        )
    return record


def get_outcome_or_404(outcome_id: str, db: Session) -> Outcome:
    outcome = (
        db.query(Outcome)
        .filter(Outcome.outcome_id == outcome_id.strip().upper())
        .first()
    )
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No outcome found with ID {outcome_id}",
        )
    return outcome


def get_employment_or_404(employment_id: str, db: Session) -> EmploymentRecord:
    """
    Phase 4 helper — looks up an employment_records row by its public
    EMP0000xx id. Added here (rather than duplicated in each of the three
    new Phase 4 route files) the same way the Phase 3 lookups above were.
    """
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
    return record
