"""
Pydantic schemas for Phase 5 — automated + assisted follow-up tracking.

Covers: schedule generation, pending/upcoming/overdue lists, completing
or missing a follow-up, contact attempts, the trainee's current-situation
outcome update, and the follow-up/admin summaries.

Reuses the reason-category and outcome-type vocabularies already defined
in Phase 3 (schemas/non_placement.py, schemas/outcome.py) instead of
redefining them.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.non_placement import ALLOWED_REASON_CATEGORIES
from schemas.outcome import ALLOWED_OUTCOME_TYPES

ALLOWED_CONTACT_METHODS = {"Phone", "SMS", "WhatsApp", "Email", "In Person", "Other"}
ALLOWED_ATTEMPT_STATUSES = {
    "Successful",
    "No Response",
    "Busy",
    "Invalid Contact",
    "Not Reachable",
    "Other",
}


# ---------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------


class FollowUpGenerateResponse(BaseModel):
    success: bool
    training_id: str
    followups_created: int
    message: str


# ---------------------------------------------------------------------
# Pending / upcoming / overdue lists
# ---------------------------------------------------------------------


class FollowUpListItem(BaseModel):
    """Used for pending and upcoming lists (no PII)."""

    followup_id: str
    trainee_id: str
    training_id: str
    followup_type: str
    scheduled_date: date
    status: str

    model_config = {"from_attributes": True}


class OverdueFollowUpItem(BaseModel):
    followup_id: str
    trainee_id: str
    training_id: str
    followup_type: str
    scheduled_date: date
    days_overdue: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------
# Complete / missed / not-reachable
# ---------------------------------------------------------------------


class FollowUpCompleteRequest(BaseModel):
    completed_date: date
    status: str = "Completed"
    notes: Optional[str] = Field(None, max_length=2000)
    outcome_id: Optional[str] = Field(None, min_length=3, max_length=20)

    @field_validator("status")
    @classmethod
    def must_be_completed(cls, value: str) -> str:
        if value.strip().lower() != "completed":
            raise ValueError("status must be 'Completed' for this endpoint")
        return "Completed"

    @field_validator("outcome_id")
    @classmethod
    def normalize_outcome_id(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().upper() if value else value


class FollowUpMissedRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class FollowUpNotReachableRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


# ---------------------------------------------------------------------
# Follow-up attempts
# ---------------------------------------------------------------------


class FollowUpAttemptCreate(BaseModel):
    attempt_date: date
    contact_method: str
    attempt_status: str
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "attempt_date": "2026-09-23",
                "contact_method": "Phone",
                "attempt_status": "No Response",
                "notes": "Called twice but no response.",
            }
        }
    }

    @field_validator("contact_method")
    @classmethod
    def valid_contact_method(cls, value: str) -> str:
        matched = next(
            (m for m in ALLOWED_CONTACT_METHODS if m.lower() == value.strip().lower()), None
        )
        if matched is None:
            raise ValueError(
                f"contact_method must be one of: {', '.join(sorted(ALLOWED_CONTACT_METHODS))}"
            )
        return matched

    @field_validator("attempt_status")
    @classmethod
    def valid_attempt_status(cls, value: str) -> str:
        matched = next(
            (s for s in ALLOWED_ATTEMPT_STATUSES if s.lower() == value.strip().lower()), None
        )
        if matched is None:
            raise ValueError(
                f"attempt_status must be one of: {', '.join(sorted(ALLOWED_ATTEMPT_STATUSES))}"
            )
        return matched


class FollowUpAttemptResponse(BaseModel):
    attempt_id: str
    followup_id: str
    attempt_date: date
    contact_method: str
    attempt_status: str
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------
# Outcome update (trainee's current situation)
# ---------------------------------------------------------------------


class FollowUpOutcomeUpdateCreate(BaseModel):
    employment_status: str
    training_relevance: Optional[int] = Field(None, ge=1, le=5)
    skill_gap: Optional[bool] = None
    additional_training_needed: Optional[bool] = None
    unemployment_reason_category: Optional[str] = None
    unemployment_reason_details: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "employment_status": "Employed",
                "training_relevance": 4,
                "skill_gap": False,
                "additional_training_needed": False,
                "notes": "Trainee is still working at the same company.",
            }
        }
    }

    @field_validator("employment_status")
    @classmethod
    def valid_employment_status(cls, value: str) -> str:
        matched = next(
            (t for t in ALLOWED_OUTCOME_TYPES if t.lower() == value.strip().lower()), None
        )
        if matched is None:
            raise ValueError(
                f"employment_status must be one of: {', '.join(sorted(ALLOWED_OUTCOME_TYPES))}"
            )
        return matched

    @field_validator("unemployment_reason_category")
    @classmethod
    def valid_reason_category(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        matched = next(
            (r for r in ALLOWED_REASON_CATEGORIES if r.lower() == value.strip().lower()), None
        )
        if matched is None:
            raise ValueError(
                f"unemployment_reason_category must be one of: "
                f"{', '.join(sorted(ALLOWED_REASON_CATEGORIES))}"
            )
        return matched

    @model_validator(mode="after")
    def reason_only_when_unemployed(self) -> "FollowUpOutcomeUpdateCreate":
        # Do not require a reason for employed trainees; don't accept one either
        # unless the trainee is actually unemployed, to keep the data clean.
        if self.employment_status != "Unemployed" and (
            self.unemployment_reason_category or self.unemployment_reason_details
        ):
            raise ValueError(
                "unemployment_reason_category / unemployment_reason_details are only "
                "valid when employment_status is 'Unemployed'"
            )
        return self


class FollowUpOutcomeUpdateResponse(BaseModel):
    update_id: str
    followup_id: str
    employment_status: str
    training_relevance: Optional[int] = None
    skill_gap: Optional[bool] = None
    additional_training_needed: Optional[bool] = None
    unemployment_reason_category: Optional[str] = None
    unemployment_reason_details: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------
# Summaries / timeline
# ---------------------------------------------------------------------


class FollowUpSummaryResponse(BaseModel):
    followup_id: str
    trainee_id: str
    training_id: str
    followup_type: str
    scheduled_date: date
    completed_date: Optional[date] = None
    status: str
    attempt_count: int
    latest_attempt: Optional[FollowUpAttemptResponse] = None
    current_outcome: Optional[FollowUpOutcomeUpdateResponse] = None


class TraineeFollowupTimelineItem(BaseModel):
    followup_id: str
    training_id: str
    followup_type: str
    scheduled_date: date
    completed_date: Optional[date] = None
    status: str


class TraineeFollowupTimelineResponse(BaseModel):
    trainee_id: str
    followups: list[TraineeFollowupTimelineItem]


class AdminFollowUpSummaryResponse(BaseModel):
    total: int
    scheduled: int
    completed: int
    missed: int
    not_reachable: int
    overdue: int
    upcoming_7_days: int
