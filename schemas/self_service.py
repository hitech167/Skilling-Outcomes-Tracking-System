"""
Schemas for the low-burden, link-based channels:

- trainee self-report (one link per follow-up, no login)
- employer confirmation (one link per verification request, no login)
- admin endpoints that create links / dispatch follow-ups / manage the outbox
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.non_placement import ALLOWED_REASON_CATEGORIES
from schemas.outcome import ALLOWED_OUTCOME_TYPES

PLACEMENT_TYPES = {"Employed", "Self-employed", "Apprenticeship"}
EMPLOYER_STATUSES = {"Active", "Left Job", "Terminated", "On Leave"}


def _match(value: Optional[str], allowed: set, field: str) -> Optional[str]:
    if value is None:
        return None
    matched = next((a for a in allowed if a.lower() == value.strip().lower()), None)
    if matched is None:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return matched


# ---------------------------------------------------------------------
# Trainee self-report
# ---------------------------------------------------------------------


class SelfReportContext(BaseModel):
    """What the trainee sees on the form — no contact details or IDs."""

    first_name: str
    course_name: str
    provider_name: str
    followup_type: str
    already_submitted: bool


class SelfReportSubmission(BaseModel):
    outcome_type: str
    # Employer (Employed) / business name (Self-employed) / organisation (Apprenticeship)
    organisation_name: Optional[str] = Field(None, max_length=200)
    # Job role / business type / apprentice role
    role: Optional[str] = Field(None, max_length=150)
    start_date: Optional[date] = None
    # Monthly salary / business income / stipend, in rupees
    monthly_income: Optional[float] = Field(None, ge=0, le=10_000_000)
    training_relevance: Optional[int] = Field(None, ge=1, le=5)
    skill_gap: Optional[bool] = None
    additional_training_needed: Optional[bool] = None
    unemployment_reason: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_type": "Employed",
                "organisation_name": "Volt Works Pvt Ltd",
                "role": "Junior Electrician",
                "start_date": "2025-05-15",
                "monthly_income": 18000,
                "training_relevance": 4,
                "skill_gap": False,
                "additional_training_needed": True,
            }
        }
    }

    @field_validator("outcome_type")
    @classmethod
    def valid_outcome(cls, value: str) -> str:
        return _match(value, ALLOWED_OUTCOME_TYPES, "outcome_type")

    @field_validator("unemployment_reason")
    @classmethod
    def valid_reason(cls, value: Optional[str]) -> Optional[str]:
        return _match(value, ALLOWED_REASON_CATEGORIES, "unemployment_reason")

    @field_validator("organisation_name", "role", "notes")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def details_for_placements(self) -> "SelfReportSubmission":
        if self.outcome_type in PLACEMENT_TYPES and not (self.organisation_name and self.role):
            raise ValueError(
                "organisation_name and role are required when you are employed, "
                "self-employed or in an apprenticeship"
            )
        if self.start_date and self.start_date > date.today():
            raise ValueError("start_date cannot be in the future")
        return self


class SelfReportResult(BaseModel):
    success: bool = True
    message: str = "Thank you — your update has been recorded."


# ---------------------------------------------------------------------
# Employer confirmation
# ---------------------------------------------------------------------


class EmployerVerifyContext(BaseModel):
    """The minimum an employer needs to identify the employee."""

    company_name: str
    employee_name: str
    job_role: str
    joining_date: date
    already_submitted: bool


class EmployerVerifySubmission(BaseModel):
    employment_confirmed: bool
    current_status: Optional[str] = None
    salary: Optional[float] = Field(None, ge=0, le=100_000_000)
    salary_period: Optional[str] = "Monthly"
    verified_by: str = Field(..., min_length=2, max_length=150)
    notes: Optional[str] = Field(None, max_length=1000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "employment_confirmed": True,
                "current_status": "Active",
                "salary": 19500,
                "salary_period": "Monthly",
                "verified_by": "R. Deshmukh, HR Manager",
            }
        }
    }

    @field_validator("current_status")
    @classmethod
    def valid_status(cls, value: Optional[str]) -> Optional[str]:
        return _match(value, EMPLOYER_STATUSES, "current_status")

    @field_validator("salary_period")
    @classmethod
    def valid_period(cls, value: Optional[str]) -> Optional[str]:
        return _match(value, {"Monthly", "Annual"}, "salary_period")

    @field_validator("verified_by")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("verified_by cannot be empty")
        return value.strip()


class EmployerVerifyResult(BaseModel):
    success: bool = True
    verification_status: str
    message: str = "Thank you — the confirmation has been recorded."


# ---------------------------------------------------------------------
# Admin: links, dispatch, outbox
# ---------------------------------------------------------------------


class SelfReportLinkResponse(BaseModel):
    followup_id: str
    link: str
    valid_days: int


class VerificationRequestCreate(BaseModel):
    """Body of POST /api/employment/{employment_id}/verification-request"""

    employer_contact: Optional[str] = Field(None, max_length=255)

    model_config = {"json_schema_extra": {"example": {"employer_contact": "hr@voltworks.example"}}}


class VerificationRequestResponse(BaseModel):
    verification_id: str
    employment_id: str
    link: str
    valid_days: int
    notification_id: Optional[str] = None
    delivery_status: Optional[str] = None


class DispatchSummary(BaseModel):
    due_followups: int
    sent: int
    queued: int
    failed: int
    skipped_no_consent: int
    skipped_recently_contacted: int
    # Older overdue check-ins of a training that already gets a message
    skipped_superseded: int = 0
    notification_ids: list[str]


class NotificationItem(BaseModel):
    notification_id: str
    trainee_id: str
    trainee_name: Optional[str] = None
    followup_id: Optional[str] = None
    purpose: str
    channel: str
    recipient: str
    message: str
    status: str
    provider: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
