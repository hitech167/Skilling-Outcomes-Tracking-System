"""
Tests for the features that close the remaining problem-statement gaps:

1. Automated follow-up contact (dispatch, channels, outbox, resend guard)
2. Low-burden self-reporting by trainees and confirmation by employers
3. Cross-programme identity (external IDs, lookup, duplicate detection)
4. Consent withdrawal removes a trainee from analytics

Each test gets its own empty in-memory database (the isolated_db fixture in conftest.py).
"""

from datetime import date

import pytest

from services import notification_service
from services.auth import PURPOSE_EMPLOYER_VERIFY, PURPOSE_SELF_REPORT, create_link_token
from tests.test_phase8_hardening import (
    AGGREGATE_ENDPOINTS,
    add_wage,
    admin,
    analyst,
    anon,
    get_ok,
    make_employment,
    make_outcome,
    make_trainee,
    make_training,
    new_phone,
)


def _due_followup(trainee_id: str, followup_type: str = "30_DAY") -> str:
    """Completed training far enough in the past that every follow-up is due."""
    training_id = make_training(trainee_id, start_date="2024-01-01", end_date="2024-06-30")
    assert admin.post(f"/api/followups/generate/{training_id}").status_code == 200
    timeline = get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]
    return next(f["followup_id"] for f in timeline if f["followup_type"] == followup_type)


def _token_from(link: str) -> str:
    return link.rsplit("/", 1)[1]


# =====================================================================
# 1. Automated follow-up contact
# =====================================================================


def test_dispatch_messages_due_followups_by_preferred_channel(isolated_db):
    sms_trainee = make_trainee(full_name="Meera Kale", preferred_contact="SMS")
    email_trainee = make_trainee(
        full_name="Ravi Joshi", preferred_contact="Email", email="ravi@example.com"
    )
    phone_trainee = make_trainee(preferred_contact="Phone")
    withdrawn = make_trainee()
    for t in (sms_trainee, email_trainee, phone_trainee, withdrawn):
        _due_followup(t)
    admin.post(f"/api/trainees/{withdrawn}/consent", json={"consent_given": False})

    summary = admin.post("/api/followups/dispatch-due").json()
    # 4 trainees x 4 follow-ups, all past due. One message per training:
    # the latest due (12_MONTH) check-in; the 3 older ones are superseded.
    assert summary["due_followups"] == 16
    assert summary["skipped_superseded"] == 12
    assert summary["skipped_no_consent"] == 1
    # No SMTP / SMS provider in tests -> everything waits in the outbox
    assert (summary["queued"], summary["sent"], summary["failed"]) == (3, 0, 0)

    outbox = get_ok(admin, "/api/notifications", params={"status": "Queued", "purpose": "FOLLOWUP_REQUEST", "limit": 500})
    assert len(outbox) == 3
    assert "12-month check-in" in outbox[0]["message"]
    channels = {(n["trainee_id"], n["channel"]) for n in outbox}
    assert (sms_trainee, "SMS") in channels
    assert (email_trainee, "Email") in channels
    assert (phone_trainee, "Phone") in channels
    email_msg = next(n for n in outbox if n["channel"] == "Email")
    assert email_msg["recipient"] == "ravi@example.com"
    assert email_msg["trainee_name"] == "Ravi Joshi"
    assert "Ravi" in email_msg["message"] and "/self-report/" in email_msg["message"]
    assert "SMTP_HOST" in email_msg["error"]

    # Re-running within the resend window does not message anyone twice
    again = admin.post("/api/followups/dispatch-due").json()
    assert again["skipped_recently_contacted"] == 3 and again["queued"] == 0

    # Staff work the queue manually
    marked = admin.post(f"/api/notifications/{outbox[0]['notification_id']}/mark-sent")
    assert marked.status_code == 200 and marked.json()["status"] == "Sent"

    # The outbox holds contact details: admin only
    assert analyst.get("/api/notifications").status_code == 403


