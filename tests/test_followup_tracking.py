"""
Phase 5 tests — automated + assisted follow-up system.

Runs against the real database from .env, same as the earlier test
files. Mirrors the 20-test checklist from the Phase 5 spec.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from main import app
from tests.auth_helpers import ADMIN_HEADERS

client = TestClient(app, headers=ADMIN_HEADERS)


def register_dummy_trainee(phone: str) -> str:
    import uuid
    unique_phone = f"96{uuid.uuid4().int % 100000000:08d}"
    payload = {
        "full_name": "Followup Test Trainee",
        "dob": "2000-01-15",
        "gender": "Male",
        "district": "Raigad",
        "current_location": "Panvel",
        "phone": unique_phone,
        "preferred_contact": "Phone",
        "consent_given": True,
    }
    response = client.post("/api/trainees", json=payload)
    assert response.status_code == 201
    return response.json()["trainee_id"]


def add_completed_training(trainee_id: str, end_date: str) -> str:
    payload = {
        "course_name": "Electrical Wiring Basics",
        "provider_name": "Test ITI",
        "start_date": "2025-01-01",
        "end_date": end_date,
        "status": "Completed",
        "certification_issued": True,
    }
    response = client.post(f"/api/trainees/{trainee_id}/training-records", json=payload)
    assert response.status_code == 201
    return response.json()["record_id"]


def add_ongoing_training(trainee_id: str) -> str:
    payload = {
        "course_name": "Plumbing Fundamentals",
        "provider_name": "Test ITI",
        "start_date": "2026-01-01",
        "status": "Ongoing",
    }
    response = client.post(f"/api/trainees/{trainee_id}/training-records", json=payload)
    assert response.status_code == 201
    return response.json()["record_id"]


# --- Test 1 & 2: create a completed training, generate the schedule ---


def test_generate_schedule_creates_four_followups():
    trainee_id = register_dummy_trainee("9811100001")
    training_id = add_completed_training(trainee_id, "2026-06-01")

    response = client.post(f"/api/followups/generate/{training_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["followups_created"] == 4
    assert body["training_id"] == training_id

    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline")
    assert timeline.status_code == 200
    types = {f["followup_type"] for f in timeline.json()["followups"]}
    assert types == {"30_DAY", "90_DAY", "6_MONTH", "12_MONTH"}


# --- Test 3: duplicate generation is a no-op ---


def test_generate_schedule_is_idempotent():
    trainee_id = register_dummy_trainee("9811100002")
    training_id = add_completed_training(trainee_id, "2026-06-01")

    first = client.post(f"/api/followups/generate/{training_id}")
    assert first.json()["followups_created"] == 4

    second = client.post(f"/api/followups/generate/{training_id}")
    assert second.status_code == 200
    assert second.json()["followups_created"] == 0
    assert "already exists" in second.json()["message"].lower()


# --- Test 4 & 5: pending / upcoming ---


def test_pending_and_upcoming_followups():
    trainee_id = register_dummy_trainee("9811100003")
    # end_date in the past so the 30_DAY follow-up is already due
    past_end = (date.today() - timedelta(days=40)).isoformat()
    training_id = add_completed_training(trainee_id, past_end)
    client.post(f"/api/followups/generate/{training_id}")

    pending = client.get("/api/followups/pending")
    assert pending.status_code == 200
    assert any(f["training_id"] == training_id for f in pending.json())

    upcoming = client.get("/api/followups/upcoming", params={"days": 400})
    assert upcoming.status_code == 200
    assert any(f["training_id"] == training_id for f in upcoming.json())


# --- Test 6, 7, 8, 9: complete, attempts, attempt history ---


def test_complete_followup_and_record_attempts():
    trainee_id = register_dummy_trainee("9811100004")
    past_end = (date.today() - timedelta(days=40)).isoformat()
    training_id = add_completed_training(trainee_id, past_end)
    client.post(f"/api/followups/generate/{training_id}")

    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline").json()
    followup_id = next(
        f["followup_id"] for f in timeline["followups"] if f["followup_type"] == "30_DAY"
    )

    attempt1 = client.post(
        f"/api/followups/{followup_id}/attempt",
        json={
            "attempt_date": date.today().isoformat(),
            "contact_method": "Phone",
            "attempt_status": "No Response",
            "notes": "First try.",
        },
    )
    assert attempt1.status_code == 201
    assert attempt1.json()["attempt_id"].startswith("ATT")

    attempt2 = client.post(
        f"/api/followups/{followup_id}/attempt",
        json={
            "attempt_date": date.today().isoformat(),
            "contact_method": "WhatsApp",
            "attempt_status": "Successful",
        },
    )
    assert attempt2.status_code == 201

    history = client.get(f"/api/followups/{followup_id}/attempts")
    assert history.status_code == 200
    assert len(history.json()) == 2

    complete = client.post(
        f"/api/followups/{followup_id}/complete",
        json={"completed_date": date.today().isoformat(), "notes": "Reached the trainee."},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "Completed"


# --- Test 10: outcome update for an employed trainee ---


def test_outcome_update_employed():
    trainee_id = register_dummy_trainee("9811100005")
    past_end = (date.today() - timedelta(days=40)).isoformat()
    training_id = add_completed_training(trainee_id, past_end)
    client.post(f"/api/followups/generate/{training_id}")

    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline").json()
    followup_id = timeline["followups"][0]["followup_id"]

    response = client.post(
        f"/api/followups/{followup_id}/outcome-update",
        json={
            "employment_status": "Employed",
            "training_relevance": 4,
            "skill_gap": False,
            "additional_training_needed": False,
            "notes": "Still working at the same company.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["employment_status"] == "Employed"
    assert body["training_relevance"] == 4


# --- Test 11: unemployed follow-up + non-placement reason ---


def test_outcome_update_unemployed_with_reason():
    trainee_id = register_dummy_trainee("9811100006")
    past_end = (date.today() - timedelta(days=40)).isoformat()
    training_id = add_completed_training(trainee_id, past_end)
    client.post(f"/api/followups/generate/{training_id}")

    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline").json()
    followup_id = timeline["followups"][0]["followup_id"]

    response = client.post(
        f"/api/followups/{followup_id}/outcome-update",
        json={
            "employment_status": "Unemployed",
            "unemployment_reason_category": "Lack of Jobs",
            "unemployment_reason_details": "No local openings.",
        },
    )
    assert response.status_code == 201
    assert response.json()["unemployment_reason_category"] == "Lack of Jobs"

    # A reason category on an *employed* update should be rejected
    bad = client.post(
        f"/api/followups/{followup_id}/outcome-update",
        json={"employment_status": "Employed", "unemployment_reason_category": "Lack of Jobs"},
    )
    assert bad.status_code == 422


# --- Test 12, 13: follow-up summary + trainee timeline ---


def test_followup_summary_and_timeline():
    trainee_id = register_dummy_trainee("9811100007")
    past_end = (date.today() - timedelta(days=40)).isoformat()
    training_id = add_completed_training(trainee_id, past_end)
    client.post(f"/api/followups/generate/{training_id}")

    timeline = client.get(f"/api/trainees/{trainee_id}/followup-timeline")
    assert timeline.status_code == 200
    assert len(timeline.json()["followups"]) == 4

    followup_id = timeline.json()["followups"][0]["followup_id"]
    client.post(
        f"/api/followups/{followup_id}/attempt",
        json={
            "attempt_date": date.today().isoformat(),
            "contact_method": "Phone",
            "attempt_status": "Successful",
        },
    )

    summary = client.get(f"/api/followups/{followup_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["attempt_count"] == 1
    assert summary.json()["latest_attempt"]["attempt_status"] == "Successful"


# --- Test 14, 15: overdue / upcoming ---


def test_overdue_followups():
    trainee_id = register_dummy_trainee("9811100008")
    long_past_end = (date.today() - timedelta(days=400)).isoformat()
    training_id = add_completed_training(trainee_id, long_past_end)
    client.post(f"/api/followups/generate/{training_id}")

    overdue = client.get("/api/followups/overdue")
    assert overdue.status_code == 200
    matches = [f for f in overdue.json() if f["training_id"] == training_id]
    assert len(matches) > 0
    assert all(f["days_overdue"] >= 0 for f in matches)


# --- Test 16: admin follow-up summary ---


def test_admin_followup_summary():
    response = client.get("/api/followups/summary")
    assert response.status_code == 200
    body = response.json()
    for key in ("total", "scheduled", "completed", "missed", "not_reachable", "overdue", "upcoming_7_days"):
        assert key in body


# --- Test 17: invalid follow-up type is rejected by the existing Phase 3 endpoint ---


def test_invalid_followup_type_rejected():
    trainee_id = register_dummy_trainee("9811100009")
    training_id = add_ongoing_training(trainee_id)
    response = client.post(
        "/api/followups",
        json={
            "trainee_id": trainee_id,
            "training_id": training_id,
            "followup_type": "3_DAY",
            "scheduled_date": "2026-05-01",
        },
    )
    assert response.status_code == 422


# --- Test 18, 19: invalid trainee / training IDs ---


def test_generate_schedule_invalid_training_id():
    response = client.post("/api/followups/generate/TRC999999")
    assert response.status_code == 404


def test_generate_schedule_training_not_completed():
    trainee_id = register_dummy_trainee("9811100010")
    training_id = add_ongoing_training(trainee_id)
    response = client.post(f"/api/followups/generate/{training_id}")
    assert response.status_code == 400
