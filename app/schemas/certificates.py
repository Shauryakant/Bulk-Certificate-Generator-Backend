from pydantic import BaseModel, ConfigDict, Field


class RecipientCreate(BaseModel):
    name: str = Field(..., description="Recipient's full name")
    email: str = Field(..., description="Recipient's email address")

    model_config = ConfigDict(extra="allow")


class CertificateResponse(BaseModel):
    id: str
    recipient_name: str
    recipient_email: str
    status: str
    error_message: str | None = None
    download_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedCertificatesResponse(BaseModel):
    items: list[CertificateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
