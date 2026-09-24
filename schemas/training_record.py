"""
Pydantic schemas for Phase 2 — training records.

A training record links a trainee to one course/program they took with a
provider, and carries attendance, assessment and certification info for
that course. A trainee can have many of these.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_STATUSES = {"Enrolled", "Ongoing", "Completed", "Dropped"}
ALLOWED_ASSESSMENT_STATUSES = {"Pending", "Passed", "Failed"}


def _clean_assessment_status(value):
    if value is None:
        return value
    cleaned = value.strip().capitalize()
    if cleaned not in ALLOWED_ASSESSMENT_STATUSES:
        raise ValueError(
            f"assessment_status must be one of: {', '.join(sorted(ALLOWED_ASSESSMENT_STATUSES))}"
        )
    return cleaned


class TrainingRecordCreate(BaseModel):
    """Body of POST /api/trainees/{trainee_id}/training-records"""

    program_name: Optional[str] = Field(None, max_length=200)
    course_name: str = Field(..., min_length=2, max_length=200)
    provider_name: str = Field(..., min_length=2, max_length=200)

    start_date: date
    end_date: Optional[date] = None

    status: str = "Enrolled"

    attendance_percentage: Optional[float] = Field(None, ge=0, le=100)
    assessment_score: Optional[float] = Field(None, ge=0, le=100)
    assessment_status: Optional[str] = None

    certification_issued: bool = False
    certification_id: Optional[str] = Field(None, max_length=50)

    model_config = {
        "json_schema_extra": {
            "example": {
                "program_name": "PMKVY 4.0",
                "course_name": "Python Development",
                "provider_name": "NSDC Skill Center",
                "start_date": "2025-01-10",
                "end_date": "2025-03-10",
                "status": "Completed",
                "attendance_percentage": 92.5,
                "assessment_score": 88,
                "assessment_status": "Passed",
                "certification_issued": True,
                "certification_id": "CERT-PY-2025-0456",
            }
        }
    }

    @field_validator("course_name", "provider_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        return cleaned

    @field_validator("assessment_status")
    @classmethod
    def valid_assessment_status(cls, value: Optional[str]) -> Optional[str]:
        return _clean_assessment_status(value)

    @field_validator("program_name")
    @classmethod
    def blank_program_is_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip() or None

    @model_validator(mode="after")
    def check_dates_and_certification(self) -> "TrainingRecordCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")

        if self.certification_issued and self.status != "Completed":
            raise ValueError(
                "certification_issued can only be true when status is 'Completed'"
            )

        return self


class TrainingRecordUpdate(BaseModel):
    """
    Body of PATCH /api/training-records/{record_id}.

    All fields optional — send only what changed (e.g. marking a course
    Completed once the trainee finishes it).
    """

    program_name: Optional[str] = Field(None, max_length=200)
    end_date: Optional[date] = None
    status: Optional[str] = None
    attendance_percentage: Optional[float] = Field(None, ge=0, le=100)
    assessment_score: Optional[float] = Field(None, ge=0, le=100)
    assessment_status: Optional[str] = None
    certification_issued: Optional[bool] = None
    certification_id: Optional[str] = Field(None, max_length=50)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
            )
        return cleaned

    @field_validator("assessment_status")
    @classmethod
    def valid_assessment_status(cls, value: Optional[str]) -> Optional[str]:
        return _clean_assessment_status(value)


class TrainingRecordResponse(BaseModel):
    """Response shape for a single training record."""

    record_id: str
    trainee_id: str
    program_name: Optional[str] = None
    course_name: str
    provider_name: str
    start_date: date
    end_date: Optional[date] = None
    status: str
    attendance_percentage: Optional[float] = None
    assessment_score: Optional[float] = None
    assessment_status: Optional[str] = None
    certification_issued: bool
    certification_id: Optional[str] = None

    model_config = {"from_attributes": True}
