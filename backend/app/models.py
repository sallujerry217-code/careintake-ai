from datetime import date, datetime, timezone
import uuid
from sqlalchemy import String, Date, DateTime, Text, Index, CheckConstraint, ForeignKey, JSON, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

def uid():
    return str(uuid.uuid4())

class Patient(Base):
    __tablename__ = 'patients'
    patient_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str] = mapped_column(String(20))
    phone_number: Mapped[str] = mapped_column(String(10), index=True)
    email: Mapped[str | None] = mapped_column(String(254))
    address_line_1: Mapped[str] = mapped_column(String(200))
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    zip_code: Mapped[str] = mapped_column(String(10))
    insurance_provider: Mapped[str | None] = mapped_column(String(150))
    insurance_member_id: Mapped[str | None] = mapped_column(String(100))
    preferred_language: Mapped[str] = mapped_column(String(60), default='English')
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    __table_args__ = (
        Index('uq_active_patient_phone', 'phone_number', unique=True, postgresql_where=text('deleted_at IS NULL'), sqlite_where=text('deleted_at IS NULL')),
        CheckConstraint("sex IN ('Male','Female','Other','Decline to Answer')"),
        CheckConstraint('length(first_name) BETWEEN 1 AND 50'),
        CheckConstraint('length(last_name) BETWEEN 1 AND 50'),
        CheckConstraint('length(phone_number) = 10'),
        CheckConstraint('length(city) BETWEEN 1 AND 100'),
        CheckConstraint('length(state) = 2'),
        CheckConstraint('length(zip_code) IN (5,10)'),
    )

class CallRecord(Base):
    __tablename__ = 'calls'
    call_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider_call_id: Mapped[str] = mapped_column(String(150), unique=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey('patients.patient_id'))
    caller_phone: Mapped[str | None] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default='in-progress')
    summary: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class VoiceDraft(Base):
    """Only stores a digest; demographics stay in the signed short-lived tool token."""
    __tablename__ = 'voice_drafts'
    call_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON)

class ToolReceipt(Base):
    __tablename__ = 'tool_receipts'
    key: Mapped[str] = mapped_column(String(310), primary_key=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
