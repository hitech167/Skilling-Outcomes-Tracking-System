"""
Trainee profile link: update phone / location and manage consent at any time.

Public (no login - access is by a signed link valid ~18 months, created at
registration and re-sent on request):
    GET   /my-profile/{token}                -> mobile-friendly page
    GET   /api/me/{token}/contact            -> current district / location / preference
    GET   /api/me/{token}/record             -> the trainee's own record (masked contact, no wages) + consent history
    PATCH /api/me/{token}/contact            -> update; a NEW phone number needs a code
    POST  /api/me/{token}/contact/verify     -> enter the 6-digit code sent to the new number
    POST  /api/me/{token}/consent            -> withdraw / re-grant consent
    POST  /api/request-link                  -> "send me my link again" (trainee ID or phone)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Trainee
from routes.self_service import _NO_STORE, _page
from schemas.trainee import (
    LinkRequest,
    PhoneVerifyRequest,
    SelfConsentUpdate,
    TraineeContactUpdate,
)
from services import consent_service, contact_service, notification_service, trainee_record_service
from services.auth import PURPOSE_PROFILE, read_link_token

logger = logging.getLogger(__name__)

public_router = APIRouter(tags=["Trainee profile link (public)"])

LINK_REQUEST_REPLY = {"message": "If those details match a registered trainee, a new link has been sent."}


def _trainee_from_token(token: str, db: Session) -> Trainee:
    trainee_id = read_link_token(token, PURPOSE_PROFILE)
    trainee = db.query(Trainee).filter(Trainee.trainee_id == trainee_id).first()
    if trainee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is invalid or has expired.")
    return trainee


@public_router.get("/api/me/{token}/contact", summary="Trainee's current location and contact preference")
def my_contact(token: str, db: Session = Depends(get_db)):
    trainee = _trainee_from_token(token, db)
    return {
        "first_name": trainee.full_name.split()[0],
        "district": trainee.district,
        "current_location": trainee.current_location,
        "preferred_contact": trainee.preferred_contact,
        "consent_given": trainee.consent_given,
    }


@public_router.get("/api/me/{token}/record", summary="The trainee's own record: profile, consent history, training, outcomes, follow-ups")
def my_record(token: str, db: Session = Depends(get_db)):
    trainee = _trainee_from_token(token, db)
    return trainee_record_service.build_record(db, trainee)


@public_router.patch("/api/me/{token}/contact", summary="Trainee updates their own contact details")
def update_my_contact(token: str, payload: TraineeContactUpdate, db: Session = Depends(get_db)):
    trainee = _trainee_from_token(token, db)
    result = contact_service.self_update(db, trainee, payload.model_dump(exclude_unset=True))
    logger.info("Trainee %s updated own contact details via profile link", trainee.trainee_id)
    return result


@public_router.post("/api/me/{token}/contact/verify", summary="Confirm a new phone number with the code sent to it")
def verify_my_phone(token: str, payload: PhoneVerifyRequest, db: Session = Depends(get_db)):
    trainee = _trainee_from_token(token, db)
    result = contact_service.verify_phone_change(db, trainee, payload.code)
    logger.info("Trainee %s verified a new phone number", trainee.trainee_id)
    return result


@public_router.post("/api/me/{token}/consent", summary="Trainee withdraws or re-grants their own consent")
def my_consent(token: str, payload: SelfConsentUpdate, db: Session = Depends(get_db)):
    trainee = _trainee_from_token(token, db)
    consent_service.set_consent(db, trainee, payload.consent_given, source="self", method="Self-service")
    db.commit()
    logger.info("Trainee %s set own consent to %s", trainee.trainee_id, payload.consent_given)
    return {"consent_given": trainee.consent_given}


@public_router.post("/api/request-link", summary="Send a trainee their profile link again")
def request_link(payload: LinkRequest, db: Session = Depends(get_db)):
    """
    Always answers the same way, so it cannot be used to find out who is
    registered. The link goes to the phone / email already on file, at most
    once an hour per trainee.
    """
    identifier = payload.identifier.strip()
    digits = "".join(ch for ch in identifier if ch.isdigit())[-10:]
    trainee = (
        db.query(Trainee)
        .filter((Trainee.trainee_id == identifier.upper()) | (Trainee.phone == digits))
        .first()
    )
    if trainee is not None and not notification_service.profile_link_recently_sent(db, trainee):
        notification_service.send_profile_link(db, trainee)
        db.commit()
    return LINK_REQUEST_REPLY


# ---------------------------------------------------------------------
# Mobile page
# ---------------------------------------------------------------------

_PROFILE_FORM = """<form id="f" class="hidden">
<label for="phone">New mobile number (leave blank to keep the current one)</label>
<input id="phone" inputmode="numeric" maxlength="15" placeholder="10-digit number">
<label for="email">Email (leave blank to keep the current one)</label>
<input id="email" type="email" maxlength="255">
<label for="district">District</label><input id="district" maxlength="100">
<label for="current_location">Town / area</label><input id="current_location" maxlength="150">
<label for="preferred_contact">How should we contact you?</label>
<select id="preferred_contact"><option>SMS</option><option>Email</option><option>Phone</option></select>
<button type="submit" data-label="Save">Save</button></form>
<form id="v" class="hidden"><label for="code">Enter the 6-digit code sent to your new number</label>
<input id="code" inputmode="numeric" maxlength="6" required>
<button type="submit" data-label="Confirm number">Confirm number</button></form>
<section id="rec" class="hidden"></section>
<form id="c" class="hidden"><button type="submit" data-label="Withdraw my consent" id="cbtn">Withdraw my consent</button></form>"""

_PROFILE_SCRIPT = """
let consent = true;
async function call(path, method, body){
  const r = await fetch(api + path, {method, headers:{"Content-Type":"application/json"}, body: body ? JSON.stringify(body) : undefined}).catch(() => null);
  if (!r) { show("Network problem — please try again.", true); return null; }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { show(typeof d.detail === "string" ? d.detail : "Please check the details and try again.", true); return null; }
  return d;
}
function fill(c){ consent = c.consent_given;
  $("sub").textContent = `Hi ${c.first_name} — keep your details up to date.`;
  $("district").value = c.district; $("current_location").value = c.current_location || "";
  $("preferred_contact").value = c.preferred_contact;
  $("f").classList.toggle("hidden", !consent);
  $("cbtn").textContent = consent ? "Withdraw my consent" : "Give my consent again";
  $("c").classList.remove("hidden"); }
