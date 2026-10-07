from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.jobs import JobCreateRequest, JobCreateResponse
from app.services.job_service import create_job

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
    and returns HTTP 202 Accepted immediately.
    """
    job = create_job(
        db=db,
        request=job_request,
        max_recipients=settings.MAX_RECIPIENTS_PER_REQUEST,
    )

    # Note: Background worker processing will be dispatched here in milestone 14

    status_url = f"/api/v1/jobs/{job.id}"

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        status_url=status_url,
    )