def test_dispatch_uses_configured_providers(isolated_db, monkeypatch):
    sent = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMS_WEBHOOK_URL", "https://sms.example.test/send")
    monkeypatch.setattr(
        notification_service, "_send_email", lambda to, subject, body: sent.append(("email", to)) or "smtp"
    )

    def failing_sms(to, body):
        raise RuntimeError("gateway rejected")

    monkeypatch.setattr(notification_service, "_send_sms", failing_sms)

    _due_followup(make_trainee(preferred_contact="Email", email="a@example.com"))
    _due_followup(make_trainee(preferred_contact="SMS"))
    sent.clear()  # ignore the welcome messages sent at registration
    summary = admin.post("/api/followups/dispatch-due").json()
    assert (summary["sent"], summary["failed"]) == (1, 1)
    assert sent == [("email", "a@example.com")]
    failed = get_ok(admin, "/api/notifications", params={"status": "Failed"})
    assert failed and "gateway rejected" in failed[0]["error"]


# =====================================================================
# 2a. Trainee self-report
# =====================================================================


def test_self_report_employed_creates_linked_unverified_records(isolated_db):
    trainee_id = make_trainee(full_name="Sana Shaikh")
    followup_id = _due_followup(trainee_id)
    link = get_ok(admin, f"/api/followups/{followup_id}/self-report-link")["link"]
    token = _token_from(link)

    page = anon.get(f"/self-report/{token}")
    assert page.status_code == 200 and "Training check-in" in page.text
    context = get_ok(anon, f"/api/self-report/{token}")
    assert context == {
        "first_name": "Sana", "course_name": "Electrician", "provider_name": "ITI Pune",
        "followup_type": "30_DAY", "already_submitted": False,
    }
    assert "phone" not in context and "trainee_id" not in context

    missing = anon.post(f"/api/self-report/{token}", json={"outcome_type": "Employed"})
    assert missing.status_code == 422  # employer + role required for a job

    res = anon.post(
        f"/api/self-report/{token}",
        json={
            "outcome_type": "employed",
            "organisation_name": "Sun Solar Pvt Ltd",
            "role": "Solar Technician",
            "start_date": "2024-09-01",
            "monthly_income": 16000,
            "training_relevance": 5,
            "skill_gap": True,
            "additional_training_needed": False,
        },
    )
    assert res.status_code == 200, res.text

    followup = get_ok(admin, f"/api/followups/{followup_id}")
    assert followup["status"] == "Completed" and followup["outcome_id"]
    outcome = get_ok(admin, f"/api/outcomes/{followup['outcome_id']}")
    assert outcome["outcome_type"] == "Employed" and "Self-reported" in outcome["notes"]

    employment = get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"][0]
    assert (employment["company_name"], employment["job_role"]) == ("Sun Solar Pvt Ltd", "Solar Technician")
    wages = get_ok(admin, f"/api/employment/{employment['employment_id']}/wage-history")["wage_history"]
    assert [(w["salary"], w["source"], w["verification_status"]) for w in wages] == [
        (16000.0, "Trainee", "Unverified")
    ]
    verification = get_ok(admin, f"/api/employment/{employment['employment_id']}/verification")
    assert verification["verification_status"] == "Pending"  # awaiting employer validation
    assert get_ok(admin, f"/api/followups/{followup_id}/summary")["current_outcome"]["skill_gap"] is True

    # Counted in analytics like any other outcome
    assert get_ok(analyst, "/api/analytics/placement-rate")["placed_trainees"] == 1
    # Single use
    again = anon.post(f"/api/self-report/{token}", json={"outcome_type": "Unemployed"})
    assert again.status_code == 409
    assert get_ok(anon, f"/api/self-report/{token}")["already_submitted"] is True


