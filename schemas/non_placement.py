"""
Pydantic schemas for Phase 3 — non-placement (unemployed) detail records.

One of these is created against an outcome whose outcome_type is
'Unemployed'. Structured reason category first — no ML classification
of free-text reasons yet, per the spec.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_REASON_CATEGORIES = {
    "Skill Gap",
    "Lack of Jobs",
    "Low Salary",
    "Location Problem",
    "Relocation Issue",
    "Personal/Family Reason",
    "Further Education",
    "Other",
}


class NonPlacementCreate(BaseModel):
    """Body of POST /api/non-placement"""

    outcome_id: str = Field(..., min_length=3, max_length=20)
    trainee_id: str = Field(..., min_length=3, max_length=20)

    reason_category: str
    reason_details: Optional[str] = Field(None, max_length=2000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "outcome_id": "OUT000004",
                "trainee_id": "TRN000004",
                "reason_category": "Lack of Jobs",
                "reason_details": "No openings matching the trainee's skill set in the district.",
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

    @field_validator("reason_category")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        cleaned = value.strip()
        matched = next(
            (r for r in ALLOWED_REASON_CATEGORIES if r.lower() == cleaned.lower()),
            None,
        )
        if matched is None:
            raise ValueError(
                f"reason_category must be one of: {', '.join(sorted(ALLOWED_REASON_CATEGORIES))}"
            )
        return matched


class NonPlacementResponse(BaseModel):
    non_placement_id: str
    outcome_id: str
    trainee_id: str
    reason_category: str
    reason_details: Optional[str] = None

    model_config = {"from_attributes": True}
