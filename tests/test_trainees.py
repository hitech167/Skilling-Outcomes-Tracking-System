"""
Basic Phase 1 tests.

These hit the real database configured in .env, so run them against a test
database (or an empty Supabase project), not production data.

Run with:  pytest -v
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def dummy_trainee(phone: str, email: str | None = None) -> dict:
    """All test data is dummy data — no real personal information."""
    return {
        "full_name": "Test Trainee",
        "dob": "2003-01-20",
        "gender": "Female",
        "district": "Pune",
        "current_location": "Hadapsar",
        "phone": phone,
        "email": email,
        "preferred_contact": "SMS",
        "consent_given": True,
    }


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_and_fetch_trainee():
    import uuid
    unique_phone = f"98{uuid.uuid4().int % 100000000:08d}"
    response = client.post("/api/trainees", json=dummy_trainee(unique_phone))
    assert response.status_code == 201

    body = response.json()
    assert body["success"] is True
    assert body["trainee_id"].startswith("TRN")

    fetched = client.get(f"/api/trainees/{body['trainee_id']}")
    assert fetched.status_code == 200

    profile = fetched.json()
    assert profile["district"] == "Pune"
    # The read endpoint must not leak contact details
    assert "phone" not in profile
    assert "email" not in profile
    assert "dob" not in profile


def test_registration_rejected_without_consent():
    payload = dummy_trainee("9812345671")
    payload["consent_given"] = False
    response = client.post("/api/trainees", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("phone", "12345"),            # not an Indian mobile number
        ("email", "not-an-email"),     # malformed email
        ("dob", "2099-01-01"),         # date in the future
        ("district", ""),              # empty required field
        ("preferred_contact", "Fax"),  # not an allowed channel
    ],
)
def test_invalid_input_is_rejected(field, bad_value):
    payload = dummy_trainee("9812345672")
    payload[field] = bad_value
    response = client.post("/api/trainees", json=payload)
    assert response.status_code == 422


def test_unknown_trainee_returns_404():
    response = client.get("/api/trainees/TRN999999")
    assert response.status_code == 404


def test_duplicate_phone_returns_409():
    import uuid
    unique_phone = f"98{uuid.uuid4().int % 100000000:08d}"
    payload = dummy_trainee(unique_phone)
    first = client.post("/api/trainees", json=payload)
    assert first.status_code == 201

    second = client.post("/api/trainees", json=payload)
    assert second.status_code == 409
