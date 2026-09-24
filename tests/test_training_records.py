"""
Phase 2 tests — training records.

Runs against the real database from .env, same as test_trainees.py.
Each test registers its own dummy trainee first so it doesn't depend on
data left over from other tests.
"""

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def register_dummy_trainee(phone: str) -> str:
    import uuid
    unique_phone = f"99{uuid.uuid4().int % 100000000:08d}"
    payload = {
        "full_name": "Training Test Trainee",
        "dob": "2002-06-01",
        "gender": "Male",
        "district": "Nagpur",
        "current_location": "Nagpur",
        "phone": unique_phone,
        "preferred_contact": "SMS",
        "consent_given": True,
    }
    response = client.post("/api/trainees", json=payload)
    assert response.status_code == 201
    return response.json()["trainee_id"]


def dummy_record(**overrides) -> dict:
    record = {
        "course_name": "Python Development",
        "provider_name": "NSDC Skill Center",
        "start_date": "2025-01-10",
        "end_date": "2025-03-10",
        "status": "Completed",
        "attendance_percentage": 92.5,
        "assessment_score": 88,
        "certification_issued": True,
        "certification_id": "CERT-PY-0001",
    }
    record.update(overrides)
    return record


def test_create_and_get_training_record():
    trainee_id = register_dummy_trainee("9900011122")

    response = client.post(
        f"/api/trainees/{trainee_id}/training-records", json=dummy_record()
    )
    assert response.status_code == 201
    body = response.json()
    assert body["record_id"].startswith("TRC")
    assert body["trainee_id"] == trainee_id
    assert body["status"] == "Completed"

    fetched = client.get(f"/api/training-records/{body['record_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["course_name"] == "Python Development"


def test_multiple_records_for_same_trainee():
    trainee_id = register_dummy_trainee("9900011133")

    client.post(
        f"/api/trainees/{trainee_id}/training-records",
        json=dummy_record(course_name="Python Development"),
    )
    client.post(
        f"/api/trainees/{trainee_id}/training-records",
        json=dummy_record(
            course_name="AWS Fundamentals",
            certification_issued=False,
            status="Ongoing",
            end_date=None,
        ),
    )

    response = client.get(f"/api/trainees/{trainee_id}/training-records")
    assert response.status_code == 200
    courses = {r["course_name"] for r in response.json()}
    assert courses == {"Python Development", "AWS Fundamentals"}


def test_record_for_unknown_trainee_returns_404():
    response = client.post(
        "/api/trainees/TRN999999/training-records", json=dummy_record()
    )
    assert response.status_code == 404


def test_unknown_record_returns_404():
    response = client.get("/api/training-records/TRC999999")
    assert response.status_code == 404


def test_end_date_before_start_date_rejected():
    trainee_id = register_dummy_trainee("9900011144")
    payload = dummy_record(start_date="2025-03-10", end_date="2025-01-10")
    response = client.post(
        f"/api/trainees/{trainee_id}/training-records", json=payload
    )
    assert response.status_code == 422


def test_certification_without_completed_status_rejected():
    trainee_id = register_dummy_trainee("9900011155")
    payload = dummy_record(status="Ongoing", certification_issued=True, end_date=None)
    response = client.post(
        f"/api/trainees/{trainee_id}/training-records", json=payload
    )
    assert response.status_code == 422


def test_patch_updates_status_to_completed():
    trainee_id = register_dummy_trainee("9900011166")
    created = client.post(
        f"/api/trainees/{trainee_id}/training-records",
        json=dummy_record(status="Ongoing", certification_issued=False, end_date=None),
    ).json()

    response = client.patch(
        f"/api/training-records/{created['record_id']}",
        json={"status": "Completed", "end_date": "2025-04-01"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Completed"
