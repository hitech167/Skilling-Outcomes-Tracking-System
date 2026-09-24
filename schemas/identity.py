"""
Pydantic schemas for cross-programme identity (external IDs + duplicate checks).

Different programmes identify the same person differently (Skill India
Digital ID, PMKVY candidate ID, state-scheme registration numbers...).
These are stored as (id_type, id_value) pairs linked to the one stable
internal trainee_id.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ExternalIdCreate(BaseModel):
    id_type: str = Field(..., min_length=2, max_length=60)
    id_value: str = Field(..., min_length=1, max_length=100)
    source_programme: Optional[str] = Field(None, max_length=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_type": "Skill India Digital ID",
                "id_value": "SID-2025-00012345",
                "source_programme": "PMKVY 4.0",
            }
        }
    }

    @field_validator("id_type")
    @classmethod
    def clean_type(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("id_type cannot be empty")
        # Aadhaar numbers must not be stored by programmes (Aadhaar Act,
        # s.29 / UIDAI regulations) — use a scheme or Skill India ID instead.
        if "aadhaar" in cleaned.lower() or "aadhar" in cleaned.lower():
            raise ValueError("Aadhaar numbers must not be stored; use a programme or Skill India ID")
        return cleaned

    @field_validator("id_value")
    @classmethod
    def clean_value(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("id_value cannot be empty")
        if re.fullmatch(r"\d{12}", re.sub(r"[\s-]", "", cleaned)):
            raise ValueError("A 12-digit number looks like an Aadhaar number and cannot be stored")
        return cleaned


class ExternalIdResponse(BaseModel):
    trainee_id: str
    id_type: str
    id_value: str
    source_programme: Optional[str] = None


class ExternalIdLookupResponse(BaseModel):
    trainee_id: str
    id_type: str
    id_value: str


class DuplicateGroup(BaseModel):
    """Trainees sharing the same normalised name and date of birth."""

    full_name: str
    dob: str
    trainee_ids: list[str]


class PossibleDuplicatesResponse(BaseModel):
    groups: list[DuplicateGroup]
    trainees_involved: int
