from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.certificates import RecipientCreate


class JobCreateRequest(BaseModel):
    event_name: str = Field(..., description="Name of the event or course")
    issuer_name: str = Field(..., description="Name of the issuing authority")
    issue_date: date | None = Field(
        default=None, description="Date of issuance (defaults to today)"
    )
    recipients: list[RecipientCreate] = Field(
        ..., description="List of recipients to receive a certificate"
    )


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    event_name: str
    issuer_name: str
    issue_date: date
    total_count: int
    generated_count: int
    failed_count: int
    pending_count: int
    progress_percent: float
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
