"""
Pydantic schemas for Phase 3 — self-employment detail records.

One of these is created against an outcome whose outcome_type is
'Self-employed'.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SelfEmploymentCreate(BaseModel):
    """Body of POST /api/self-employment"""

    outcome_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    business_name: str = Field(..., min_length=2, max_length=200)
    business_type: str = Field(..., min_length=2, max_length=150)
    start_date: date
    monthly_income: Optional[float] = Field(None, ge=0)
    location: Optional[str] = Field(None, max_length=150)
    number_of_workers: Optional[int] = Field(None, ge=0)

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_id": "OUT000002",
                "trainee_id": "TRN000002",
                "business_name": "Sharma Tailoring Works",
                "business_type": "Tailoring & Alterations",
                "start_date": "2026-07-01",
                "monthly_income": 15000,
                "location": "Raigad",
                "number_of_workers": 1,
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

    @field_validator("business_name", "business_type")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned


class SelfEmploymentResponse(BaseModel):
    self_employment_id: str
    outcome_id: str
    trainee_id: str
    business_name: str
    business_type: str
    start_date: date
    monthly_income: Optional[float] = None
    location: Optional[str] = None
    number_of_workers: Optional[int] = None

    model_config = {"from_attributes": True}
