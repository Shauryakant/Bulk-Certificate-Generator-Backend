from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas.jobs import JobCreateRequest
from app.services.validation import (
    validate_and_normalise_recipients,
    validate_request_level,
)


def create_job(db: Session, request: JobCreateRequest, max_recipients: int = 5000) -> Job:
    """
    Validates request and recipient data, persists Job and Certificate records in the DB,
    pre-flagging invalid recipients as FAILED upfront.
    """
    # 1. Request-level validation (raises 422 if invalid)
    validate_request_level(
        event_name=request.event_name,
        issuer_name=request.issuer_name,
        recipients=request.recipients,
        max_recipients=max_recipients,
    )

    # 2. Recipient-level validation and normalisation
    validated_recipients = validate_and_normalise_recipients(request.recipients)

    issue_date = request.issue_date or date.today()
    total_count = len(validated_recipients)
    initial_failure_count = sum(1 for r in validated_recipients if not r.is_valid)

    # 3. Create Job entity
    job = Job(
        event_name=request.event_name.strip(),
        issuer_name=request.issuer_name.strip(),
        issue_date=issue_date,
        status=JobStatus.PENDING.value,
        total_count=total_count,
        success_count=0,
        failure_count=initial_failure_count,
    )
    db.add(job)
    db.flush()  # Populates job.id

    # 4. Create Certificate entities for all recipients
    certificate_objects = []
    for val in validated_recipients:
        if val.is_valid:
            cert = Certificate(
                job_id=job.id,
                recipient_name=val.sanitised_name,
                recipient_email=val.normalised_email,
                status=CertificateStatus.PENDING.value,
                file_path=None,
                error_message=None,
            )
        else:
            cert = Certificate(
                job_id=job.id,
                recipient_name=val.original_name or "Unknown",
                recipient_email=val.normalised_email or val.original_email,
                status=CertificateStatus.FAILED.value,
                file_path=None,
                error_message=val.error_message,
            )
        certificate_objects.append(cert)

    db.add_all(certificate_objects)
    db.commit()
    db.refresh(job)

    return job
