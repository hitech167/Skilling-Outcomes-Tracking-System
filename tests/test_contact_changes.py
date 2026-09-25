"""
Trainee self-service contact updates, contact history, and employer reminders.
"""

from datetime import datetime, timedelta, timezone

from database.models import Notification
from tests.test_gap_features import _due_followup, _token_from
from tests.test_phase8_hardening import (
    admin,
    anon,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
    new_phone,
)


def test_trainee_updates_own_contact_and_history_is_kept(isolated_db):
    trainee_id = make_trainee(full_name="Sana Shaikh")
    old_phone = get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"]
    followup_id = _due_followup(trainee_id)
    token = _token_from(get_ok(admin, f"/api/followups/{followup_id}/self-report-link")["link"])

    ctx = get_ok(anon, f"/api/self-report/{token}/contact")
    assert "phone" not in ctx

    new = new_phone()
    res = anon.patch(f"/api/self-report/{token}/contact", json={"phone": new, "district": "Nagpur"})
    assert res.status_code == 200, res.text
    assert set(res.json()["updated"]) == {"phone", "district"}

    assert get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"] == new
    history = get_ok(admin, f"/api/trainees/{trainee_id}/contact-history")
    phone_row = next(h for h in history if h["field"] == "phone")
    assert phone_row["old_value"] == old_phone and phone_row["new_value"] == new
    assert phone_row["source"] == "self"

    # staff edits are logged too; unchanged values are not
    admin.patch(f"/api/trainees/{trainee_id}", json={"district": "Nagpur", "current_location": "Wardha"})
    history = get_ok(admin, f"/api/trainees/{trainee_id}/contact-history")
    assert [h["field"] for h in history if h["source"] == "admin"] == ["current_location"]


def test_self_contact_update_rejects_bad_token_duplicate_and_withdrawn(isolated_db):
    a = make_trainee()
    b = make_trainee()
    token = _token_from(get_ok(admin, f"/api/followups/{_due_followup(a)}/self-report-link")["link"])
    b_phone = get_ok(admin, f"/api/trainees/{b}/contact")["phone"]

    assert anon.patch("/api/self-report/garbage/contact", json={"district": "X"}).status_code == 404
    assert anon.patch(f"/api/self-report/{token}/contact", json={"phone": b_phone}).status_code == 409
    assert anon.patch(f"/api/self-report/{token}/contact", json={"phone": None}).status_code == 422

    admin.post(f"/api/trainees/{a}/consent", json={"consent_given": False})
    assert anon.patch(f"/api/self-report/{token}/contact", json={"district": "X"}).status_code == 403


def test_employer_reminders_then_marked_unresponsive(isolated_db):
    trainee_id = make_trainee()
    employment_id = make_employment(trainee_id, make_outcome(trainee_id, make_training(trainee_id), "Employed"))
    admin.post(
        f"/api/employment/{employment_id}/verification-request",
        json={"employer_contact": "hr@voltworks.example"},
    )

    def age_notifications():
        db = isolated_db()
        for n in db.query(Notification).all():
            n.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()
        db.close()

    assert admin.post("/api/verifications/remind-pending").json()["reminded"] == 0  # too soon

    age_notifications()
    assert admin.post("/api/verifications/remind-pending").json()["reminded"] == 1
    age_notifications()
    assert admin.post("/api/verifications/remind-pending").json()["reminded"] == 1
    age_notifications()
    summary = admin.post("/api/verifications/remind-pending").json()
    assert summary["marked_unresponsive"] == 1 and summary["reminded"] == 0

    verification = get_ok(admin, f"/api/employment/{employment_id}/verification")
    assert verification["verification_status"] == "Unable to Verify"
    assert "unresponsive" in verification["verification_notes"]


def test_no_employer_reminders_after_consent_withdrawn(isolated_db):
    trainee_id = make_trainee()
    employment_id = make_employment(trainee_id, make_outcome(trainee_id, make_training(trainee_id), "Employed"))
    admin.post(
        f"/api/employment/{employment_id}/verification-request",
        json={"employer_contact": "hr@voltworks.example"},
    )
    db = isolated_db()
    for n in db.query(Notification).all():
        n.created_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    db.close()

    admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": False})
    summary = admin.post("/api/verifications/remind-pending").json()
    assert summary["reminded"] == 0 and summary["skipped_no_consent"] == 1
