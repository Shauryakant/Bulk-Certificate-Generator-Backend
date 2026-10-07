from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.errors import ConflictException, NotFoundException
from app.db.models import Certificate, CertificateStatus
from app.db.session import get_db

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get("/{certificate_id}/download")
def download_single_certificate(certificate_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """
    Streams the generated PDF certificate for a recipient.
    Returns HTTP 404 if not found, or HTTP 409 Conflict if pending/failed.
    """
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        raise NotFoundException(f"Certificate with id '{certificate_id}' not found.")

    if cert.status == CertificateStatus.PENDING.value:
        raise ConflictException("Certificate is still pending generation.")

    if cert.status == CertificateStatus.FAILED.value:
        raise ConflictException(
            f"Certificate generation failed: {cert.error_message or 'Unknown error'}"
        )

    if not cert.file_path or not Path(cert.file_path).exists():
        raise NotFoundException("Certificate PDF file not found on storage.")

    safe_name = "".join(
        c for c in cert.recipient_name if c.isalnum() or c in (" ", "-", "_")
    ).strip()
    filename = f"{safe_name}_{cert.id[:8]}.pdf" if safe_name else f"certificate_{cert.id}.pdf"

    return FileResponse(
        path=cert.file_path,
        media_type="application/pdf",
        filename=filename,
    )
