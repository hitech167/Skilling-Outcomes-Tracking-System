"""
Low-burden data capture + automated follow-up contact.

Public (no login — access is by signed, single-use, expiring link):
    GET  /self-report/{token}               -> mobile-friendly form for the trainee
    GET  /api/self-report/{token}           -> form context (no contact details)
    POST /api/self-report/{token}           -> trainee reports current situation
    GET  /employer-verify/{token}           -> form for the employer
    GET  /api/employer-verify/{token}       -> form context
    POST /api/employer-verify/{token}       -> employer confirms employment / salary

Admin:
    POST /api/followups/dispatch-due                    -> message every due follow-up
    GET  /api/followups/{followup_id}/self-report-link   -> link to share manually
    POST /api/employment/{employment_id}/verification-request -> employer link
    GET  /api/notifications                              -> outbox
    POST /api/notifications/{notification_id}/mark-sent  -> staff sent/called manually
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import FollowUp, Notification, Trainee
from routes._shared import get_employment_or_404
from routes.followup import get_followup_or_404
from schemas.self_service import (
    DispatchSummary,
    EmployerVerifyContext,
    EmployerVerifyResult,
    EmployerVerifySubmission,
    NotificationItem,
    SelfReportContext,
    SelfReportLinkResponse,
    SelfReportResult,
    SelfReportSubmission,
    VerificationRequestCreate,
    VerificationRequestResponse,
)
from services import notification_service, self_service
from services.auth import (
    PURPOSE_EMPLOYER_VERIFY,
    PURPOSE_SELF_REPORT,
    read_link_token,
)

logger = logging.getLogger(__name__)

public_router = APIRouter(tags=["Self-service links (public)"])
admin_router = APIRouter(tags=["Automated follow-up & verification links"])


# =====================================================================
# Public: trainee self-report
# =====================================================================


@public_router.get("/api/self-report/{token}", response_model=SelfReportContext, summary="Self-report form context")
def self_report_context(token: str, db: Session = Depends(get_db)):
    followup_id = read_link_token(token, PURPOSE_SELF_REPORT)
    followup, trainee, training = self_service.load_followup_context(db, followup_id)
    return SelfReportContext(
        first_name=trainee.full_name.split()[0],
        course_name=training.course_name,
        provider_name=training.provider_name,
        followup_type=followup.followup_type,
        already_submitted=followup.status != "Scheduled",
    )


@public_router.post("/api/self-report/{token}", response_model=SelfReportResult, summary="Trainee reports their current situation")
def self_report_submit(token: str, payload: SelfReportSubmission, db: Session = Depends(get_db)):
    followup_id = read_link_token(token, PURPOSE_SELF_REPORT)
    self_service.submit_self_report(db, followup_id, payload)
    logger.info("Self-report recorded for follow-up %s", followup_id)
    return SelfReportResult()


# =====================================================================
# Public: employer confirmation
# =====================================================================


@public_router.get("/api/employer-verify/{token}", response_model=EmployerVerifyContext, summary="Employer confirmation form context")
def employer_verify_context(token: str, db: Session = Depends(get_db)):
    verification_id = read_link_token(token, PURPOSE_EMPLOYER_VERIFY)
    verification, employment, trainee = self_service.load_verification_context(db, verification_id)
    return EmployerVerifyContext(
        company_name=employment.company_name,
        employee_name=trainee.full_name,
        job_role=employment.job_role,
        joining_date=employment.joining_date,
        already_submitted=verification.verification_status != "Pending",
    )


@public_router.post("/api/employer-verify/{token}", response_model=EmployerVerifyResult, summary="Employer confirms employment and salary")
def employer_verify_submit(token: str, payload: EmployerVerifySubmission, db: Session = Depends(get_db)):
    verification_id = read_link_token(token, PURPOSE_EMPLOYER_VERIFY)
    result = self_service.submit_employer_confirmation(db, verification_id, payload)
    logger.info("Employer confirmation recorded for %s -> %s", verification_id, result)
    return EmployerVerifyResult(verification_status=result)


# =====================================================================
# Admin: automated dispatch, links, outbox
# =====================================================================


@admin_router.post(
    "/api/followups/dispatch-due",
    response_model=DispatchSummary,
    summary="Automatically message every due follow-up with a self-report link",
)
def dispatch_due_followups(db: Session = Depends(get_db)):
    return notification_service.dispatch_due_followups(db)


@admin_router.get(
    "/api/followups/{followup_id}/self-report-link",
    response_model=SelfReportLinkResponse,
    summary="Get a follow-up's self-report link to share manually",
)
def get_self_report_link(followup_id: str, db: Session = Depends(get_db)):
    followup = get_followup_or_404(followup_id, db)
    return SelfReportLinkResponse(
        followup_id=followup.followup_id,
        link=notification_service.self_report_link(followup),
        valid_days=notification_service.LINK_VALID_DAYS,
    )


@admin_router.post(
    "/api/employment/{employment_id}/verification-request",
    response_model=VerificationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employer confirmation link (emailed if the contact is an email and SMTP is set up)",
)
def create_verification_request(
    employment_id: str, payload: VerificationRequestCreate, db: Session = Depends(get_db)
):
    employment = get_employment_or_404(employment_id, db)
    verification = self_service.create_verification_request(db, employment, payload.employer_contact)
    link = notification_service.employer_verify_link(verification.verification_id)

    notification = None
    contact = (payload.employer_contact or "").strip()
    if contact:
        channel = "Email" if "@" in contact else "SMS"
        notification = Notification(
            notification_id=notification_service.generate_notification_id(db),
            trainee_pk_id=employment.trainee_pk_id,
            purpose="EMPLOYER_VERIFICATION",
            channel=channel,
            recipient=contact,
            message=(
                f"Please confirm the employment of a trainee at {employment.company_name} "
                f"({employment.job_role}). It takes one minute: {link}"
            ),
        )
        notification_service.deliver(notification, subject="Employment confirmation request")
        db.add(notification)
    db.commit()

    return VerificationRequestResponse(
        verification_id=verification.verification_id,
        employment_id=employment.employment_id,
        link=link,
        valid_days=notification_service.VERIFICATION_LINK_DAYS,
        notification_id=notification.notification_id if notification else None,
        delivery_status=notification.status if notification else None,
    )


def _notification_item(n: Notification, db: Session) -> NotificationItem:
    trainee_id, trainee_name = (
        db.query(Trainee.trainee_id, Trainee.full_name).filter(Trainee.id == n.trainee_pk_id).one()
    )
    followup_id = None
    if n.followup_pk_id is not None:
        followup_id = db.query(FollowUp.followup_id).filter(FollowUp.id == n.followup_pk_id).scalar()
    return NotificationItem(
        notification_id=n.notification_id,
        trainee_id=trainee_id,
        trainee_name=trainee_name,
        followup_id=followup_id,
        purpose=n.purpose,
        channel=n.channel,
        recipient=n.recipient,
        message=n.message,
        status=n.status,
        provider=n.provider,
        error=n.error,
        created_at=n.created_at,
        sent_at=n.sent_at,
    )


@admin_router.get(
    "/api/notifications",
    response_model=list[NotificationItem],
    summary="Outbox of automated messages (filter by status, e.g. Queued for staff to action)",
)
def list_notifications(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Notification)
    if status_filter:
        query = query.filter(Notification.status == status_filter.strip().capitalize())
    rows = query.order_by(Notification.id.desc()).limit(limit).all()
    return [_notification_item(n, db) for n in rows]


@admin_router.post(
    "/api/notifications/{notification_id}/mark-sent",
    response_model=NotificationItem,
    summary="Record that staff sent or phoned a queued message manually",
)
def mark_notification_sent(notification_id: str, db: Session = Depends(get_db)):
    n = (
        db.query(Notification)
        .filter(Notification.notification_id == notification_id.strip().upper())
        .first()
    )
    if n is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No notification {notification_id}")
    n.status = "Sent"
    n.provider = "manual"
    n.error = None
    n.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(n)
    return _notification_item(n, db)


# =====================================================================
# Public HTML forms (no framework, no external assets)
# =====================================================================

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>__TITLE__</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f4f6f8;color:#1c2430}
 main{max-width:520px;margin:0 auto;padding:20px 16px 40px}
 h1{font-size:1.35rem;margin:8px 0 4px} p.sub{color:#556;margin:0 0 18px}
 form{background:#fff;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
 label{display:block;font-weight:600;margin:14px 0 6px}
 input,select,textarea{width:100%;box-sizing:border-box;padding:10px;border:1px solid #c9d1da;border-radius:8px;font-size:1rem}
 .row{display:flex;gap:10px} .row>*{flex:1}
 button:disabled{opacity:.6} button{margin-top:20px;width:100%;padding:12px;border:0;border-radius:8px;background:#1f6feb;color:#fff;font-size:1rem;font-weight:600}
 .hidden{display:none} .msg{padding:14px;border-radius:10px;background:#e7f5ec;color:#1b5e33;margin-top:14px}
 .err{background:#fdecea;color:#8a1c1c}
</style></head><body><main>
<h1 id="title">__TITLE__</h1><p class="sub" id="sub">Loading…</p>
__FORM__
<div id="msg" class="msg hidden" role="status"></div>
</main><script>
const token = location.pathname.split("/").pop();
const api = "__API__" + token;
const $ = id => document.getElementById(id);
function show(text, bad){ const m=$("msg"); m.textContent=text; m.className="msg"+(bad?" err":""); }
__SCRIPT__
</script></body></html>"""

