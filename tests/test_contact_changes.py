"""
Trainee self-service contact updates, contact history, and employer reminders.
"""

from datetime import datetime, timedelta, timezone

from database.models import Notification, PhoneChangeRequest
from services import contact_service
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


def test_trainee_updates_own_contact_and_history_is_kept(isolated_db, monkeypatch):
    monkeypatch.setattr(contact_service, "_new_code", lambda: "123456")
    trainee_id = make_trainee(full_name="Sana Shaikh")
    old_phone = get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"]
    followup_id = _due_followup(trainee_id)
    token = _token_from(get_ok(admin, f"/api/followups/{followup_id}/self-report-link")["link"])

    ctx = get_ok(anon, f"/api/self-report/{token}/contact")
    assert "phone" not in ctx

    new = new_phone()
    res = anon.patch(f"/api/self-report/{token}/contact", json={"phone": new, "district": "Nagpur"})
    assert res.status_code == 200, res.text
    assert res.json() == {"updated": ["district"], "phone_verification_sent": True}
    # not switched until the code is entered
    assert get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"] == old_phone

    assert anon.post(f"/api/self-report/{token}/contact/verify", json={"code": "000000"}).status_code == 400
    assert anon.post(f"/api/self-report/{token}/contact/verify", json={"code": "123456"}).status_code == 200
    assert get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"] == new
    # the code works once
    assert anon.post(f"/api/self-report/{token}/contact/verify", json={"code": "123456"}).status_code == 404

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


def _profile_token(trainee_id):
    return _token_from(get_ok(admin, f"/api/trainees/{trainee_id}/profile-link")["link"])


def test_profile_link_from_registration_changes_phone_with_code(isolated_db, monkeypatch):
    monkeypatch.setattr(contact_service, "_new_code", lambda: "424242")
    res = admin.post(
        "/api/trainees",
        json={
            "full_name": "Asha Rane", "dob": "2003-01-02", "gender": "Female", "district": "Pune",
            "phone": new_phone(), "preferred_contact": "SMS", "consent_given": True,
        },
    )
    assert res.status_code == 201
    token = _token_from(res.json()["profile_link"])
    trainee_id = res.json()["trainee_id"]
    assert "/my-profile/" in res.json()["profile_link"]

    # welcome message queued for the trainee, with the link
    welcome = get_ok(admin, "/api/notifications", params={"purpose": "PROFILE_LINK"})
    assert welcome and token in welcome[0]["message"]

    assert anon.get(f"/my-profile/{token}").status_code == 200
    assert get_ok(anon, f"/api/me/{token}/contact")["district"] == "Pune"

    new = new_phone()
    assert anon.patch(f"/api/me/{token}/contact", json={"phone": new}).json()["phone_verification_sent"] is True
    code_msg = get_ok(admin, "/api/notifications", params={"purpose": "PHONE_VERIFICATION"})[0]
    assert code_msg["recipient"] == new and "424242" in code_msg["message"]

    assert anon.post(f"/api/me/{token}/contact/verify", json={"code": "424242"}).status_code == 200
    assert get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"] == new


def test_phone_code_expires_and_locks_after_wrong_attempts(isolated_db, monkeypatch):
    monkeypatch.setattr(contact_service, "_new_code", lambda: "111111")
    trainee_id = make_trainee()
    token = _profile_token(trainee_id)
    anon.patch(f"/api/me/{token}/contact", json={"phone": new_phone()})
    for _ in range(5):
        assert anon.post(f"/api/me/{token}/contact/verify", json={"code": "222222"}).status_code == 400
    assert anon.post(f"/api/me/{token}/contact/verify", json={"code": "111111"}).status_code == 429

    anon.patch(f"/api/me/{token}/contact", json={"phone": new_phone()})
    db = isolated_db()
    for r in db.query(PhoneChangeRequest).all():
        r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()
    assert anon.post(f"/api/me/{token}/contact/verify", json={"code": "111111"}).status_code == 410
    assert anon.post(f"/api/me/{token}/contact/verify", json={"code": "12ab56"}).status_code == 422


def test_profile_link_consent_and_wrong_token_type(isolated_db):
    trainee_id = make_trainee()
    token = _profile_token(trainee_id)
    assert anon.post(f"/api/me/{token}/consent", json={"consent_given": False}).json() == {"consent_given": False}
    assert anon.patch(f"/api/me/{token}/contact", json={"district": "X"}).status_code == 403
    assert anon.post(f"/api/me/{token}/consent", json={"consent_given": True}).status_code == 200

    # a follow-up link is not a profile link, and vice versa
    followup_token = _token_from(get_ok(admin, f"/api/followups/{_due_followup(trainee_id)}/self-report-link")["link"])
    assert anon.get(f"/api/me/{followup_token}/contact").status_code == 404
    assert anon.get(f"/api/self-report/{token}/contact").status_code == 404
    assert anon.get("/api/me/garbage/contact").status_code == 404


