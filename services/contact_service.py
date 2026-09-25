"""
Contact/location changes for a trainee, from staff (PATCH) or from the
trainee's own link. Every changed field is logged to
trainee_contact_history so the old value stays on record.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Notification, PhoneChangeRequest, Trainee, TraineeContactHistory
from services.auth import _secret_key

REQUIRED_FIELDS = ("phone", "district", "preferred_contact")
CODE_VALID_MINUTES = 15
MAX_CODE_ATTEMPTS = 5


def apply_contact_update(db: Session, trainee: Trainee, updates: dict, source: str) -> list[str]:
    """Apply `updates` (already exclude_unset) and log changes. Caller commits."""
    for field in REQUIRED_FIELDS:
        if field in updates and updates[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} cannot be empty",
            )
    if updates.get("email") is not None:
        updates["email"] = str(updates["email"])

    changed = []
    for field, value in updates.items():
        old = getattr(trainee, field)
        if old == value:
            continue
        db.add(
            TraineeContactHistory(
                trainee_pk_id=trainee.id,
                field=field,
                old_value=None if old is None else str(old),
                new_value=None if value is None else str(value),
                source=source,
            )
        )
        setattr(trainee, field, value)
        changed.append(field)
    return changed


# ---------------------------------------------------------------------
# Trainee self-service: a new phone number must be proved with a code
# ---------------------------------------------------------------------


def _new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _hash_code(trainee_pk_id: int, code: str) -> str:
    return hmac.new(_secret_key().encode(), f"{trainee_pk_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def self_update(db: Session, trainee: Trainee, updates: dict) -> dict:
    """
    Apply a trainee's own contact update. Everything except the phone number
    is applied at once; a new phone number is only stored as a pending
    request and a 6-digit code is sent to that new number.
    """
    from services import notification_service  # avoid an import cycle

    if not trainee.consent_given:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consent has been withdrawn.")

    if "phone" in updates and updates["phone"] is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="phone cannot be empty")
    new_phone = updates.pop("phone", None)
    if new_phone is not None and new_phone == trainee.phone:
        new_phone = None
    if new_phone is not None:
        if db.query(Trainee.id).filter(Trainee.phone == new_phone).first():
            raise _conflict("That phone number is already registered to someone else.")

    changed = apply_contact_update(db, trainee, updates, source="self")

    verification_sent = False
    if new_phone is not None:
        code = _new_code()
        db.query(PhoneChangeRequest).filter(PhoneChangeRequest.trainee_pk_id == trainee.id).delete()
        db.add(
            PhoneChangeRequest(
                trainee_pk_id=trainee.id,
                new_phone=new_phone,
                code_hash=_hash_code(trainee.id, code),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=CODE_VALID_MINUTES),
            )
        )
        notification = Notification(
            notification_id=notification_service.generate_notification_id(db),
            trainee_pk_id=trainee.id,
            purpose="PHONE_VERIFICATION",
            channel="SMS",
            recipient=new_phone,
            message=f"Your verification code is {code}. It is valid for {CODE_VALID_MINUTES} minutes.",
        )
        notification_service.deliver(notification, subject="Your verification code")
        db.add(notification)
        verification_sent = True

    _commit_or_conflict(db)
    return {"updated": changed, "phone_verification_sent": verification_sent}


def verify_phone_change(db: Session, trainee: Trainee, code: str) -> dict:
    request = db.query(PhoneChangeRequest).filter(PhoneChangeRequest.trainee_pk_id == trainee.id).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone number change is waiting for a code.")
    if _aware(request.expires_at) < datetime.now(timezone.utc):
        db.delete(request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="The code has expired. Please request the change again.")
    if request.attempts >= MAX_CODE_ATTEMPTS:
        db.delete(request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many wrong codes. Please request the change again.")
    if not hmac.compare_digest(request.code_hash, _hash_code(trainee.id, code)):
        request.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code is not correct.")

    new_phone = request.new_phone
    db.delete(request)
    apply_contact_update(db, trainee, {"phone": new_phone}, source="self")
    _commit_or_conflict(db)
    return {"updated": ["phone"]}


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _conflict("That phone number or email is already registered to someone else.")