_SELF_REPORT_FORM = """<form id="f" class="hidden">
<label for="outcome_type">What are you doing now?</label>
<select id="outcome_type" required>
 <option value="Employed">Working in a job</option>
 <option value="Self-employed">Running my own work / business</option>
 <option value="Apprenticeship">Apprenticeship</option>
 <option value="Unemployed">Looking for work</option>
 <option value="Further Education">Studying further</option>
</select>
<div id="work">
 <label for="organisation_name" id="org_label">Employer / business name</label><input id="organisation_name" maxlength="200">
 <label for="role">Job role / type of work</label><input id="role" maxlength="150">
 <div class="row"><div><label for="start_date">Since</label><input id="start_date" type="date"></div>
 <div><label for="monthly_income">Monthly income (₹)</label><input id="monthly_income" type="number" min="0" inputmode="numeric"></div></div>
</div>
<div id="reason_box" class="hidden"><label for="unemployment_reason">Main reason</label>
<select id="unemployment_reason"><option value="">Prefer not to say</option>
<option>Skill Gap</option><option>Lack of Jobs</option><option>Low Salary</option><option>Location Problem</option>
<option>Relocation Issue</option><option>Personal/Family Reason</option><option>Other</option></select></div>
<label for="training_relevance">How useful was the training for what you do now?</label>
<select id="training_relevance"><option value="">Skip</option><option value="5">5 – Very useful</option><option value="4">4</option>
<option value="3">3</option><option value="2">2</option><option value="1">1 – Not useful</option></select>
<label><input type="checkbox" id="skill_gap" style="width:auto"> I need skills the course did not cover</label>
<label><input type="checkbox" id="additional_training_needed" style="width:auto"> I would like more training</label>
<button type="submit" data-label="Send update">Send update</button></form>"""

