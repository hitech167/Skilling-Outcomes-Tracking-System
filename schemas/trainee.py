"""
Pydantic schemas: what the API accepts and what it returns.

Keeping request/response shapes here means the routes stay short and the
validation rules live in one obvious place.
"""

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from schemas.identity import ExternalIdCreate

# Only these three channels are allowed in Phase 1
ALLOWED_CONTACT_METHODS = {"SMS", "Email", "Phone"}
ConsentMethod = Literal["Paper form", "Digital form", "Verbal", "Self-service"]

# Indian mobile numbers: 10 digits starting with 6-9.
# We accept an optional +91 / 0 prefix and strip it before storing.
PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")


class TraineeCreate(BaseModel):
    """Body of POST /api/trainees"""

    full_name: str = Field(..., min_length=2, max_length=150)
    dob: date
    gender: str = Field(..., max_length=20)
    district: str = Field(..., min_length=1, max_length=100)
    current_location: Optional[str] = Field(None, max_length=150)

    phone: str
    email: Optional[EmailStr] = None
    preferred_contact: str

    # Consent statement 1 — required. Registration fails without it.
    consent_given: bool

    # Evidence of how/by whom consent was captured (optional, kept in the
    # consent history). Staff normally record it on the trainee's behalf.
    consent_method: Optional[ConsentMethod] = None
    consent_recorded_by: Optional[str] = Field(None, max_length=150)

    # Consent statements 2 and 3 from the form (aggregated analytics use,
    # privacy notice). consent_given is the recorded consent and covers
    # both; these are optional acknowledgements. They are never silently
    # overridden: an explicit `false` means the trainee has NOT agreed to
    # how the data is used, so registration is refused rather than
    # storing their data against their stated choice.
    consent_analytics: Optional[bool] = None
    consent_privacy_notice: Optional[bool] = None

    # IDs this person already has in other programmes (Skill India
    # Digital ID, scheme candidate IDs...). Optional; used to link records
    # across programmes and to refuse a duplicate registration.
    external_ids: list[ExternalIdCreate] = Field(default_factory=list, max_length=10)

    model_config = {
        "json_schema_extra": {
            "example": {
                "full_name": "Rahul Patil",
                "dob": "2005-08-15",
                "gender": "Male",
                "district": "Raigad",
                "current_location": "Panvel",
                "phone": "9876543210",
                "email": "rahul@example.com",
                "preferred_contact": "SMS",
                "consent_given": True,
            }
        }
    }

    @field_validator("full_name", "gender", "district")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("dob")
    @classmethod
    def sensible_date_of_birth(cls, value: date) -> date:
        today = date.today()
        if value >= today:
            raise ValueError("Date of birth must be in the past")
        age = (today - value).days / 365.25
        if age < 10 or age > 100:
            raise ValueError("Date of birth does not look valid")
        return value

    @field_validator("phone")
    @classmethod
    def valid_indian_mobile(cls, value: str) -> str:
        # Remove spaces, dashes and a leading +91 / 91 / 0
        digits = re.sub(r"[\s\-()]", "", value)
        # Strip a country/trunk prefix only when one is really there:
        # 9123456789 is a valid mobile number, not "91" + 8 digits.
        if digits.startswith("+91"):
            digits = digits[3:]
        elif len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if not PHONE_PATTERN.match(digits):
            raise ValueError(
                "Phone must be a valid 10-digit Indian mobile number "
                "starting with 6, 7, 8 or 9"
            )
        return digits

    @field_validator("preferred_contact")
    @classmethod
    def valid_contact_method(cls, value: str) -> str:
        cleaned = value.strip().capitalize()
        # "SMS" would become "Sms" with capitalize(), so fix that case
        if cleaned.lower() == "sms":
            cleaned = "SMS"
        if cleaned not in ALLOWED_CONTACT_METHODS:
            raise ValueError("preferred_contact must be one of: SMS, Email, Phone")
        return cleaned

    @field_validator("consent_given")
    @classmethod
    def consent_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError(
                "Consent is required. Registration cannot proceed without it."
            )
        return value

    @field_validator("consent_analytics", "consent_privacy_notice")
    @classmethod
    def consent_not_refused(cls, value: Optional[bool]) -> Optional[bool]:
        if value is False:
            raise ValueError(
                "Registration requires agreement to aggregated outcome analytics "
                "and the privacy notice."
            )
        return value


class TraineeContactUpdate(BaseModel):
    """
    Body of PATCH /api/trainees/{trainee_id}.

    Trainees change phone numbers and move; the stable trainee_id never
    changes, so the longitudinal record stays linked. Send only what
    changed.
    """

    district: Optional[str] = Field(None, min_length=1, max_length=100)
    current_location: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    preferred_contact: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {"phone": "9123456780", "current_location": "Pune"}
        }
    }

    @field_validator("district")
    @classmethod
    def not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be empty")
        return cleaned

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else TraineeCreate.valid_indian_mobile(value)

    @field_validator("preferred_contact")
    @classmethod
    def valid_contact(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else TraineeCreate.valid_contact_method(value)


class ConsentUpdate(BaseModel):
    """Body of POST /api/trainees/{trainee_id}/consent (grant again or withdraw)."""

    consent_given: bool
    method: Optional[ConsentMethod] = None
    recorded_by: Optional[str] = Field(None, max_length=150)
    notes: Optional[str] = Field(None, max_length=255)


class PhoneVerifyRequest(BaseModel):
    """Body of POST /api/me/{token}/contact/verify."""

    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class LinkRequest(BaseModel):
    """Body of POST /api/request-link: a trainee ID or the phone number on file."""

    identifier: str = Field(..., min_length=3, max_length=30)


class SelfConsentUpdate(BaseModel):
    """Body of POST /api/self-report/{token}/consent (trainee withdraws or re-grants)."""

    consent_given: bool


class TraineeContact(BaseModel):
    """
    Response of GET /api/trainees/{trainee_id}/contact — admin only.
    Contact details needed to carry out assisted follow-ups.
    """

    trainee_id: str
    full_name: str
    phone: str
    email: Optional[str] = None
    preferred_contact: str
    district: str
    current_location: Optional[str] = None
    consent_given: bool

    model_config = {"from_attributes": True}


class TraineeCreateResponse(BaseModel):
    """Response of a successful POST /api/trainees"""

    success: bool = True
    trainee_id: str
    message: str = "Trainee registered successfully"
    # Existing trainees with the same name and date of birth — a warning
    # for the admin to review, not an error.
    possible_duplicates: list[str] = []
    # Personal link the trainee can use to update their phone / location or
    # withdraw consent at any time (also sent to them as a welcome message).
    profile_link: Optional[str] = None


class TraineePublic(BaseModel):
    """
    Response of GET /api/trainees/{trainee_id}.

    Note what is NOT here: phone, email and date of birth are deliberately
    left out so the read endpoint does not leak personal contact details.
    """

    trainee_id: str
    full_name: str
    district: str
    current_location: Optional[str] = None
    preferred_contact: str
    consent_given: bool

    model_config = {"from_attributes": True}
