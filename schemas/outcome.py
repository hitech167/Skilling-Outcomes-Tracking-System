"""
Pydantic schemas for Phase 3 — outcomes.

An outcome identifies WHAT happened to a trainee after a specific
training (job, self-employed, apprenticeship, unemployed, further
education, or not reachable). It deliberately carries no company/salary/
business detail — those live in their own detail-record schemas.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_OUTCOME_TYPES = {
    "Employed",
    "Self-employed",
    "Apprenticeship",
    "Unemployed",
    "Further Education",
    "Not Reachable",
}


class OutcomeCreate(BaseModel):
    """Body of POST /api/outcomes"""

    trainee_id: str = Field(..., min_length=3, max_length=20)
    training_id: str = Field(..., min_length=3, max_length=20)
    outcome_type: str
    status_date: date
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "trainee_id": "TRN000001",
                "training_id": "TRC000001",
                "outcome_type": "Employed",
                "status_date": "2026-06-15",
                "notes": "Trainee started employment after completing training.",
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

    @field_validator("outcome_type")
    @classmethod
    def valid_outcome_type(cls, value: str) -> str:
        cleaned = value.strip()
        # Accept common casing variants, then check against the canonical set
        matched = next(
            (t for t in ALLOWED_OUTCOME_TYPES if t.lower() == cleaned.lower()), None
        )
        if matched is None:
            raise ValueError(
                f"outcome_type must be one of: {', '.join(sorted(ALLOWED_OUTCOME_TYPES))}"
            )
        return matched


class OutcomeResponse(BaseModel):
    """Response shape for a single outcome."""

    outcome_id: str
    trainee_id: str
    training_id: str
    outcome_type: str
    status_date: date
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class OutcomeSummary(BaseModel):
    """Slim shape used inside the trainee outcomes list."""

    outcome_id: str
    training_id: str
    outcome_type: str
    status_date: date


class TraineeOutcomesResponse(BaseModel):
    """Response of GET /api/trainees/{trainee_id}/outcomes"""

    trainee_id: str
    outcomes: list[OutcomeSummary]