_SELF_REPORT_SCRIPT = """
const placed = ["Employed","Self-employed","Apprenticeship"];
function toggle(){ const t=$("outcome_type").value;
  $("work").classList.toggle("hidden", !placed.includes(t));
  $("reason_box").classList.toggle("hidden", t!=="Unemployed"); }
$("outcome_type").onchange = toggle;
fetch(api).then(r => r.ok ? r.json() : Promise.reject(r)).then(c => {
  $("sub").textContent = `Hi ${c.first_name} — your check-in after ${c.course_name} (${c.provider_name}).`;
  if (c.already_submitted) { show("You have already sent this update. Thank you!"); return; }
  $("f").classList.remove("hidden"); toggle();
}).catch(() => { $("sub").textContent = ""; show("This link is invalid or has expired.", true); });
$("f").onsubmit = async e => { e.preventDefault();
  const t = $("outcome_type").value, v = id => $(id).value.trim() || null;
  const body = { outcome_type: t, training_relevance: v("training_relevance") ? Number(v("training_relevance")) : null,
    skill_gap: $("skill_gap").checked, additional_training_needed: $("additional_training_needed").checked };
  if (placed.includes(t)) Object.assign(body, { organisation_name: v("organisation_name"), role: v("role"),
    start_date: v("start_date"), monthly_income: v("monthly_income") ? Number(v("monthly_income")) : null });
  if (t === "Unemployed") body.unemployment_reason = v("unemployment_reason");
  const btn = $("f").querySelector("button"); if (btn.disabled) return;
  btn.disabled = true; btn.textContent = "Sending…";
  const r = await fetch(api, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)})
    .catch(() => null);
  btn.disabled = false; btn.textContent = btn.dataset.label;
  if (!r) { show("Network problem — please try again.", true); return; }
  const d = await r.json().catch(() => ({}));
  if (r.ok) { $("f").classList.add("hidden"); show(d.message); }
  else show(typeof d.detail === "string" ? d.detail : "Please fill in the employer/business name and role.", true);
};"""

