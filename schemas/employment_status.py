"""
Pydantic schemas for Phase 4 — employment status history (job retention).

Each row is one status change for an employment. Old rows are never
deleted, so the sequence of rows over time is the retention timeline.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_EMPLOYMENT_STATUSES = {"Active", "Left Job", "Terminated", "On Leave", "Unknown"}


class EmploymentStatusCreate(BaseModel):
    """Body of POST /api/employment-status"""

    employment_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    employment_status: str
    status_date: date
    reason: Optional[str] = Field(None, max_length=150)
    notes: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "employment_id": "EMP000001",
                "trainee_id": "TRN000001",
                "employment_status": "Left Job",
                "status_date": "2026-12-20",
                "reason": "Better Job Opportunity",
                "notes": "Trainee changed employer.",
            }
        }
    }

    @field_validator("employment_id", "trainee_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("employment_status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        cleaned = value.strip().title()
        if cleaned not in ALLOWED_EMPLOYMENT_STATUSES:
            raise ValueError(
                f"employment_status must be one of: {', '.join(sorted(ALLOWED_EMPLOYMENT_STATUSES))}"
            )
        return cleaned


class EmploymentStatusResponse(BaseModel):
    status_record_id: str
    employment_id: str
    trainee_id: str

    employment_status: str
    status_date: date
    reason: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class EmploymentStatusHistoryListResponse(BaseModel):
    """Body of GET /api/employment/{employment_id}/status-history"""

    employment_id: str
    status_history: list[EmploymentStatusResponse]
