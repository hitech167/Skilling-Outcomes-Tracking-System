"""
Tests for listing employer verifications and reminding pending ones.

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


def test_remind_pending_resends_links_for_latest_pending_only(isolated_db):
    trainee_a, emp_a = _employment("A One")
    _request(emp_a, "hr@a.example")
    _request(emp_a, "hr@a.example")  # newer attempt supersedes the first

    trainee_b, emp_b = _employment("B Two")
    _request(emp_b, None)  # no contact -> cannot be reminded

    trainee_c, emp_c = _employment("C Three")
    _manual(trainee_c, emp_c, "Pending")  # not link-based -> staff follow up by hand

    trainee_d, emp_d = _employment("D Four")
    _request(emp_d, "9876500000")
    _manual(trainee_d, emp_d, "Verified")  # already resolved by a later attempt

    before = len(get_ok(admin, "/api/notifications", params={"limit": 500}))
    summary = admin.post("/api/employer-verifications/remind-pending").json()
    assert summary == {
        "pending": 3, "reminded": 1, "sent": 0, "queued": 1, "failed": 0,
        "skipped_no_contact": 1, "skipped_not_link_based": 1,
    }

    outbox = get_ok(admin, "/api/notifications", params={"limit": 500})
    assert len(outbox) == before + 1
    reminder = outbox[0]
    assert (reminder["trainee_id"], reminder["channel"], reminder["recipient"]) == (
        trainee_a, "Email", "hr@a.example",
    )
    assert reminder["message"].startswith("Reminder:") and "/employer-verify/" in reminder["message"]