@pytest.mark.parametrize(
    "report, detail_path",
    [
        ({"outcome_type": "Self-employed", "organisation_name": "Kale Electricals",
          "role": "Electrical repair shop", "monthly_income": 22000}, "self_employment_records"),
        ({"outcome_type": "Apprenticeship", "organisation_name": "MSEDCL",
          "role": "Apprentice Lineman", "monthly_income": 9000}, "apprenticeship_records"),
        ({"outcome_type": "Unemployed", "unemployment_reason": "location problem"}, "non_placement_records"),
        ({"outcome_type": "Further Education"}, None),
    ],
)
def test_self_report_other_outcomes(isolated_db, report, detail_path):
    trainee_id = make_trainee()
    followup_id = _due_followup(trainee_id)
    token = create_link_token(PURPOSE_SELF_REPORT, followup_id)
    assert anon.post(f"/api/self-report/{token}", json=report).status_code == 200

    session = isolated_db()
    from database import models

    tables = {
        "self_employment_records": models.SelfEmploymentRecord,
        "apprenticeship_records": models.ApprenticeshipRecord,
        "non_placement_records": models.NonPlacementRecord,
    }
    for name, model in tables.items():
        assert session.query(model).count() == (1 if name == detail_path else 0), name
    session.close()
    outcomes = get_ok(admin, f"/api/trainees/{trainee_id}/outcomes")["outcomes"]
    assert [o["outcome_type"] for o in outcomes] == [report["outcome_type"]]


def test_link_tokens_cannot_be_forged_or_reused_as_logins(isolated_db):
    trainee_id = make_trainee()
    followup_id = _due_followup(trainee_id)
    self_token = create_link_token(PURPOSE_SELF_REPORT, followup_id)

    # Wrong purpose, garbage, and a login token are all rejected as links
    wrong_purpose = create_link_token(PURPOSE_EMPLOYER_VERIFY, followup_id)
    login_token = admin.headers["Authorization"].split()[1]
    for bad in (wrong_purpose, "garbage", login_token):
        assert anon.get(f"/api/self-report/{bad}").status_code == 404
    # A link token is not a login
    res = anon.get("/api/analytics/overview", headers={"Authorization": f"Bearer {self_token}"})
    assert res.status_code == 401

    # Withdrawn consent blocks the self-report too
    admin.post(f"/api/trainees/{trainee_id}/consent", json={"consent_given": False})
    blocked = anon.post(f"/api/self-report/{self_token}", json={"outcome_type": "Further Education"})
    assert blocked.status_code == 409


# =====================================================================
# 2b. Employer confirmation
# =====================================================================


def test_employer_confirmation_link(isolated_db):
    trainee_id = make_trainee(full_name="Kiran More")
    outcome_id = make_outcome(trainee_id, make_training(trainee_id), "Employed")
    employment_id = make_employment(trainee_id, outcome_id)
    add_wage(trainee_id, employment_id, 15000, "Monthly", "2025-05-15")

    req = admin.post(
        f"/api/employment/{employment_id}/verification-request",
        json={"employer_contact": "hr@voltworks.example"},
    )
    assert req.status_code == 201
    body = req.json()
    assert body["delivery_status"] == "Queued"  # no SMTP in tests
    token = _token_from(body["link"])
    assert get_ok(admin, f"/api/employment/{employment_id}/verification")["verification_status"] == "Pending"

    assert "Employment confirmation" in anon.get(f"/employer-verify/{token}").text
    context = get_ok(anon, f"/api/employer-verify/{token}")
    assert (context["employee_name"], context["company_name"]) == ("Kiran More", "Volt Works Pvt Ltd")

    res = anon.post(
        f"/api/employer-verify/{token}",
        json={"employment_confirmed": True, "current_status": "active", "salary": 216000,
              "salary_period": "annual", "verified_by": "R. Deshmukh, HR"},
    )
    assert res.status_code == 200 and res.json()["verification_status"] == "Verified"

    verification = get_ok(admin, f"/api/employment/{employment_id}/verification")
    assert (verification["verification_status"], verification["verification_method"]) == (
        "Verified", "Employer Portal",
    )
    assert verification["verified_by"] == "R. Deshmukh, HR"
    summary = get_ok(admin, f"/api/employment/{employment_id}/summary")
    assert summary["current_status"] == "Active"
    assert (summary["salary"]["latest"], summary["salary"]["period"]) == (216000.0, "Annual")
    assert summary["salary"]["growth_percentage"] == 20.0  # 15,000 -> 18,000 a month

    assert anon.post(
        f"/api/employer-verify/{token}", json={"employment_confirmed": False, "verified_by": "X Y"}
    ).status_code == 409


