"""
SQLAlchemy models.

Phase 1: trainees
Phase 2: training_records (linked to trainees, many records per trainee)
Phase 3: outcomes + employment_records, self_employment_records,
         apprenticeship_records, non_placement_records, followups
Phase 4: employer_verifications, wage_history, employment_status_history
         (all extend employment_records; Phase 1-3 tables are untouched)

Phase 8: trainee_external_ids (cross-programme identity), notifications
         (automated follow-up / verification message outbox)
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from database.connection import Base


class Trainee(Base):
    __tablename__ = "trainees"

    # Internal database row id (never shown to API users)
    id = Column(Integer, primary_key=True, index=True)

    # Permanent public identifier, e.g. TRN000001.
    # This is the stable identity of the trainee — phone numbers may change,
    # this never does.
    trainee_id = Column(String(20), unique=True, nullable=False, index=True)

    # ---- Personal information ----
    full_name = Column(String(150), nullable=False)
    dob = Column(Date, nullable=False)
    gender = Column(String(20), nullable=False)
    district = Column(String(100), nullable=False, index=True)
    current_location = Column(String(150), nullable=True)

    # ---- Contact information ----
    phone = Column(String(15), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    preferred_contact = Column(String(10), nullable=False)

    # ---- Consent ----
    consent_given = Column(Boolean, nullable=False, default=False)
    consent_date = Column(DateTime(timezone=True), nullable=True)

    # ---- Record metadata ----
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # A trainee can have many training records (Python Dev, AWS Fundamentals, ...)
    training_records = relationship(
        "TrainingRecord",
        back_populates="trainee",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # A trainee can have multiple outcomes — one per completed training
    outcomes = relationship(
        "Outcome",
        back_populates="trainee",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        # Deliberately does not include name, phone or email (privacy).
        return f"<Trainee {self.trainee_id}>"


class TrainingRecord(Base):
    """
    Phase 2 — one row per (trainee, course/program) they have taken.

    Linked to trainees via trainee_pk_id (the internal integer id), NOT via
    the public trainee_id string, so the foreign key stays a normal indexed
    integer relationship. The API still speaks in TRN000001 / TRC000001
    terms — see schemas/training_record.py.
    """

    __tablename__ = "training_records"

    id = Column(Integer, primary_key=True, index=True)

    # Permanent public identifier, e.g. TRC000001
    record_id = Column(String(20), unique=True, nullable=False, index=True)

    # Link back to the trainee (internal FK, ON DELETE CASCADE)
    trainee_pk_id = Column(
        Integer,
        ForeignKey("trainees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---- Programme / course / provider ----
    # Scheme/programme the course was delivered under (e.g. PMKVY 4.0).
    # Nullable: added in Phase 8 via ALTER TABLE ... ADD COLUMN IF NOT
    # EXISTS, so rows created earlier simply have no programme recorded.
    program_name = Column(String(200), nullable=True, index=True)
    course_name = Column(String(200), nullable=False)
    provider_name = Column(String(200), nullable=False)

    # ---- Timeline ----
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    # Enrolled | Ongoing | Completed | Dropped
    status = Column(String(20), nullable=False, default="Enrolled")

    # ---- Assessment ----
    attendance_percentage = Column(Numeric(5, 2), nullable=True)
    assessment_score = Column(Numeric(5, 2), nullable=True)
    # Pending | Passed | Failed (nullable, Phase 8 additive column)
    assessment_status = Column(String(10), nullable=True)

    # ---- Certification ----
    certification_issued = Column(Boolean, nullable=False, default=False)
    certification_id = Column(String(50), nullable=True)

    # ---- Record metadata ----
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trainee = relationship("Trainee", back_populates="training_records")

    def __repr__(self) -> str:
        return f"<TrainingRecord {self.record_id} ({self.course_name})>"


class Outcome(Base):
    """
    Phase 3 — records WHAT happened to a trainee after ONE specific
    training (job / self-employed / apprenticeship / unemployed / further
    education / not reachable).

    Deliberately thin: this table only identifies the outcome. Company
    name, salary, business income, stipend etc. live in their own detail
    tables below, each pointing back here via outcome_pk_id.
    """

    __tablename__ = "outcomes"

    id = Column(Integer, primary_key=True, index=True)

    # Permanent public identifier, e.g. OUT000001
    outcome_id = Column(String(20), unique=True, nullable=False, index=True)

    # Links (internal FKs — the API speaks in TRN0000xx / TRC0000xx / OUT0000xx)
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_record_pk_id = Column(
        Integer,
        ForeignKey("training_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Employed | Self-employed | Apprenticeship | Unemployed |
    # Further Education | Not Reachable
    outcome_type = Column(String(30), nullable=False)

    status_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trainee = relationship("Trainee", back_populates="outcomes")
    training_record = relationship("TrainingRecord")

    def __repr__(self) -> str:
        return f"<Outcome {self.outcome_id} ({self.outcome_type})>"


class EmploymentRecord(Base):
    """Phase 3 — detail for an outcome where outcome_type == 'Employed'."""

    __tablename__ = "employment_records"

    id = Column(Integer, primary_key=True, index=True)
    employment_id = Column(String(20), unique=True, nullable=False, index=True)

    outcome_pk_id = Column(
        Integer, ForeignKey("outcomes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    company_name = Column(String(200), nullable=False)
    job_role = Column(String(150), nullable=False)
    joining_date = Column(Date, nullable=False)
    salary = Column(Numeric(12, 2), nullable=True)
    employment_status = Column(String(20), nullable=False, default="Active")
    job_location = Column(String(150), nullable=True)
    job_relevance = Column(String(20), nullable=True)  # Relevant | Not Relevant | Partially Relevant

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<EmploymentRecord {self.employment_id}>"


class SelfEmploymentRecord(Base):
    """Phase 3 — detail for an outcome where outcome_type == 'Self-employed'."""

    __tablename__ = "self_employment_records"

    id = Column(Integer, primary_key=True, index=True)
    self_employment_id = Column(String(20), unique=True, nullable=False, index=True)

    outcome_pk_id = Column(
        Integer, ForeignKey("outcomes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    business_name = Column(String(200), nullable=False)
    business_type = Column(String(150), nullable=False)
    start_date = Column(Date, nullable=False)
    monthly_income = Column(Numeric(12, 2), nullable=True)
    location = Column(String(150), nullable=True)
    number_of_workers = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<SelfEmploymentRecord {self.self_employment_id}>"


class ApprenticeshipRecord(Base):
    """Phase 3 — detail for an outcome where outcome_type == 'Apprenticeship'."""

    __tablename__ = "apprenticeship_records"

    id = Column(Integer, primary_key=True, index=True)
    apprenticeship_id = Column(String(20), unique=True, nullable=False, index=True)

    outcome_pk_id = Column(
        Integer, ForeignKey("outcomes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    organization_name = Column(String(200), nullable=False)
    role = Column(String(150), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    monthly_stipend = Column(Numeric(12, 2), nullable=True)
    location = Column(String(150), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ApprenticeshipRecord {self.apprenticeship_id}>"


class NonPlacementRecord(Base):
    """
    Phase 3 — detail for an outcome where outcome_type == 'Unemployed'.

    Structured reason first, per the spec — no ML classification yet.
    """

    __tablename__ = "non_placement_records"

    id = Column(Integer, primary_key=True, index=True)
    non_placement_id = Column(String(20), unique=True, nullable=False, index=True)

    outcome_pk_id = Column(
        Integer, ForeignKey("outcomes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Skill Gap | Lack of Jobs | Low Salary | Location Problem |
    # Relocation Issue | Personal/Family Reason | Further Education | Other
    reason_category = Column(String(40), nullable=False)
    reason_details = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<NonPlacementRecord {self.non_placement_id}>"


class FollowUp(Base):
    """
    Phase 3 — longitudinal check-ins on a trainee after a specific
    training (30-day / 90-day / 6-month / 12-month). outcome_pk_id is
    filled in once the follow-up call actually establishes an outcome;
    it stays NULL for a follow-up that's only scheduled so far.
    """

    __tablename__ = "followups"

    id = Column(Integer, primary_key=True, index=True)
    followup_id = Column(String(20), unique=True, nullable=False, index=True)

    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_record_pk_id = Column(
        Integer,
        ForeignKey("training_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outcome_pk_id = Column(
        Integer, ForeignKey("outcomes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 30_DAY | 90_DAY | 6_MONTH | 12_MONTH
    followup_type = Column(String(20), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    completed_date = Column(Date, nullable=True)

    # Scheduled | Completed | Missed | Not Reachable
    status = Column(String(20), nullable=False, default="Scheduled")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<FollowUp {self.followup_id} ({self.followup_type})>"


class EmployerVerification(Base):
    """
    Phase 4 — verification of an employment_records row.

    Supports multiple verification attempts per employment (history is
    kept, never overwritten) — e.g. a first attempt that comes back
    'Unable to Verify' followed later by a successful 'Employer Contact'
    verification. The current/authoritative verification for an
    employment is simply the most recent row (highest id / created_at)
    for that employment_pk_id; callers needing "the" verification for an
    employment (see routes/employer_verifications.py) fetch the latest
    one rather than assuming there is only ever one.
    """

    __tablename__ = "employer_verifications"

    id = Column(Integer, primary_key=True, index=True)
    verification_id = Column(String(20), unique=True, nullable=False, index=True)

    employment_pk_id = Column(
        Integer, ForeignKey("employment_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    employer_name = Column(String(200), nullable=False)
    employer_contact = Column(String(255), nullable=True)

    # Pending | Verified | Rejected | Unable to Verify
    verification_status = Column(String(20), nullable=False, default="Pending")

    # Employer Portal | Employer Contact | Document | Trainee Confirmation | Admin Verification
    verification_method = Column(String(30), nullable=False)

    verified_date = Column(Date, nullable=True)
    verified_by = Column(String(150), nullable=True)
    verification_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<EmployerVerification {self.verification_id} ({self.verification_status})>"


class WageHistory(Base):
    """
    Phase 4 — one row per known salary point for an employment_records row.

    The original salary in employment_records.salary is never overwritten;
    every new figure (raise, correction, employer-confirmed update) is a
    new row here instead, so full wage progression stays reconstructable.
    """

    __tablename__ = "wage_history"

    id = Column(Integer, primary_key=True, index=True)
    wage_record_id = Column(String(20), unique=True, nullable=False, index=True)

    employment_pk_id = Column(
        Integer, ForeignKey("employment_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    salary = Column(Numeric(12, 2), nullable=False)
    # Monthly | Annual
    salary_period = Column(String(10), nullable=False)
    effective_date = Column(Date, nullable=False)

    # Trainee | Employer | Document | Admin
    source = Column(String(20), nullable=False)
    # Unverified | Verified
    verification_status = Column(String(20), nullable=False, default="Unverified")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<WageHistory {self.wage_record_id} ({self.salary} {self.salary_period})>"


class EmploymentStatusHistory(Base):
    """
    Phase 4 — one row per employment-status change for an employment_records
    row. Old rows are never deleted, so this is the retention timeline
    (Active -> Active -> Left Job, etc).
    """

    __tablename__ = "employment_status_history"

    id = Column(Integer, primary_key=True, index=True)
    status_record_id = Column(String(20), unique=True, nullable=False, index=True)

    employment_pk_id = Column(
        Integer, ForeignKey("employment_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Active | Left Job | Terminated | On Leave | Unknown
    employment_status = Column(String(20), nullable=False)
    status_date = Column(Date, nullable=False)
    reason = Column(String(150), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<EmploymentStatusHistory {self.status_record_id} ({self.employment_status})>"


class FollowUpAttempt(Base):
    """
    Phase 5 — one contact attempt made while carrying out a follow-up.

    A single follow-up (e.g. the 30_DAY check-in) can take several tries
    to reach the trainee, so every attempt is its own row and none are
    ever overwritten — see routes/followup_tracking.py.
    """

    __tablename__ = "followup_attempts"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(String(20), unique=True, nullable=False, index=True)

    followup_pk_id = Column(
        Integer, ForeignKey("followups.id", ondelete="CASCADE"), nullable=False, index=True
    )

    attempt_date = Column(Date, nullable=False)
    # Phone | SMS | WhatsApp | Email | In Person | Other
    contact_method = Column(String(20), nullable=False)
    # Successful | No Response | Busy | Invalid Contact | Not Reachable | Other
    attempt_status = Column(String(20), nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    followup = relationship("FollowUp", backref="attempts")

    def __repr__(self) -> str:
        return f"<FollowUpAttempt {self.attempt_id} ({self.attempt_status})>"


class FollowUpOutcomeUpdate(Base):
    """
    Phase 5 — the trainee's current situation as captured during one
    follow-up call: current employment status, how relevant the training
    turned out to be, and whether a skill gap or further training need
    was identified.

    This is separate from Phase 3/4's Outcome / EmploymentRecord /
    WageHistory tables on purpose: it is a lightweight, manually-collected
    snapshot for analytics, not a new employment/wage record. If the
    follow-up reveals a real change (new job, new salary), that still
    goes through the existing Phase 3/4 endpoints.
    """

    __tablename__ = "followup_outcome_updates"

    id = Column(Integer, primary_key=True, index=True)
    update_id = Column(String(20), unique=True, nullable=False, index=True)

    followup_pk_id = Column(
        Integer, ForeignKey("followups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Employed | Self-employed | Apprenticeship | Unemployed |
    # Further Education | Not Reachable
    employment_status = Column(String(30), nullable=False)

    # 1 (not relevant) .. 5 (highly relevant)
    training_relevance = Column(Integer, nullable=True)
    skill_gap = Column(Boolean, nullable=True)
    additional_training_needed = Column(Boolean, nullable=True)

    # Only meaningful when employment_status == 'Unemployed'
    unemployment_reason_category = Column(String(40), nullable=True)
    unemployment_reason_details = Column(Text, nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    followup = relationship("FollowUp", backref="outcome_updates")

    def __repr__(self) -> str:
        return f"<FollowUpOutcomeUpdate {self.update_id} ({self.employment_status})>"


class TraineeExternalId(Base):
    """
    Phase 8 — identifiers the same trainee carries in OTHER programmes /
    systems (e.g. Skill India Digital ID, a PMKVY candidate ID, a state
    scheme registration number).

    The internal trainee_id stays the one stable identity; these rows
    let records arriving from different programmes be linked to it, and
    the (id_type, id_value) uniqueness stops the same external ID being
    attached to two different trainees (a duplicate registration).
    Aadhaar numbers are deliberately NOT accepted here (see schema).
    """

    __tablename__ = "trainee_external_ids"
    __table_args__ = (UniqueConstraint("id_type", "id_value", name="uq_external_id_type_value"),)

    id = Column(Integer, primary_key=True, index=True)
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    id_type = Column(String(60), nullable=False)
    id_value = Column(String(100), nullable=False)
    source_programme = Column(String(200), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<TraineeExternalId {self.id_type}>"


class Notification(Base):
    """
    Phase 8 — outbound follow-up / verification messages (the outbox).

    Every automated message is recorded here whether or not a delivery
    provider is configured: status is Sent when a provider accepted it,
    Queued when it is waiting for a provider or a staff member (e.g. a
    phone call), Failed when the provider rejected it.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(String(20), unique=True, nullable=False, index=True)

    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    followup_pk_id = Column(
        Integer, ForeignKey("followups.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # FOLLOWUP_REQUEST | EMPLOYER_VERIFICATION
    purpose = Column(String(30), nullable=False)
    # SMS | Email | Phone | WhatsApp
    channel = Column(String(20), nullable=False)
    recipient = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Queued | Sent | Failed
    status = Column(String(10), nullable=False, default="Queued")
    provider = Column(String(30), nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Notification {self.notification_id} ({self.channel} {self.status})>"


class TraineeContactHistory(Base):
    """
    One row per changed contact field, so an old phone number or district
    is never lost when a trainee moves or changes number. `source` is
    'self' (trainee used their link) or 'admin' (staff edited it).
    """

    __tablename__ = "trainee_contact_history"

    id = Column(Integer, primary_key=True, index=True)
    trainee_pk_id = Column(
        Integer, ForeignKey("trainees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field = Column(String(30), nullable=False)
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    source = Column(String(10), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<TraineeContactHistory {self.field} ({self.source})>"
