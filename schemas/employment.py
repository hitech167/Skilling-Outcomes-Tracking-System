"""
Pydantic schemas for Phase 3 — employment detail records.

One of these is created against an outcome whose outcome_type is
'Employed'. Company/salary/role detail lives here, not in outcomes.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_EMPLOYMENT_STATUSES = {"Active", "Left", "Terminated"}
ALLOWED_RELEVANCE = {"Relevant", "Partially Relevant", "Not Relevant"}


class EmploymentCreate(BaseModel):
    """Body of POST /api/employment"""

    outcome_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    company_name: str = Field(..., min_length=2, max_length=200)
    job_role: str = Field(..., min_length=2, max_length=150)
    joining_date: date
    salary: Optional[float] = Field(None, ge=0)
    employment_status: str = "Active"
    job_location: Optional[str] = Field(None, max_length=150)
    job_relevance: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_id": "OUT000001",
                "trainee_id": "TRN000001",
                "company_name": "ABC Technologies Pvt Ltd",
                "job_role": "Junior Python Developer",
                "joining_date": "2026-06-20",
                "salary": 22000,
                "employment_status": "Active",
                "job_location": "Pune",
                "job_relevance": "Relevant",
            }
        }
    }

    @field_validator("outcome_id", "trainee_id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("company_name", "job_role")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("employment_status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        if cleaned not in ALLOWED_EMPLOYMENT_STATUSES:
            raise ValueError(
                f"employment_status must be one of: {', '.join(sorted(ALLOWED_EMPLOYMENT_STATUSES))}"
            )
        return cleaned

    @field_validator("job_relevance")
    @classmethod
    def valid_relevance(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip().title()
        if cleaned not in ALLOWED_RELEVANCE:
            raise ValueError(
                f"job_relevance must be one of: {', '.join(sorted(ALLOWED_RELEVANCE))}"
            )
        return cleaned


class EmploymentResponse(BaseModel):
    employment_id: str
    outcome_id: str
    trainee_id: str
    company_name: str
    job_role: str
    joining_date: date
    salary: Optional[float] = None
    employment_status: str
    job_location: Optional[str] = None
    job_relevance: Optional[str] = None

    model_config = {"from_attributes": True}
