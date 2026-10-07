from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, Job, JobStatus


def test_create_job_success(client: TestClient, db_session: Session):
    payload = {
        "event_name": "FastAPI & SQLAlchemy Masterclass",
        "issuer_name": "Dev Academy",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202

    data = response.json()
    assert "job_id" in data
    assert data["status"] == JobStatus.PENDING.value
    assert data["total_count"] == 2
    assert data["status_url"] == f"/api/v1/jobs/{data['job_id']}"

    # Verify persisted DB records
    job = db_session.query(Job).filter(Job.id == data["job_id"]).first()
    assert job is not None
    assert job.event_name == "FastAPI & SQLAlchemy Masterclass"
    assert job.issuer_name == "Dev Academy"
    assert job.total_count == 2
    assert job.failure_count == 0

    certs = db_session.query(Certificate).filter(Certificate.job_id == job.id).all()
    assert len(certs) == 2
    for cert in certs:
        assert cert.status == CertificateStatus.PENDING.value


def test_create_job_request_level_validation_failures(client: TestClient):
    # 1. Missing event_name
    res1 = client.post(
        "/api/v1/jobs",
        json={
            "event_name": "  ",
            "issuer_name": "Dev Academy",
            "recipients": [{"name": "Alice", "email": "alice@example.com"}],
        },
    )
    assert res1.status_code == 422
    assert res1.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "event_name" in res1.json()["error"]["message"]

    # 2. Empty recipients
    res2 = client.post(
        "/api/v1/jobs",
        json={
            "event_name": "Python Summit",
            "issuer_name": "Dev Academy",
            "recipients": [],
        },
    )
    assert res2.status_code == 422
    assert res2.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "recipients" in res2.json()["error"]["message"]


def test_create_job_with_recipient_level_validation_failures(
    client: TestClient, db_session: Session
):
    payload = {
        "event_name": "Genomics Workshop",
        "issuer_name": "Science Org",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Bad Email User", "email": "invalid-email-format"},
            {"name": "   ", "email": "blankname@example.com"},
            {"name": "Duplicate User", "email": "valid@example.com"},
        ],
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = db_session.query(Job).filter(Job.id == job_id).first()
    assert job.total_count == 4
    assert job.failure_count == 3  # Bad email, blank name, duplicate email

    certs = (
        db_session.query(Certificate)
        .filter(Certificate.job_id == job_id)
        .order_by(Certificate.recipient_email)
        .all()
    )
    assert len(certs) == 4

    valid_certs = [c for c in certs if c.status == CertificateStatus.PENDING.value]
    failed_certs = [c for c in certs if c.status == CertificateStatus.FAILED.value]

    assert len(valid_certs) == 1
    assert valid_certs[0].recipient_email == "valid@example.com"

    assert len(failed_certs) == 3
    for fc in failed_certs:
        assert fc.error_message is not None