def test_employer_can_reject(isolated_db):
    trainee_id = make_trainee()
    employment_id = make_employment(trainee_id, make_outcome(trainee_id, make_training(trainee_id), "Employed"))
    link = admin.post(f"/api/employment/{employment_id}/verification-request", json={}).json()["link"]
    res = anon.post(
        f"/api/employer-verify/{_token_from(link)}",
        json={"employment_confirmed": False, "verified_by": "Owner"},
    )
    assert res.json()["verification_status"] == "Rejected"
    assert get_ok(admin, f"/api/employment/{employment_id}/wage-history")["wage_history"] == []


# =====================================================================
# 3. Cross-programme identity
# =====================================================================


def test_external_ids_link_programmes_and_block_duplicates(isolated_db):
    trainee_id = make_trainee(
        full_name="Pooja Pawar",
        dob="2000-02-02",
        external_ids=[{"id_type": "Skill India Digital ID", "id_value": "sid-778899",
                       "source_programme": "PMKVY 4.0"}],
    )
    res = admin.post(
        f"/api/trainees/{trainee_id}/external-ids",
        json={"id_type": "DDU-GKY Candidate ID", "id_value": "DDU/2025/4411", "source_programme": "DDU-GKY"},
    )
    assert res.status_code == 201
    ids = get_ok(admin, f"/api/trainees/{trainee_id}/external-ids")
    assert [(i["id_type"], i["id_value"]) for i in ids] == [
        ("Skill India Digital ID", "SID-778899"),
        ("DDU-GKY Candidate ID", "DDU/2025/4411"),
    ]

    found = get_ok(admin, "/api/identity/lookup",
                   params={"id_type": "skill india digital id", "id_value": " sid-778899 "})
    assert found["trainee_id"] == trainee_id
    assert admin.get("/api/identity/lookup",
                     params={"id_type": "Skill India Digital ID", "id_value": "NOPE"}).status_code == 404

    # Same person registering again through another programme -> refused, points to the existing ID
    again = admin.post("/api/trainees", json={
        "full_name": "Pooja Pawar", "dob": "2000-02-02", "gender": "Female", "district": "Pune",
        "phone": new_phone(), "preferred_contact": "SMS", "consent_given": True,
        "external_ids": [{"id_type": "Skill India Digital ID", "id_value": "SID-778899"}],
    })
    assert again.status_code == 409 and trainee_id in again.json()["detail"]

    # Linking someone else's ID to another trainee is refused too
    other = make_trainee()
    clash = admin.post(f"/api/trainees/{other}/external-ids",
                       json={"id_type": "DDU-GKY Candidate ID", "id_value": "ddu/2025/4411"})
    assert clash.status_code == 409

    # Aadhaar must never be stored
    for bad in ({"id_type": "Aadhaar", "id_value": "X1"}, {"id_type": "Scheme ID", "id_value": "1234 5678 9012"}):
        assert admin.post(f"/api/trainees/{other}/external-ids", json=bad).status_code == 422


def test_possible_duplicates_are_flagged_not_merged(isolated_db):
    first = make_trainee(full_name="Amit Kumar Singh", dob="1999-09-09")
    res = admin.post("/api/trainees", json={
        "full_name": "amit  kumar singh", "dob": "1999-09-09", "gender": "Male", "district": "Nagpur",
        "phone": new_phone(), "preferred_contact": "SMS", "consent_given": True,
    })
    assert res.status_code == 201
    second = res.json()["trainee_id"]
    assert res.json()["possible_duplicates"] == [first]

    groups = get_ok(admin, "/api/identity/possible-duplicates")
    assert groups["trainees_involved"] == 2
    assert groups["groups"][0]["trainee_ids"] == sorted([first, second])
    assert get_ok(analyst, "/api/insights/data-quality")["possible_duplicate_trainees"] == 2


# =====================================================================
# 4. Consent withdrawal and analytics
# =====================================================================