_EMPLOYER_FORM = """<form id="f" class="hidden">
<label for="employment_confirmed">Did this person work for you in this role?</label>
<select id="employment_confirmed"><option value="true">Yes</option><option value="false">No</option></select>
<div id="more"><label for="current_status">Current status</label>
<select id="current_status"><option>Active</option><option>On Leave</option><option>Left Job</option><option>Terminated</option></select>
<div class="row"><div><label for="salary">Current salary (₹)</label><input id="salary" type="number" min="0" inputmode="numeric"></div>
<div><label for="salary_period">Per</label><select id="salary_period"><option>Monthly</option><option>Annual</option></select></div></div></div>
<label for="verified_by">Your name and designation</label><input id="verified_by" required maxlength="150">
<button type="submit" data-label="Confirm">Confirm</button></form>"""

_EMPLOYER_SCRIPT = """
$("employment_confirmed").onchange = () => $("more").classList.toggle("hidden", $("employment_confirmed").value !== "true");
fetch(api).then(r => r.ok ? r.json() : Promise.reject(r)).then(c => {
  $("sub").textContent = `${c.employee_name} — ${c.job_role} at ${c.company_name}, joined ${c.joining_date}.`;
  if (c.already_submitted) { show("This confirmation has already been submitted. Thank you!"); return; }
  $("f").classList.remove("hidden");
}).catch(() => { $("sub").textContent = ""; show("This link is invalid or has expired.", true); });
$("f").onsubmit = async e => { e.preventDefault();
  const yes = $("employment_confirmed").value === "true";
  const body = { employment_confirmed: yes, verified_by: $("verified_by").value.trim() };
  if (yes) Object.assign(body, { current_status: $("current_status").value,
    salary: $("salary").value ? Number($("salary").value) : null, salary_period: $("salary_period").value });
  const btn = $("f").querySelector("button"); if (btn.disabled) return;
  btn.disabled = true; btn.textContent = "Sending…";
  const r = await fetch(api, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)})
    .catch(() => null);
  btn.disabled = false; btn.textContent = btn.dataset.label;
  if (!r) { show("Network problem — please try again.", true); return; }
  const d = await r.json().catch(() => ({}));
  if (r.ok) { $("f").classList.add("hidden"); show(d.message); }
  else show(typeof d.detail === "string" ? d.detail : "Please check the form and try again.", true);
};"""


def _page(title: str, form: str, api: str, script: str) -> str:
    return (
        _PAGE.replace("__TITLE__", title)
        .replace("__FORM__", form)
        .replace("__API__", api)
        .replace("__SCRIPT__", script)
    )


_SELF_REPORT_HTML = _page("Training check-in", _SELF_REPORT_FORM, "/api/self-report/", _SELF_REPORT_SCRIPT)
_EMPLOYER_HTML = _page("Employment confirmation", _EMPLOYER_FORM, "/api/employer-verify/", _EMPLOYER_SCRIPT)
_NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


@public_router.get("/self-report/{token}", response_class=HTMLResponse, include_in_schema=False)
def self_report_page(token: str):
    return HTMLResponse(_SELF_REPORT_HTML, headers=_NO_STORE)


@public_router.get("/employer-verify/{token}", response_class=HTMLResponse, include_in_schema=False)
def employer_verify_page(token: str):
    return HTMLResponse(_EMPLOYER_HTML, headers=_NO_STORE)
