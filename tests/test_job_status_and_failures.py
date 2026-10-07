import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import CertificateStatus, JobStatus
from app.services.generator import CertificateGenerator


def test_get_job_status_not_found(client: TestClient):
    response = client.get("/api/v1/jobs/non-existent-uuid-999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_job_status_and_progress_flow(client: TestClient, db_session: Session):
    payload = {
        "event_name": "AI & ML Conference 2026",
        "issuer_name": "Tech Org",
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
        ],
    }

    # Submit job (SYNC_WORKER=True in conftest processes it immediately)
    res = client.post("/api/v1/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Check GET /jobs/{job_id} status
    status_res = client.get(f"/api/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    data = status_res.json()

    assert data["job_id"] == job_id
    assert data["status"] == JobStatus.COMPLETED.value
    assert data["total_count"] == 2
    assert data["generated_count"] == 2
    assert data["failed_count"] == 0
    assert data["pending_count"] == 0
    assert data["progress_percent"] == 100.0
    assert data["started_at"] is not None
    assert data["completed_at"] is not None


def test_individual_certificate_failure_isolated(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    # Monkeypatch CertificateGenerator.generate to raise an exception for a specific recipient
    orig_generate = CertificateGenerator.generate

    def mock_generate(self, recipient_name, event_name, issuer_name, issue_date, certificate_id):
        if recipient_name == "Corrupted User":
            raise RuntimeError("Simulated PDF font rendering corruption error")
        return orig_generate(
            self, recipient_name, event_name, issuer_name, issue_date, certificate_id
        )

    monkeypatch.setattr(CertificateGenerator, "generate", mock_generate)

    payload = {
        "event_name": "Resilience Workshop",
        "issuer_name": "QA Guild",
        "recipients": [
            {"name": "Good User 1", "email": "good1@example.com"},
            {"name": "Corrupted User", "email": "corrupt@example.com"},
            {"name": "Good User 2", "email": "good2@example.com"},
        ],
    }

    res = client.post("/api/v1/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Job status should be COMPLETED_WITH_ERRORS
    job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    data = job_res.json()

    assert data["status"] == JobStatus.COMPLETED_WITH_ERRORS.value
    assert data["total_count"] == 3
    assert data["generated_count"] == 2
    assert data["failed_count"] == 1
    assert data["progress_percent"] == 100.0

    # Test GET /jobs/{job_id}/certificates?status=FAILED
    failed_certs_res = client.get(f"/api/v1/jobs/{job_id}/certificates?status=FAILED")
    assert failed_certs_res.status_code == 200
    failed_data = failed_certs_res.json()

    assert failed_data["total"] == 1
    assert len(failed_data["items"]) == 1
    failed_item = failed_data["items"][0]
    assert failed_item["recipient_name"] == "Corrupted User"
    assert failed_item["status"] == CertificateStatus.FAILED.value
    assert "Simulated PDF font rendering corruption error" in failed_item["error_message"]
    assert failed_item["download_url"] is None


def test_list_certificates_pagination(client: TestClient):
    payload = {
        "event_name": "Pagination Test Event",
        "issuer_name": "Pagination Org",
        "recipients": [{"name": f"User {i}", "email": f"user{i}@example.com"} for i in range(5)],
    }

    res = client.post("/api/v1/jobs", json=payload)
    job_id = res.json()["job_id"]

    # Page 1, page_size 2
    page1_res = client.get(f"/api/v1/jobs/{job_id}/certificates?page=1&page_size=2")
    assert page1_res.status_code == 200
    p1 = page1_res.json()
    assert p1["total"] == 5
    assert p1["page"] == 1
    assert p1["page_size"] == 2
    assert p1["total_pages"] == 3
    assert len(p1["items"]) == 2

    # Page 3, page_size 2
    page3_res = client.get(f"/api/v1/jobs/{job_id}/certificates?page=3&page_size=2")
    assert page3_res.status_code == 200
    p3 = page3_res.json()
    assert len(p3["items"]) == 1