def test_withdrawn_trainees_are_excluded_from_every_aggregate(isolated_db):
    kept = make_trainee(district="Pune")
    make_outcome(kept, make_training(kept), "Unemployed")

    gone = make_trainee(district="Nashik", gender="Male")
    training = make_training(gone, course_name="Welder")
    employment_id = make_employment(gone, make_outcome(gone, training, "Employed"))
    add_wage(gone, employment_id, 20000, "Monthly", "2025-05-15")
    add_wage(gone, employment_id, 30000, "Monthly", "2025-11-15")

    before = get_ok(analyst, "/api/analytics/placement-rate")
    assert before == {"eligible_trainees": 2, "placed_trainees": 1, "placement_rate": 50.0}

    admin.post(f"/api/trainees/{gone}/consent", json={"consent_given": False})

    assert get_ok(analyst, "/api/analytics/placement-rate") == {
        "eligible_trainees": 1, "placed_trainees": 0, "placement_rate": 0.0,
    }
    overview = get_ok(analyst, "/api/analytics/overview")
    assert overview["total_trainees"] == 1 and overview["employed_trainees"] == 0
    assert get_ok(analyst, "/api/analytics/wage-progression")["employment_records"] == 0
    assert [c["course_name"] for c in get_ok(analyst, "/api/analytics/course-performance")] == ["Electrician"]
    assert [d["district"] for d in get_ok(analyst, "/api/insights/resource-allocation")] == ["Pune"]
    genders = {g["gender"] for g in get_ok(analyst, "/api/analytics/demographics")["gender_distribution"]}
    assert genders == {"Female"}
    assert get_ok(analyst, "/api/insights/data-quality")["trainees_consent_withdrawn_excluded"] == 1
    for path in AGGREGATE_ENDPOINTS:
        assert analyst.get(path).status_code == 200, path

    # Nothing was deleted: admins still see the record, and re-granting restores it
    assert get_ok(admin, f"/api/trainees/{gone}/employment-history")["employment_history"]
    admin.post(f"/api/trainees/{gone}/consent", json={"consent_given": True})
    assert get_ok(analyst, "/api/analytics/placement-rate")["placed_trainees"] == 1


def test_dispatch_is_admin_only_and_links_are_public(isolated_db):
    assert anon.post("/api/followups/dispatch-due").status_code == 401
    assert analyst.post("/api/followups/dispatch-due").status_code == 403
    assert anon.get(f"/api/self-report/{create_link_token(PURPOSE_SELF_REPORT, 'FUP999999')}").status_code == 404
    assert date.today()  # links are validated against the DB, not just the signature


def test_repeat_self_reports_extend_the_same_job(isolated_db):
    trainee_id = make_trainee()
    training_id = make_training(trainee_id, start_date="2024-01-01", end_date="2024-06-30")
    admin.post(f"/api/followups/generate/{training_id}")
    followups = get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]

    job = {"outcome_type": "Employed", "organisation_name": "MahaElectric Contractors",
           "role": "Junior Electrician", "start_date": "2024-08-01"}
    for fu, income in zip(followups, (18000, 18000, 20000, 20000)):
        token = create_link_token(PURPOSE_SELF_REPORT, fu["followup_id"])
        body = dict(job, monthly_income=income)
        if fu["followup_type"] == "12_MONTH":
            body["organisation_name"] = "  mahaelectric   CONTRACTORS "  # same employer, typed differently
        assert anon.post(f"/api/self-report/{token}", json=body).status_code == 200

    jobs = get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"]
    assert len(jobs) == 1  # one job, not four
    wages = get_ok(admin, f"/api/employment/{jobs[0]['employment_id']}/wage-history")["wage_history"]
    assert [w["salary"] for w in wages] == [18000.0, 20000.0]  # a new point only when it changed
    # Every check-in is still recorded as an outcome over time
    assert len(get_ok(admin, f"/api/trainees/{trainee_id}/outcomes")["outcomes"]) == 4
    assert get_ok(analyst, "/api/analytics/placement-rate")["placed_trainees"] == 1

    # A different employer is a genuinely new job
    other = make_training(trainee_id, course_name="Solar PV Installer", start_date="2024-01-01", end_date="2024-06-30")
    admin.post(f"/api/followups/generate/{other}")
    fu = next(f for f in get_ok(admin, f"/api/trainees/{trainee_id}/followup-timeline")["followups"]
              if f["training_id"] == other)
    token = create_link_token(PURPOSE_SELF_REPORT, fu["followup_id"])
    anon.post(f"/api/self-report/{token}", json=dict(job, organisation_name="SunGrid Solar"))
    assert len(get_ok(admin, f"/api/trainees/{trainee_id}/employment-history")["employment_history"]) == 2
