from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Certificate, CertificateStatus, Job, JobStatus
from app.services.worker import recover_interrupted_jobs


def test_startup_recovery_interrupted_job(db_session: Session):
    # 1. Manually simulate a job left in PROCESSING state after a server crash
    interrupted_job = Job(
        event_name="Crash Recovery Workshop",
        issuer_name="Reliability Org",
        issue_date=date.today(),
        status=JobStatus.PROCESSING.value,
        total_count=2,
        success_count=0,
        failure_count=0,
    )
    db_session.add(interrupted_job)
    db_session.flush()

    cert1 = Certificate(
        job_id=interrupted_job.id,
        recipient_name="Recovered Recipient 1",
        recipient_email="rec1@example.com",
        status=CertificateStatus.PENDING.value,
    )
    cert2 = Certificate(
        job_id=interrupted_job.id,
        recipient_name="Recovered Recipient 2",
        recipient_email="rec2@example.com",
        status=CertificateStatus.PENDING.value,
    )
    db_session.add_all([cert1, cert2])
    db_session.commit()

    # 2. Trigger startup recovery
    recovered = recover_interrupted_jobs(db=db_session)
    assert recovered == 1

    # 3. Verify job transitions to COMPLETED and certificates are GENERATED
    db_session.refresh(interrupted_job)
    assert interrupted_job.status == JobStatus.COMPLETED.value
    assert interrupted_job.success_count == 2
    assert interrupted_job.failure_count == 0

    certs = db_session.query(Certificate).filter(Certificate.job_id == interrupted_job.id).all()
    assert len(certs) == 2
    for cert in certs:
        assert cert.status == CertificateStatus.GENERATED.value
        assert cert.file_path is not None
