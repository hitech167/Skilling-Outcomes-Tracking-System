"""
Phase 3 tests — outcomes, employment/self-employment/apprenticeship/
non-placement detail, and follow-ups.

Runs against the real database from .env, same as the earlier test files.
"""

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def register_dummy_trainee(phone: str) -> str:
    import uuid
    unique_phone = f"97{uuid.uuid4().int % 100000000:08d}"
    payload = {
        "full_name": "Outcome Test Trainee",
        "dob": "2001-05-10",
        "gender": "Female",
        "district": "Thane",
        "current_location": "Thane",
        "phone": unique_phone,
        "preferred_contact": "SMS",
        "consent_given": True,
    }
    response = client.post("/api/trainees", json=payload)
    assert response.status_code == 201
    return response.json()["trainee_id"]


def add_dummy_training(trainee_id: str, status: str = "Completed") -> str:
    payload = {
        "course_name": "Data Entry Fundamentals",
        "provider_name": "Test Skill Center",
        "start_date": "2025-01-10",
        "end_date": "2025-02-10" if status == "Completed" else None,
        "status": status,
        "certification_issued": status == "Completed",
    }
    response = client.post(f"/api/trainees/{trainee_id}/training-records", json=payload)
    assert response.status_code == 201
    return response.json()["record_id"]


def test_create_outcome_and_get_and_list():
    trainee_id = register_dummy_trainee("9700011122")
    training_id = add_dummy_training(trainee_id)

    payload = {
        "trainee_id": trainee_id,
        "training_id": training_id,
        "outcome_type": "Employed",
        "status_date": "2026-06-15",
        "notes": "Started a job.",
    }
    response = client.post("/api/outcomes", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["outcome_id"].startswith("OUT")
    assert body["trainee_id"] == trainee_id
    assert body["training_id"] == training_id

    fetched = client.get(f"/api/outcomes/{body['outcome_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["outcome_type"] == "Employed"

    listed = client.get(f"/api/trainees/{trainee_id}/outcomes")
    assert listed.status_code == 200
    assert listed.json()["trainee_id"] == trainee_id
    assert len(listed.json()["outcomes"]) == 1


def test_outcome_rejects_training_from_another_trainee():
    trainee_a = register_dummy_trainee("9700011133")
    trainee_b = register_dummy_trainee("9700011144")
    training_of_a = add_dummy_training(trainee_a)

    payload = {
        "trainee_id": trainee_b,
        "training_id": training_of_a,
        "outcome_type": "Employed",
        "status_date": "2026-06-15",
    }
    response = client.post("/api/outcomes", json=payload)
    assert response.status_code == 400


def test_outcome_unknown_trainee_or_training_404():
    training_id = add_dummy_training(register_dummy_trainee("9700011155"))

    bad_trainee = client.post(
        "/api/outcomes",
        json={
            "trainee_id": "TRN999999",
            "training_id": training_id,
            "outcome_type": "Employed",
            "status_date": "2026-06-15",
        },
    )
    assert bad_trainee.status_code == 404

    trainee_id = register_dummy_trainee("9700011166")
    bad_training = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": "TRC999999",
            "outcome_type": "Employed",
            "status_date": "2026-06-15",
        },
    )
    assert bad_training.status_code == 404


def test_invalid_outcome_type_rejected():
    trainee_id = register_dummy_trainee("9700011177")
    training_id = add_dummy_training(trainee_id)

    response = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "outcome_type": "Retired",
            "status_date": "2026-06-15",
        },
    )
    assert response.status_code == 422


def _make_employed_outcome(phone: str) -> tuple[str, str]:
    trainee_id = register_dummy_trainee(phone)
    training_id = add_dummy_training(trainee_id)
    outcome = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "outcome_type": "Employed",
            "status_date": "2026-06-15",
        },
    ).json()
    return trainee_id, outcome["outcome_id"]


def test_employment_detail_create_and_get():
    trainee_id, outcome_id = _make_employed_outcome("9700011188")

    payload = {
        "outcome_id": outcome_id,
        "trainee_id": trainee_id,
        "company_name": "ABC Technologies Pvt Ltd",
        "job_role": "Junior Developer",
        "joining_date": "2026-06-20",
        "salary": 22000,
        "employment_status": "Active",
        "job_location": "Pune",
        "job_relevance": "Relevant",
    }
    response = client.post("/api/employment", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["employment_id"].startswith("EMP")
    assert body["outcome_id"] == outcome_id

    fetched = client.get(f"/api/employment/{body['employment_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["company_name"] == "ABC Technologies Pvt Ltd"


def test_employment_detail_rejected_for_wrong_outcome_type():
    trainee_id = register_dummy_trainee("9700011199")
    training_id = add_dummy_training(trainee_id)
    outcome = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "outcome_type": "Unemployed",
            "status_date": "2026-06-15",
        },
    ).json()

    payload = {
        "outcome_id": outcome["outcome_id"],
        "trainee_id": trainee_id,
        "company_name": "Some Company",
        "job_role": "Role",
        "joining_date": "2026-06-20",
    }
    response = client.post("/api/employment", json=payload)
    assert response.status_code == 400


def test_non_placement_flow():
    trainee_id = register_dummy_trainee("9700011200")
    training_id = add_dummy_training(trainee_id)
    outcome = client.post(
        "/api/outcomes",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "outcome_type": "Unemployed",
            "status_date": "2026-06-15",
        },
    ).json()

    payload = {
        "outcome_id": outcome["outcome_id"],
        "trainee_id": trainee_id,
        "reason_category": "Lack of Jobs",
        "reason_details": "No matching openings in the district.",
    }
    response = client.post("/api/non-placement", json=payload)
    assert response.status_code == 201
    assert response.json()["reason_category"] == "Lack of Jobs"

    bad_reason = client.post(
        "/api/non-placement",
        json={**payload, "reason_category": "Bad Luck"},
    )
    assert bad_reason.status_code == 422


def test_followup_schedule_and_patch():
    trainee_id, outcome_id = _make_employed_outcome("9700011211")
    training_response = client.get(f"/api/trainees/{trainee_id}/training-records")
    training_id = training_response.json()[0]["record_id"]

    created = client.post(
        "/api/followups",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "followup_type": "30_DAY",
            "scheduled_date": "2026-04-15",
        },
    )
    assert created.status_code == 201
    followup_id = created.json()["followup_id"]
    assert created.json()["status"] == "Scheduled"

    patched = client.patch(
        f"/api/followups/{followup_id}",
        json={
            "status": "Completed",
            "completed_date": "2026-04-16",
            "outcome_id": outcome_id,
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "Completed"
    assert patched.json()["outcome_id"] == outcome_id

    listed = client.get(f"/api/trainees/{trainee_id}/followups")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_followup_completed_requires_completed_date():
    trainee_id = register_dummy_trainee("9700011222")
    training_id = add_dummy_training(trainee_id)
    created = client.post(
        "/api/followups",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "followup_type": "90_DAY",
            "scheduled_date": "2026-05-01",
        },
    ).json()

    response = client.patch(
        f"/api/followups/{created['followup_id']}", json={"status": "Completed"}
    )
    assert response.status_code == 422
