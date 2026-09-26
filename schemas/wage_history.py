"""
Pydantic schemas for Phase 4 — wage history.

Each row is one known salary point for an employment. The original
salary on the employment record is never overwritten; every new figure
is a new row here, so progression can be reconstructed later without
any ML — see PROJECT_LOG's "Do not calculate wage progression using ML".
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_SALARY_PERIODS = {"Monthly", "Annual"}
ALLOWED_WAGE_SOURCES = {"Trainee", "Employer", "Document", "Admin"}
ALLOWED_WAGE_VERIFICATION_STATUSES = {"Unverified", "Verified"}


class WageHistoryCreate(BaseModel):
    """Body of POST /api/wage-history"""

    employment_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    salary: float = Field(..., ge=0)
    salary_period: str
    effective_date: date

    source: str
    verification_status: str = "Unverified"
    notes: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "employment_id": "EMP000001",
                "trainee_id": "TRN000001",
                "salary": 22000,
                "salary_period": "Monthly",
                "effective_date": "2026-06-15",
                "source": "Employer",
                "verification_status": "Verified",
                "notes": "Initial salary.",
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

    @field_validator("salary_period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_SALARY_PERIODS:
            raise ValueError(
                f"salary_period must be one of: {', '.join(sorted(ALLOWED_SALARY_PERIODS))}"
            )
        return cleaned

    @field_validator("source")
    @classmethod
    def valid_source(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_WAGE_SOURCES:
            raise ValueError(
                f"source must be one of: {', '.join(sorted(ALLOWED_WAGE_SOURCES))}"
            )
        return cleaned

    @field_validator("verification_status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_WAGE_VERIFICATION_STATUSES:
            raise ValueError(
                f"verification_status must be one of: {', '.join(sorted(ALLOWED_WAGE_VERIFICATION_STATUSES))}"
            )
        return cleaned


class WageHistoryResponse(BaseModel):
    wage_record_id: str
    employment_id: str
    trainee_id: str

    salary: float
    salary_period: str
    effective_date: date

    source: str
    verification_status: str
    notes: Optional[str] = None

    # Joined from the trainee / employment record (list endpoint only)
    trainee_name: Optional[str] = None
    company_name: Optional[str] = None
    job_role: Optional[str] = None

    model_config = {"from_attributes": True}


class WageHistoryListResponse(BaseModel):
    """Body of GET /api/employment/{employment_id}/wage-history"""

    employment_id: str
    wage_history: list[WageHistoryResponse]
