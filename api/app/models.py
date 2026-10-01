import uuid
from datetime import datetime, UTC
from typing import Optional, List
from sqlalchemy import String, ForeignKey, DateTime, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from enum import Enum as PyEnum

class Base(DeclarativeBase):
    pass

class UserRole(str, PyEnum):
    ORGANIZER = "Organizer"
    AGENCY_REVIEWER = "Agency Reviewer"
    CITY_ADMIN = "City Admin"

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    tenant: Mapped["Tenant"] = relationship()

class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

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
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_name: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[EventType]
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    expected_attendance: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(default=ApplicationStatus.DRAFT)
    submitter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    submitter: Mapped["User"] = relationship()
    tenant: Mapped["Tenant"] = relationship()
    review_tasks: Mapped[List["ReviewTask"]] = relationship(back_populates="application")

class ReviewTask(Base):
    __tablename__ = "review_tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"))
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
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(255))
    old_status: Mapped[Optional[str]] = mapped_column(String(255))
    new_status: Mapped[Optional[str]] = mapped_column(String(255))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))

    application: Mapped["Application"] = relationship()
    user: Mapped["User"] = relationship()
    tenant: Mapped["Tenant"] = relationship()
