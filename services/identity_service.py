"""
Cross-programme identity helpers: linking external IDs and spotting
probable duplicate registrations.

Duplicate detection is deliberately conservative and explainable: two
trainee records are "possible duplicates" when they have the same
normalised full name and the same date of birth. They are only flagged,
never merged automatically — an admin decides.
"""

from collections import defaultdict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import Trainee, TraineeExternalId


def normalise_name(name: str) -> str:
    return " ".join(name.lower().replace(".", " ").split())


def find_possible_duplicates(db: Session, full_name: str, dob, exclude_pk: int | None = None) -> list[str]:
    """trainee_ids of other trainees with the same normalised name and DOB."""
    target = normalise_name(full_name)
    candidates = db.query(Trainee).filter(Trainee.dob == dob).all()
    return sorted(
        t.trainee_id
        for t in candidates
        if t.id != exclude_pk and normalise_name(t.full_name) == target
    )


def duplicate_groups(db: Session) -> list[dict]:
    groups = defaultdict(list)
    for t in db.query(Trainee).all():
        groups[(normalise_name(t.full_name), t.dob)].append(t)
    result = []
    for (_name, dob), members in groups.items():
        if len(members) > 1:
            result.append(
                {
                    "full_name": members[0].full_name,
                    "dob": dob.isoformat(),
                    "trainee_ids": sorted(m.trainee_id for m in members),
                }
            )
    return sorted(result, key=lambda g: g["trainee_ids"][0])


def existing_owner(db: Session, id_type: str, id_value: str) -> Trainee | None:
    """The trainee an external ID is already linked to, if any (case-insensitive type)."""
    row = (
        db.query(TraineeExternalId)
        .filter(TraineeExternalId.id_value == id_value)
        .all()
    )
    for link in row:
        if link.id_type.lower() == id_type.lower():
            return db.query(Trainee).filter(Trainee.id == link.trainee_pk_id).first()
    return None


def link_external_id(db: Session, trainee: Trainee, id_type: str, id_value: str, source_programme=None):
    """
    Attach an external ID to a trainee (caller commits). Re-linking the
    same ID to the same trainee is a no-op; linking it to a different
    trainee is a 409 naming the existing trainee — that is the
    cross-programme duplicate check.
    """
    owner = existing_owner(db, id_type, id_value)
    if owner is not None:
        if owner.id == trainee.id:
            return None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{id_type} {id_value} is already linked to trainee {owner.trainee_id}",
        )
    link = TraineeExternalId(
        trainee_pk_id=trainee.id,
        id_type=id_type,
        id_value=id_value,
        source_programme=source_programme,
    )
    db.add(link)
    return link
