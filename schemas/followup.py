"""
Pydantic schemas for Phase 3 — follow-ups.

Longitudinal check-ins after a specific training: 30-day, 90-day,
6-month, 12-month. A follow-up starts out Scheduled; PATCH is used
to record what happened when it's actually carried out.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_FOLLOWUP_TYPES = {"30_DAY", "90_DAY", "6_MONTH", "12_MONTH"}
ALLOWED_FOLLOWUP_STATUSES = {"Scheduled", "Completed", "Missed", "Not Reachable"}


class FollowUpCreate(BaseModel):
    """Body of POST /api/followups"""

    trainee_id: str = Field(..., min_length=3, max_length=20)
    training_id: str = Field(..., min_length=3, max_length=20)
    followup_type: str
    scheduled_date: date
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "trainee_id": "TRN000001",
                "training_id": "TRC000001",
                "followup_type": "30_DAY",
                "scheduled_date": "2026-04-15",
                "notes": "First check-in after training completion.",
            }
        }
    }

    @field_validator("trainee_id", "training_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("followup_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned not in ALLOWED_FOLLOWUP_TYPES:
            raise ValueError(
                f"followup_type must be one of: {', '.join(sorted(ALLOWED_FOLLOWUP_TYPES))}"
            )
        return cleaned


class FollowUpUpdate(BaseModel):
    """
    Body of PATCH /api/followups/{followup_id}.

    Used to record the result of a follow-up call: mark it Completed
    or Missed, attach the completed date, link the outcome it produced.
    """

    status: Optional[str] = None
    completed_date: Optional[date] = None
    outcome_id: Optional[str] = Field(None, min_length=3, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        matched = next(
            (s for s in ALLOWED_FOLLOWUP_STATUSES if s.lower() == cleaned.lower()),
            None,
        )
        if matched is None:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(ALLOWED_FOLLOWUP_STATUSES))}"
            )
        return matched

    @field_validator("outcome_id")
    @classmethod
    def normalize_outcome_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip().upper()

    @model_validator(mode="after")
    def completed_needs_date(self) -> "FollowUpUpdate":
        if self.status == "Completed" and self.completed_date is None:
            raise ValueError("completed_date is required when marking a follow-up Completed")
        return self


class FollowUpResponse(BaseModel):
    followup_id: str
    trainee_id: str
    training_id: str
    followup_type: str
    scheduled_date: date
    completed_date: Optional[date] = None
    status: str
    outcome_id: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}
