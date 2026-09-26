"""
Cross-programme identity routes (admin only).

POST /api/trainees/{trainee_id}/external-ids   -> link a programme / Skill India ID
GET  /api/trainees/{trainee_id}/external-ids   -> list a trainee's linked IDs
GET  /api/identity/lookup                      -> find the trainee for an external ID
GET  /api/identity/possible-duplicates         -> same name + DOB registered more than once
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import TraineeExternalId
from routes._shared import get_trainee_or_404
from schemas.identity import (
    ExternalIdCreate,
    ExternalIdLookupResponse,
    ExternalIdResponse,
    PossibleDuplicatesResponse,
)
from services import identity_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Identity (cross-programme)"])


@router.post(
    "/api/trainees/{trainee_id}/external-ids",
    response_model=ExternalIdResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link an ID from another programme/system to this trainee",
)
def add_external_id(trainee_id: str, payload: ExternalIdCreate, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)
    identity_service.link_external_id(
        db, trainee, payload.id_type, payload.id_value, payload.source_programme
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.id_type} {payload.id_value} is already linked to another trainee",
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while linking an external ID")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save the record right now. Please try again.",
        )
    return ExternalIdResponse(trainee_id=trainee.trainee_id, **payload.model_dump())


@router.get(
    "/api/trainees/{trainee_id}/external-ids",
    response_model=list[ExternalIdResponse],
    summary="List the external IDs linked to a trainee",
)
def list_external_ids(trainee_id: str, db: Session = Depends(get_db)):
    trainee = get_trainee_or_404(trainee_id, db)
    links = (
        db.query(TraineeExternalId)
        .filter(TraineeExternalId.trainee_pk_id == trainee.id)
        .order_by(TraineeExternalId.id)
        .all()
    )
    return [
        ExternalIdResponse(
            trainee_id=trainee.trainee_id,
            id_type=link.id_type,
            id_value=link.id_value,
            source_programme=link.source_programme,
        )
        for link in links
    ]


@router.get(
    "/api/identity/lookup",
    response_model=ExternalIdLookupResponse,
    summary="Find the stable trainee_id for an ID used by another programme",
)
def lookup_external_id(
    id_type: str = Query(..., min_length=2),
    id_value: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    try:
        clean = ExternalIdCreate(id_type=id_type, id_value=id_value)
    except ValidationError as exc:
        # e.g. an Aadhaar-like value: a client error, not a 500
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(err["msg"].removeprefix("Value error, ") for err in exc.errors()),
        )
    owner = identity_service.existing_owner(db, clean.id_type, clean.id_value)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No trainee is linked to {clean.id_type} {clean.id_value}",
        )
    return ExternalIdLookupResponse(
        trainee_id=owner.trainee_id, id_type=clean.id_type, id_value=clean.id_value
    )


@router.get(
    "/api/identity/possible-duplicates",
    response_model=PossibleDuplicatesResponse,
    summary="Trainee records sharing the same name and date of birth (flagged, never auto-merged)",
)
def possible_duplicates(db: Session = Depends(get_db)):
    groups = identity_service.duplicate_groups(db)
    return PossibleDuplicatesResponse(
        groups=groups, trainees_involved=sum(len(g["trainee_ids"]) for g in groups)
    )
