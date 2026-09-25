"""
Contact/location changes for a trainee, from staff (PATCH) or from the
trainee's own link. Every changed field is logged to
trainee_contact_history so the old value stays on record.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import Trainee, TraineeContactHistory

REQUIRED_FIELDS = ("phone", "district", "preferred_contact")


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
