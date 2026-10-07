import io
import math
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ConflictException, NotFoundException
from app.db.models import Certificate, CertificateStatus, Job, JobStatus
from app.db.session import get_db
from app.schemas.certificates import CertificateResponse, PaginatedCertificatesResponse
from app.schemas.jobs import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.job_service import create_job
from app.services.worker import dispatch_job

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(
    job_request: JobCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JobCreateResponse:
    """
    Submits a bulk certificate generation job.
    Validates request and recipient data, stores job and recipients in DB,
    and returns HTTP 202 Accepted immediately while background worker processes certificates.
    """
    job = create_job(
        db=db,
        request=job_request,
        max_recipients=settings.MAX_RECIPIENTS_PER_REQUEST,
    )

    # Dispatch to background thread pool (or synchronous execution in test mode)
    dispatch_job(job.id)

    status_url = f"/api/v1/jobs/{job.id}"

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        status_url=status_url,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    """Retrieves current job status, counts, progress percentage, and timestamps."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundException(f"Job with id '{job_id}' not found.")

    processed_count = job.success_count + job.failure_count
    pending_count = max(0, job.total_count - processed_count)
    progress_percent = (
        round((processed_count / job.total_count) * 100.0, 2) if job.total_count > 0 else 0.0
    )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        event_name=job.event_name,
        issuer_name=job.issuer_name,
        issue_date=job.issue_date,
        total_count=job.total_count,
        generated_count=job.success_count,
        failed_count=job.failure_count,
        pending_count=pending_count,
        progress_percent=progress_percent,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/certificates", response_model=PaginatedCertificatesResponse)
def list_job_certificates(
    job_id: str,
    status_filter: str | None = Query(
        None, alias="status", description="Filter by status (PENDING, GENERATED, FAILED)"
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedCertificatesResponse:
    """Lists certificates for a job with optional status filtering and pagination."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundException(f"Job with id '{job_id}' not found.")

    query = db.query(Certificate).filter(Certificate.job_id == job_id)

    if status_filter:
        query = query.filter(Certificate.status == status_filter.upper())

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    offset = (page - 1) * page_size
    certs = query.order_by(Certificate.created_at.asc()).offset(offset).limit(page_size).all()

    items = [
        CertificateResponse(
            id=c.id,
            recipient_name=c.recipient_name,
            recipient_email=c.recipient_email,
            status=c.status,
            error_message=c.error_message,
            download_url=(
                f"/api/v1/certificates/{c.id}/download"
                if c.status == CertificateStatus.GENERATED.value
                else None
            ),
        )
        for c in certs
    ]

    return PaginatedCertificatesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{job_id}/download")
def download_job_zip(job_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """
    Streams a ZIP archive containing all successfully generated PDF certificates for a job.
    Returns HTTP 409 Conflict if the job is still running or has no generated certificates.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFoundException(f"Job with id '{job_id}' not found.")

    if job.status in (JobStatus.PENDING.value, JobStatus.PROCESSING.value):
        raise ConflictException(
            "Job is still running. Cannot download ZIP until processing completes."
        )

    generated_certs = (
        db.query(Certificate)
        .filter(
            Certificate.job_id == job_id,
            Certificate.status == CertificateStatus.GENERATED.value,
        )
        .all()
    )

    if not generated_certs:
        raise ConflictException("No generated certificates available for this job.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for cert in generated_certs:
            if cert.file_path and Path(cert.file_path).exists():
                safe_name = "".join(
                    c for c in cert.recipient_name if c.isalnum() or c in (" ", "-", "_")
                ).strip()
                filename = (
                    f"{safe_name}_{cert.id[:8]}.pdf" if safe_name else f"certificate_{cert.id}.pdf"
                )
                zip_file.write(cert.file_path, arcname=filename)

    zip_buffer.seek(0)
    zip_filename = f"job_{job_id[:8]}_certificates.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
    )
