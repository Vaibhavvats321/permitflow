import uuid
from datetime import datetime, UTC
from typing import Optional, List
from sqlalchemy import String, ForeignKey, DateTime, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from enum import Enum as PyEnum

class Base(DeclarativeBase):
    pass

class UserRole(str, PyEnum):
    ORGANIZER = "Organizer"
    AGENCY_REVIEWER = "Agency Reviewer"
    CITY_ADMIN = "City Admin"

    @classmethod
    def parse(cls, value: object) -> "UserRole":
        """
        Coerce a value read from the database into a UserRole.

        The Postgres enum stores member NAMES ("ORGANIZER"), while the Python
        enum's API-visible values are the human-readable strings ("Organizer").
        SQLAlchemy bridges that gap for ORM queries, but a raw text() select
        through get_user_by_email does not, so both forms are accepted here.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
            try:
                return cls[value.upper()]
            except KeyError:
                pass
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")

class ApplicationStatus(str, PyEnum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CHANGES_REQUESTED = "Changes Requested"

class EventType(str, PyEnum):
    MARATHON = "Marathon"
    CONCERT = "Concert"
    STREET_FAIR = "Street Fair"
    OTHER = "Other"

class ReviewStatus(str, PyEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    CHANGES_REQUESTED = "Changes Requested"

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole]
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    agency_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("agencies.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    tenant: Mapped["Tenant"] = relationship()
    agency: Mapped[Optional["Agency"]] = relationship()

class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    # Attendance above this value makes the agency a required reviewer.
    # NULL means the agency is only ever required by the routing matrix.
    attendance_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    tenant: Mapped["Tenant"] = relationship()

from sqlalchemy import UniqueConstraint

class EventTypeAgencyRule(Base):
    __tablename__ = "event_type_agency_rules"
    __table_args__ = (
        UniqueConstraint('tenant_id', 'event_type', 'agency_id', name='uq_event_type_agency_rule'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_type: Mapped[EventType]
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    agency: Mapped["Agency"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index('ix_applications_tenant_id', 'tenant_id'),
        Index('ix_applications_tenant_id_status', 'tenant_id', 'status'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_name: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[EventType]
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    expected_attendance: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(default=ApplicationStatus.DRAFT)
    submitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    submitter: Mapped["User"] = relationship()
    tenant: Mapped["Tenant"] = relationship()
    review_tasks: Mapped[List["ReviewTask"]] = relationship(back_populates="application")

class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        Index('ix_review_tasks_agency_id_status', 'agency_id', 'status'),
        # One review task per agency per application. Enforced in the schema so
        # a retried submit cannot create a second vote for the same agency.
        UniqueConstraint('application_id', 'agency_id', name='uq_review_tasks_application_agency'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    agency_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencies.id"))
    status: Mapped[ReviewStatus] = mapped_column(default=ReviewStatus.PENDING)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    application: Mapped["Application"] = relationship(back_populates="review_tasks")
    agency: Mapped["Agency"] = relationship()
    tenant: Mapped["Tenant"] = relationship()

class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index('ix_audit_events_application_id_created_at', 'application_id', 'created_at'),
        # Supports "what has this agency decided" without scanning a tenant's
        # whole timeline.
        Index('ix_audit_events_agency_id_created_at', 'agency_id', 'created_at'),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    # Which agency acted, for reviewer decisions. Nullable because the timeline
    # also records events with no agency behind them (submission, a future
    # resubmission), and because rows written before this column existed have no
    # value to backfill.
    # Named to match the migration: an unnamed FK here makes `alembic check`
    # report the same constraint as removed-and-re-added forever.
    agency_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("agencies.id", name="fk_audit_events_agency_id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(255))
    old_status: Mapped[Optional[str]] = mapped_column(String(255))
    new_status: Mapped[Optional[str]] = mapped_column(String(255))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    application: Mapped["Application"] = relationship()
    user: Mapped["User"] = relationship()
    tenant: Mapped["Tenant"] = relationship()
