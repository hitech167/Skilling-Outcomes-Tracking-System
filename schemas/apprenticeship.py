"""
Pydantic schemas for Phase 3 — apprenticeship detail records.

One of these is created against an outcome whose outcome_type is
'Apprenticeship'.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ApprenticeshipCreate(BaseModel):
    """Body of POST /api/apprenticeships"""

    outcome_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    organization_name: str = Field(..., min_length=2, max_length=200)
    role: str = Field(..., min_length=2, max_length=150)
    start_date: date
    end_date: Optional[date] = None
    monthly_stipend: Optional[float] = Field(None, ge=0)
    location: Optional[str] = Field(None, max_length=150)

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_id": "OUT000003",
                "trainee_id": "TRN000003",
                "organization_name": "Mahindra Logistics",
                "role": "Apprentice Technician",
                "start_date": "2026-07-01",
                "end_date": "2027-06-30",
                "monthly_stipend": 9000,
                "location": "Nagpur",
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

    @field_validator("organization_name", "role")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @model_validator(mode="after")
    def check_dates(self) -> "ApprenticeshipCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ApprenticeshipResponse(BaseModel):
    apprenticeship_id: str
    outcome_id: str
    trainee_id: str
    organization_name: str
    role: str
    start_date: date
    end_date: Optional[date] = None
    monthly_stipend: Optional[float] = None
    location: Optional[str] = None

    model_config = {"from_attributes": True}
