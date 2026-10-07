import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus(StrEnum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True, default=JobStatus.PENDING.value
    )
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    certificates: Mapped[list["Certificate"]] = relationship(
        "Certificate", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_jobs_status", "status"),)


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True, default=CertificateStatus.PENDING.value
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["Job"] = relationship("Job", back_populates="certificates")

    __table_args__ = (
        Index("idx_certificates_job_id", "job_id"),
        Index("idx_certificates_status", "status"),
        Index("idx_certificates_job_status", "job_id", "status"),
    )