function el(tag, text, cls){ const e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; return e; }
function section(title, lines){ const box = el("div", ""); box.style.cssText = "margin:14px 0";
  box.appendChild(el("h3", title)); if (!lines.length) box.appendChild(el("p", "Nothing recorded yet."));
  lines.forEach(t => box.appendChild(el("p", t))); return box; }
const d = v => v || "—";
function renderRecord(r){ const rec = $("rec"); rec.replaceChildren();
  const p = r.profile;
  rec.appendChild(section("What we hold about you", [`Trainee ID: ${p.trainee_id}`, `Name: ${p.full_name}`,
    `Phone: ${p.phone}`, `Email: ${d(p.email)}`, `Place: ${d(p.current_location)}, ${p.district}`]));
  rec.appendChild(section("Your consent", [r.consent.given ? "You have given consent." : "Consent is withdrawn."]
    .concat(r.consent.history.map(h => `${h.consent_given ? "Given" : "Withdrawn"} on ${String(h.when).slice(0,10)} (${d(h.how)}, recorded by ${h.recorded_by})`))));
  rec.appendChild(section("Your training", r.training.map(t => `${t.course} at ${t.provider}: ${t.start_date} to ${d(t.end_date)}, ${t.status}${t.certificate_issued ? ", certificate issued" : ""}`)));
  rec.appendChild(section("Work since training", r.work.map(w => `${w.type}: ${w.role} at ${w.organisation}, since ${w.since}${w.employer_confirmation ? " (employer: " + w.employer_confirmation + ")" : ""}`)));
  rec.appendChild(section("Your check-ins", r.follow_ups.map(f => `${f.type.replace("_", " ").toLowerCase()} check-in due ${f.due}: ${f.status}`)));
  rec.classList.remove("hidden"); }
fetch(api + "/record").then(r => r.ok ? r.json() : null).then(r => { if (r) renderRecord(r); });
fetch(api + "/contact").then(r => r.ok ? r.json() : Promise.reject(r)).then(fill)
  .catch(() => { $("sub").textContent = ""; show("This link is invalid or has expired.", true); });
$("f").onsubmit = async e => { e.preventDefault();
  const body = { district: $("district").value.trim(), current_location: $("current_location").value.trim() || null,
    preferred_contact: $("preferred_contact").value };
  if ($("phone").value.trim()) body.phone = $("phone").value.trim();
  if ($("email").value.trim()) body.email = $("email").value.trim();
  const d = await call("/contact", "PATCH", body); if (!d) return;
  if (d.phone_verification_sent) { $("v").classList.remove("hidden"); show("Saved. We sent a code to your new number — enter it below to finish."); }
  else show("Saved. Thank you!");
  fetch(api + "/record").then(r => r.ok ? r.json() : null).then(r => { if (r) renderRecord(r); }); };
$("v").onsubmit = async e => { e.preventDefault();
  const d = await call("/contact/verify", "POST", {code: $("code").value.trim()}); if (!d) return;
  $("v").classList.add("hidden"); $("phone").value = ""; show("Your new number is saved.");
  fetch(api + "/record").then(r => r.ok ? r.json() : null).then(r => { if (r) renderRecord(r); }); };
$("c").onsubmit = async e => { e.preventDefault();
  const d = await call("/consent", "POST", {consent_given: !consent}); if (!d) return;
  consent = d.consent_given; $("f").classList.toggle("hidden", !consent);
  $("cbtn").textContent = consent ? "Withdraw my consent" : "Give my consent again";
  show(consent ? "Consent recorded. Thank you!" : "Your consent has been withdrawn. We will not contact you.");
  fetch(api + "/record").then(r => r.ok ? r.json() : null).then(r => { if (r) renderRecord(r); }); };"""

_PROFILE_HTML = _page("My details", _PROFILE_FORM, "/api/me/", _PROFILE_SCRIPT)


@public_router.get("/my-profile/{token}", response_class=HTMLResponse, include_in_schema=False)
def my_profile_page(token: str):
    return HTMLResponse(_PROFILE_HTML, headers=_NO_STORE)
