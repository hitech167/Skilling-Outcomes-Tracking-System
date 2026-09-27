"""
Tests for listing employer verifications.

Each test gets its own empty in-memory database (the isolated_db fixture in conftest.py).
"""

from tests.test_phase8_hardening import (
    admin,
    analyst,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
)


def _employment(full_name: str = "Kiran More") -> tuple[str, str]:
    trainee_id = make_trainee(full_name=full_name)
    outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
    return trainee_id, make_employment(trainee_id, outcome_id)


def _request(employment_id: str, contact: str | None) -> str:
    res = admin.post(
        f"/api/employment/{employment_id}/verification-request",
        json={"employer_contact": contact} if contact else {},
    )
    assert res.status_code == 201
    return res.json()["verification_id"]


def _manual(trainee_id: str, employment_id: str, status: str) -> str:
    res = admin.post(
        "/api/employer-verifications",
        json={"employment_id": employment_id, "trainee_id": trainee_id,
              "employer_name": "Volt Works Pvt Ltd", "verification_status": status,
              "verification_method": "Employer Contact"},
    )
    assert res.status_code == 201
    return res.json()["verification_id"]


def test_list_includes_trainee_and_employment_details(isolated_db):
    trainee_id, employment_id = _employment("Kiran More")
    verification_id = _request(employment_id, "hr@voltworks.example")

    rows = get_ok(admin, "/api/employer-verifications")
    assert len(rows) == 1
    row = rows[0]
    assert row["verification_id"] == verification_id
    assert (row["trainee_id"], row["trainee_name"]) == (trainee_id, "Kiran More")
    assert row["employment_id"] == employment_id
    assert row["verification_status"] == "Pending"
    assert row["created_at"] is not None
    assert "job_role" in row and "salary" in row

    detail = get_ok(admin, f"/api/employer-verifications/{verification_id}")
    assert detail["trainee_name"] == "Kiran More"


def test_list_filters_by_status_newest_first(isolated_db):
    trainee_id, employment_id = _employment()
    first = _manual(trainee_id, employment_id, "Verified")
    second = _request(employment_id, "hr@voltworks.example")

    assert [r["verification_id"] for r in get_ok(admin, "/api/employer-verifications")] == [second, first]
    pending = get_ok(admin, "/api/employer-verifications", params={"status": "Pending"})
    assert [r["verification_id"] for r in pending] == [second]


def test_list_is_admin_only(isolated_db):
    assert analyst.get("/api/employer-verifications").status_code == 403


def test_staff_can_confirm_a_pending_request(isolated_db):
    _, employment_id = _employment()
    verification_id = _request(employment_id, "hr@voltworks.example")

    res = admin.patch(
        f"/api/employer-verifications/{verification_id}/status",
        json={"verification_status": "verified", "verified_by": "Admin",
              "verification_notes": "Confirmed by phone."},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["verification_status"] == "Verified"
    assert body["verified_by"] == "Admin"
    assert body["verified_date"] is not None
    assert body["verification_notes"] == "Confirmed by phone."


def test_decided_requests_cannot_be_changed(isolated_db):
    trainee_id, employment_id = _employment()
    verification_id = _manual(trainee_id, employment_id, "Verified")

    res = admin.patch(
        f"/api/employer-verifications/{verification_id}/status",
        json={"verification_status": "Rejected"},
    )
    assert res.status_code == 409


def test_status_update_rejects_pending_and_unknown_values(isolated_db):
    _, employment_id = _employment()
    verification_id = _request(employment_id, None)
    path = f"/api/employer-verifications/{verification_id}/status"

    assert admin.patch(path, json={"verification_status": "Pending"}).status_code == 422
    assert admin.patch(path, json={"verification_status": "Maybe"}).status_code == 422
    assert admin.patch("/api/employer-verifications/VER999999/status",
                       json={"verification_status": "Rejected"}).status_code == 404
    assert analyst.patch(path, json={"verification_status": "Rejected"}).status_code == 403
