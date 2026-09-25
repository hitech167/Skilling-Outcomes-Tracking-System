"""
Automated follow-up contact.

dispatch_due_followups() finds follow-ups that are due, still Scheduled,
belong to a trainee with active consent, and have not been messaged in
the last RESEND_AFTER_DAYS. Only the most recent due check-in of each
training is messaged, so a trainee with a backlog gets one message. For each it creates a personal self-report
link and sends it on the trainee's preferred channel:

    Email -> SMTP, when SMTP_HOST is configured
    SMS   -> HTTP gateway webhook, when SMS_WEBHOOK_URL is configured
    Phone -> always queued for a staff call (assisted follow-up)

Every message is written to the notifications table (the outbox) with
status Sent / Queued / Failed, so nothing is silently dropped when a
provider isn't configured yet — staff can work the queue manually.

Environment (all optional):
    PUBLIC_BASE_URL          base for links, default http://127.0.0.1:8000
    SMTP_HOST, SMTP_PORT (587), SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM,
    SMTP_STARTTLS (true)
    SMS_WEBHOOK_URL, SMS_WEBHOOK_TOKEN   POST {"to", "message"} as JSON
"""

import json
import logging
import os
import smtplib
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.models import FollowUp, Notification, Trainee, TrainingRecord
from services.auth import PURPOSE_SELF_REPORT, create_link_token

logger = logging.getLogger(__name__)

RESEND_AFTER_DAYS = 7
LINK_VALID_DAYS = 30
FOLLOWUP_LABELS = {
    "30_DAY": "30-day",
    "90_DAY": "90-day",
    "6_MONTH": "6-month",
    "12_MONTH": "12-month",
}


def public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def generate_notification_id(db: Session) -> str:
    next_number = db.execute(text("SELECT nextval('notification_id_seq')")).scalar()
    return f"NTF{next_number:06d}"


def self_report_link(followup: FollowUp) -> str:
    token = create_link_token(PURPOSE_SELF_REPORT, followup.followup_id, LINK_VALID_DAYS)
    return f"{public_base_url()}/self-report/{token}"


# ---------------------------------------------------------------------
# Delivery providers
# ---------------------------------------------------------------------


def _send_email(recipient: str, subject: str, body: str) -> str:
    host = os.getenv("SMTP_HOST")
    if not host:
        raise LookupError("no email provider configured (set SMTP_HOST)")
    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME", "")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() != "false":
            smtp.starttls()
        if os.getenv("SMTP_USERNAME"):
            smtp.login(os.getenv("SMTP_USERNAME"), (os.getenv("SMTP_PASSWORD", "") or "").strip())
        smtp.send_message(message)
    return "smtp"


def send_attempt_notification(
    db: Session,
    followup: FollowUp,
    trainee: Trainee,
    notes: str | None = None,
) -> bool:
    """
    Send a notification containing the logged attempt notes directly to the trainee.
    Prefers SMS if SMS gateway is configured, or SMTP email if configured.
    Falls back to Email-to-SMS if SMS_EMAIL_GATEWAY is configured.
    Returns True if notification was sent successfully, False otherwise.
    """
    has_smtp = bool(os.getenv("SMTP_HOST"))
    has_sms = bool(os.getenv("SMS_WEBHOOK_URL"))
    sms_email_gateway = os.getenv("SMS_EMAIL_GATEWAY")

    channel = None
    recipient = None

    # Priority selection of notification channel
    if has_sms and trainee.phone and trainee.preferred_contact in ("SMS", "WhatsApp"):
        channel = "SMS"
        recipient = trainee.phone
    elif has_smtp and trainee.email:
        channel = "Email"
        recipient = trainee.email
    elif has_sms and trainee.phone:
        channel = "SMS"
        recipient = trainee.phone
    elif has_smtp and sms_email_gateway and trainee.phone:
        channel = "Email"
        clean_phone = trainee.phone.lstrip("+").strip()
        recipient = f"{clean_phone}@{sms_email_gateway.lstrip('@').strip()}"
    elif has_smtp and trainee.email:
        channel = "Email"
        recipient = trainee.email

    if not channel or not recipient:
        logger.info(
            "No available notification channel for trainee %s (phone=%s, email=%s)",
            trainee.trainee_id,
            trainee.phone,
            trainee.email,
        )
        return False

    training = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.id == followup.training_record_pk_id)
        .first()
    )
    course_name = training.course_name if training else "Training Program"
    label = FOLLOWUP_LABELS.get(followup.followup_type, followup.followup_type)
    first_name = (trainee.full_name or "Trainee").split()[0]
    notes_clean = (notes or "").strip() or "A follow-up contact attempt was logged by staff."

    subject = f"Follow-up Update: {course_name} ({label} Check-in)"
    body = (
        f"Hello {first_name},\n\n"
        f"This is an update regarding your {label} follow-up for the {course_name} course.\n\n"
        f"Staff outreach notes:\n{notes_clean}\n\n"
        f"If you have any questions or updates regarding your status, please feel free to reach out to us.\n\n"
        f"Best regards,\nSkilling Outcomes Team"
    )

    try:
        notification = Notification(
            notification_id=generate_notification_id(db),
            trainee_pk_id=trainee.id,
            followup_pk_id=followup.id,
            purpose="FOLLOWUP_ATTEMPT",
            channel=channel,
            recipient=recipient,
            message=body,
        )
        deliver(notification, subject=subject)
        db.add(notification)
        return notification.status == "Sent"
    except Exception as exc:
        logger.warning("Error creating or delivering attempt notification: %s", exc)
        return False


