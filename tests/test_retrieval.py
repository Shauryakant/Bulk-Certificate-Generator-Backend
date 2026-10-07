import io
import zipfile
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, Job, JobStatus


def test_health_check_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_download_single_certificate_flow(client: TestClient, db_session: Session):
    # 1. Non-existent cert
    res1 = client.get("/api/v1/certificates/non-existent-uuid/download")
    assert res1.status_code == 404
    assert res1.json()["error"]["code"] == "NOT_FOUND"

    # 2. Pending cert (create manually in DB)
    job = Job(
        event_name="Test Event",
        issuer_name="Test Issuer",
        issue_date=date.today(),
        status=JobStatus.PENDING.value,
        total_count=1,
    )
    db_session.add(job)
    db_session.flush()

    pending_cert = Certificate(
        job_id=job.id,
        recipient_name="Pending Recipient",
        recipient_email="pending@example.com",
        status=CertificateStatus.PENDING.value,
    )
    failed_cert = Certificate(
        job_id=job.id,
        recipient_name="Failed Recipient",
        recipient_email="failed@example.com",
        status=CertificateStatus.FAILED.value,
        error_message="Font render error",
    )
    db_session.add_all([pending_cert, failed_cert])
    db_session.commit()

    # Download pending cert -> 409
    res_pending = client.get(f"/api/v1/certificates/{pending_cert.id}/download")
    assert res_pending.status_code == 409
    assert res_pending.json()["error"]["code"] == "CONFLICT"

    # Download failed cert -> 409
    res_failed = client.get(f"/api/v1/certificates/{failed_cert.id}/download")
    assert res_failed.status_code == 409
    assert "generation failed" in res_failed.json()["error"]["message"]

    # 3. Generated cert download via API workflow
    payload = {
        "event_name": "PDF Download Test",
        "issuer_name": "API Issuer",
        "recipients": [{"name": "Charlie Brown", "email": "charlie@example.com"}],
    }
    submit_res = client.post("/api/v1/jobs", json=payload)
    job_id = submit_res.json()["job_id"]

    certs_res = client.get(f"/api/v1/jobs/{job_id}/certificates")
    cert_id = certs_res.json()["items"][0]["id"]

    download_res = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert download_res.status_code == 200
    assert download_res.headers["content-type"] == "application/pdf"
    assert download_res.content.startswith(b"%PDF")


def test_download_job_zip_flow(client: TestClient, db_session: Session):
    # 1. Non-existent job
    res1 = client.get("/api/v1/jobs/non-existent-job-uuid/download")
    assert res1.status_code == 404

    # 2. Running job -> 409
    running_job = Job(
        event_name="Running Job",
        issuer_name="Issuer",
        issue_date=date.today(),
        status=JobStatus.PROCESSING.value,
    )
    db_session.add(running_job)
    db_session.commit()

    res_running = client.get(f"/api/v1/jobs/{running_job.id}/download")
    assert res_running.status_code == 409

    # 3. Successful job ZIP download containing generated PDFs
    payload = {
        "event_name": "ZIP Download Test Event",
        "issuer_name": "ZIP Issuer",
        "recipients": [
            {"name": "Alice In ZIP", "email": "alice_zip@example.com"},
            {"name": "Bob In ZIP", "email": "bob_zip@example.com"},
        ],
    }

    submit_res = client.post("/api/v1/jobs", json=payload)
    job_id = submit_res.json()["job_id"]

    zip_res = client.get(f"/api/v1/jobs/{job_id}/download")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"

    # Verify ZIP contents using zipfile
    with zipfile.ZipFile(io.BytesIO(zip_res.content)) as z:
        filenames = z.namelist()
        assert len(filenames) == 2
        for fn in filenames:
            assert fn.endswith(".pdf")
            pdf_data = z.read(fn)
            assert pdf_data.startswith(b"%PDF")