def test_request_link_is_uniform_and_rate_limited(isolated_db):
    trainee_id = make_trainee()
    phone = get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"]
    before = len(get_ok(admin, "/api/notifications", params={"purpose": "PROFILE_LINK"}))

    known = anon.post("/api/request-link", json={"identifier": phone})
    unknown = anon.post("/api/request-link", json={"identifier": "9999999999"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()

    after = get_ok(admin, "/api/notifications", params={"purpose": "PROFILE_LINK"})
    assert len(after) == before  # the welcome message just sent counts as recent: no second one
    anon.post("/api/request-link", json={"identifier": trainee_id.lower()})
    assert len(get_ok(admin, "/api/notifications", params={"purpose": "PROFILE_LINK"})) == len(after)


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


def test_consent_evidence_and_history(isolated_db):
    trainee_id = make_trainee(consent_method="Paper form", consent_recorded_by="Officer Patil")
    admin.post(
        f"/api/trainees/{trainee_id}/consent",
        json={"consent_given": False, "method": "Verbal", "recorded_by": "Officer Patil", "notes": "Called us"},
    )
    history = get_ok(admin, f"/api/trainees/{trainee_id}/consent-history")
    assert [(h["source"], h["consent_given"]) for h in history] == [("admin", False), ("registration", True)]
    assert history[1]["method"] == "Paper form" and history[1]["recorded_by"] == "Officer Patil"
    assert history[0]["notes"] == "Called us"

    bad = admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": True, "method": "Telepathy"})
    assert bad.status_code == 422


def test_trainee_withdraws_and_regrants_own_consent(isolated_db):
    trainee_id = make_trainee()
    token = _token_from(get_ok(admin, f"/api/followups/{_due_followup(trainee_id)}/self-report-link")["link"])

    assert anon.post(f"/api/self-report/{token}/consent", json={"consent_given": False}).json() == {
        "consent_given": False
    }
    assert get_ok(admin, f"/api/trainees/{trainee_id}")["consent_given"] is False
    # withdrawn: no more contact updates, but the trainee can still re-grant
    assert anon.patch(f"/api/self-report/{token}/contact", json={"district": "X"}).status_code == 403
    assert anon.post(f"/api/self-report/{token}/consent", json={"consent_given": True}).status_code == 200

    history = get_ok(admin, f"/api/trainees/{trainee_id}/consent-history")
    assert [(h["source"], h["method"], h["consent_given"]) for h in history[:2]] == [
        ("self", "Self-service", True),
        ("self", "Self-service", False),
    ]
    assert anon.post("/api/self-report/garbage/consent", json={"consent_given": False}).status_code == 404


def test_trainee_can_see_own_record_masked_and_without_wages(isolated_db):
    trainee_id = make_trainee(full_name="Sana Shaikh", email="sana@example.com", consent_method="Paper form")
    phone = get_ok(admin, f"/api/trainees/{trainee_id}/contact")["phone"]
    training_id = make_training(trainee_id)
    outcome_id = make_outcome(trainee_id, training_id, "Employed")
    employment_id = make_employment(trainee_id, outcome_id, salary=25000)
    admin.post(f"/api/employment/{employment_id}/verification-request", json={"employer_contact": "hr@x.example"})
    token = _profile_token(trainee_id)

    record = get_ok(anon, f"/api/me/{token}/record")
    profile = record["profile"]
    assert profile["full_name"] == "Sana Shaikh" and profile["trainee_id"] == trainee_id
    assert profile["phone"] != phone and profile["phone"][:2] == phone[:2] and profile["phone"][-2:] == phone[-2:]
    assert profile["email"] == "s•••@example.com"
    assert record["training"][0]["course"] == "Electrician"
    assert record["outcomes"][0]["outcome"] == "Employed"
    assert record["work"][0]["organisation"] == "Volt Works Pvt Ltd"
    assert record["work"][0]["employer_confirmation"] == "Pending"
    assert record["consent"]["given"] is True and record["consent"]["history"][0]["how"] == "Paper form"
    assert record["consent"]["history"][0]["recorded_by"] == "Programme staff"

    raw = anon.get(f"/api/me/{token}/record").text
    assert phone not in raw and "sana@example.com" not in raw and "2002-04-10" not in raw
    assert "25000" not in raw and "salary" not in raw

    # own consent changes show up, attributed to the trainee
    anon.post(f"/api/me/{token}/consent", json={"consent_given": False})
    record = get_ok(anon, f"/api/me/{token}/record")  # still viewable after withdrawing
    assert record["consent"]["given"] is False
    assert record["consent"]["history"][0]["recorded_by"] == "You"

    assert anon.get("/api/me/garbage/record").status_code == 404