def _send_sms(recipient: str, body: str) -> str:
    url = os.getenv("SMS_WEBHOOK_URL")
    if not url:
        raise LookupError("no SMS provider configured (set SMS_WEBHOOK_URL)")
    headers = {"Content-Type": "application/json"}
    if os.getenv("SMS_WEBHOOK_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('SMS_WEBHOOK_TOKEN')}"
    request = urllib.request.Request(
        url, data=json.dumps({"to": recipient, "message": body}).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 (configured URL)
        if response.status >= 300:
            raise RuntimeError(f"SMS gateway returned HTTP {response.status}")
    return "sms-webhook"


def deliver(notification: Notification, subject: str) -> None:
    """Try to send one notification; updates its status in place (caller commits)."""
    try:
        if notification.channel == "Email":
            provider = _send_email(notification.recipient, subject, notification.message)
        elif notification.channel in ("SMS", "WhatsApp"):
            provider = _send_sms(notification.recipient, notification.message)
        else:  # Phone: a person has to call
            raise LookupError("phone follow-ups are made by staff")
    except LookupError as reason:
        notification.status = "Queued"
        notification.provider = None
        notification.error = str(reason)
        return
    except Exception as exc:  # provider rejected / network error
        logger.warning("Delivery failed for %s: %s", notification.notification_id, type(exc).__name__)
        notification.status = "Failed"
        notification.error = f"{type(exc).__name__}: {exc}"[:500]
        return
    notification.status = "Sent"
    notification.provider = provider
    notification.error = None
    notification.sent_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Follow-up dispatch
# ---------------------------------------------------------------------


def _channel_and_recipient(trainee: Trainee) -> tuple[str, str]:
    if trainee.preferred_contact == "Email" and trainee.email:
        return "Email", trainee.email
    if trainee.preferred_contact == "Phone":
        return "Phone", trainee.phone
    return "SMS", trainee.phone


def _followup_message(trainee: Trainee, training: TrainingRecord, followup: FollowUp, link: str) -> str:
    first_name = trainee.full_name.split()[0]
    label = FOLLOWUP_LABELS.get(followup.followup_type, followup.followup_type)
    return (
        f"Hello {first_name}, this is your {label} check-in after the "
        f"{training.course_name} course. Please tell us how you are doing "
        f"(takes 1 minute): {link}"
    )


def dispatch_due_followups(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    resend_cutoff = datetime.now(timezone.utc) - timedelta(days=RESEND_AFTER_DAYS)
    summary = {
        "due_followups": 0,
        "sent": 0,
        "queued": 0,
        "failed": 0,
        "skipped_no_consent": 0,
        "skipped_recently_contacted": 0,
        "skipped_superseded": 0,
        "notification_ids": [],
    }

    due = (
        db.query(FollowUp)
        .filter(FollowUp.status == "Scheduled", FollowUp.scheduled_date <= today)
        .order_by(FollowUp.scheduled_date, FollowUp.id)
        .all()
    )
    summary["due_followups"] = len(due)

    # One message per training: only the most recent due check-in. Older
    # overdue ones are superseded (one answer describes the trainee's
    # current situation); staff can still complete or mark them missed.
    latest_per_training: dict = {}
    for followup in due:  # ordered by scheduled_date, so the last one wins
        latest_per_training[followup.training_record_pk_id] = followup
    summary["skipped_superseded"] = len(due) - len(latest_per_training)

    for followup in latest_per_training.values():
        trainee = db.query(Trainee).filter(Trainee.id == followup.trainee_pk_id).one()
        if not trainee.consent_given:
            summary["skipped_no_consent"] += 1
            continue
        recent = [
            n for n in db.query(Notification).filter(
                Notification.followup_pk_id == followup.id,
                Notification.purpose == "FOLLOWUP_REQUEST",
            )
            if n.created_at is None or _aware(n.created_at) >= resend_cutoff
        ]
        if recent:
            summary["skipped_recently_contacted"] += 1
            continue

        training = db.query(TrainingRecord).filter(TrainingRecord.id == followup.training_record_pk_id).one()
        channel, recipient = _channel_and_recipient(trainee)
        notification = Notification(
            notification_id=generate_notification_id(db),
            trainee_pk_id=trainee.id,
            followup_pk_id=followup.id,
            purpose="FOLLOWUP_REQUEST",
            channel=channel,
            recipient=recipient,
            message=_followup_message(trainee, training, followup, self_report_link(followup)),
        )
        deliver(notification, subject="Quick check-in about your training")
        db.add(notification)
        summary[notification.status.lower()] += 1
        summary["notification_ids"].append(notification.notification_id)

    db.commit()
    return summary


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
