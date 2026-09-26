"""
Pydantic schemas for Phase 4 — employer verification.

Verifies whether an employment_records row is genuine, and by whom /
how. Multiple verification attempts per employment are allowed (history
is kept, never overwritten) — see database/models.py:EmployerVerification
for the design note on why.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_VERIFICATION_STATUSES = {"Pending", "Verified", "Rejected", "Unable to Verify"}
ALLOWED_VERIFICATION_METHODS = {
    "Employer Portal",
    "Employer Contact",
    "Document",
    "Trainee Confirmation",
    "Admin Verification",
}


class EmployerVerificationCreate(BaseModel):
    """Body of POST /api/employer-verifications"""

    employment_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    employer_name: str = Field(..., min_length=2, max_length=200)
    employer_contact: Optional[str] = Field(None, max_length=255)

    verification_status: str = "Pending"
    verification_method: str

    verified_date: Optional[date] = None
    verified_by: Optional[str] = Field(None, max_length=150)
    verification_notes: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "employment_id": "EMP000001",
                "trainee_id": "TRN000001",
                "employer_name": "ABC Technologies",
                "employer_contact": "hr@abctech.com",
                "verification_status": "Verified",
                "verification_method": "Employer Contact",
                "verified_date": "2026-08-10",
                "verified_by": "Admin",
                "verification_notes": "Employment confirmed by HR.",
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

    @field_validator("employer_name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("verification_status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        cleaned = value.strip().title()
        # "Unable To Verify".title() -> "Unable To Verify"; normalise "To" -> "to"
        if cleaned == "Unable To Verify":
            cleaned = "Unable to Verify"
        if cleaned not in ALLOWED_VERIFICATION_STATUSES:
            raise ValueError(
                f"verification_status must be one of: {', '.join(sorted(ALLOWED_VERIFICATION_STATUSES))}"
            )
        return cleaned

    @field_validator("verification_method")
    @classmethod
    def valid_method(cls, value: str) -> str:
        cleaned = value.strip().title()
        if cleaned not in ALLOWED_VERIFICATION_METHODS:
            raise ValueError(
                f"verification_method must be one of: {', '.join(sorted(ALLOWED_VERIFICATION_METHODS))}"
            )
        return cleaned


class EmployerVerificationResponse(BaseModel):
    verification_id: str
    employment_id: str
    trainee_id: str

    employer_name: str
    employer_contact: Optional[str] = None

    verification_status: str
    verification_method: str

    verified_date: Optional[date] = None
    verified_by: Optional[str] = None
    verification_notes: Optional[str] = None

    # Joined from the trainee / employment record for display
    trainee_name: Optional[str] = None
    job_role: Optional[str] = None
    salary: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
