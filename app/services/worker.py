from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.db.models import Certificate, CertificateStatus, Job, JobStatus
from app.db.session import SessionLocal
from app.services.generator import CertificateGenerator
from app.services.storage import LocalStorage, Storage

settings = get_settings()

# Application-wide thread pool executor
executor = ThreadPoolExecutor(
    max_workers=settings.WORKER_THREADS,
    thread_name_prefix="cert_worker_",
)


def process_single_certificate(
    job_id: str,
    certificate_id: str,
    generator: CertificateGenerator,
    storage: Storage,
) -> None:
    """
    Processes an individual certificate in an isolated DB transaction and try/except block.
    Guarantees failure in one certificate does not impact other certificates in the job.
    """
    db: Session = SessionLocal()
    try:
        cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()

        if not cert or not job:
            logger.error(f"[job_id={job_id}] Cert {certificate_id} or Job missing in background.")
            return

        if cert.status != CertificateStatus.PENDING.value:
            # Already processed or pre-flagged as failed upfront
            return

        # Attempt PDF generation
        pdf_bytes = generator.generate(
            recipient_name=cert.recipient_name,
            event_name=job.event_name,
            issuer_name=job.issuer_name,
            issue_date=job.issue_date,
            certificate_id=cert.id,
        )

        # Atomic storage write
        file_path = storage.save(job_id=job.id, certificate_id=cert.id, pdf_bytes=pdf_bytes)

        # Update certificate status to GENERATED
        cert.status = CertificateStatus.GENERATED.value
        cert.file_path = file_path
        cert.generated_at = datetime.now(UTC)
        cert.error_message = None

        # Update job counts
        job.success_count += 1
        db.commit()

        logger.info(f"[job_id={job_id}] Generated cert {cert.id} for {cert.recipient_email}")

    except Exception as exc:
        db.rollback()
        logger.error(
            f"[job_id={job_id}] Failed generating certificate {certificate_id}: {exc}",
            exc_info=True,
        )

        # Record failure in isolated transaction
        fail_db: Session = SessionLocal()
        try:
            cert_to_fail = (
                fail_db.query(Certificate).filter(Certificate.id == certificate_id).first()
            )
            job_to_fail = fail_db.query(Job).filter(Job.id == job_id).first()

            if cert_to_fail and job_to_fail:
                cert_to_fail.status = CertificateStatus.FAILED.value
                cert_to_fail.error_message = f"PDF generation error: {str(exc)}" or "Unknown error"
                job_to_fail.failure_count += 1
                fail_db.commit()
        except Exception as fail_exc:
            fail_db.rollback()
            logger.error(
                f"[job_id={job_id}] Error saving failure state for {certificate_id}: {fail_exc}"
            )
        finally:
            fail_db.close()
    finally:
        db.close()


def process_job(
    job_id: str,
    generator: CertificateGenerator | None = None,
    storage: Storage | None = None,
) -> None:
    """
    Executes the background processing loop for a job.
    Updates job status transitions (PROCESSING -> COMPLETED / COMPLETED_WITH_ERRORS / FAILED).
    """
    if generator is None:
        generator = CertificateGenerator()
    if storage is None:
        storage = LocalStorage()

    # 1. Mark job as PROCESSING
    db: Session = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"[job_id={job_id}] Job not found.")
            return

        if job.status not in (JobStatus.PENDING.value, JobStatus.PROCESSING.value):
            logger.info(f"[job_id={job_id}] Job already in final state: {job.status}")
            return

        job.status = JobStatus.PROCESSING.value
        if not job.started_at:
            job.started_at = datetime.now(UTC)
        db.commit()

        # Fetch all PENDING certificates for this job
        pending_cert_ids = [
            c.id
            for c in db.query(Certificate.id)
            .filter(
                Certificate.job_id == job_id, Certificate.status == CertificateStatus.PENDING.value
            )
            .all()
        ]
    finally:
        db.close()

    # 2. Process each certificate independently
    for cert_id in pending_cert_ids:
        process_single_certificate(
            job_id=job_id,
            certificate_id=cert_id,
            generator=generator,
            storage=storage,
        )

    # 3. Finalize Job state and counts
    final_db: Session = SessionLocal()
    try:
        job = final_db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        total_certs = final_db.query(Certificate).filter(Certificate.job_id == job_id).count()
        success_certs = (
            final_db.query(Certificate)
            .filter(
                Certificate.job_id == job_id,
                Certificate.status == CertificateStatus.GENERATED.value,
            )
            .count()
        )
        failed_certs = (
            final_db.query(Certificate)
            .filter(
                Certificate.job_id == job_id,
                Certificate.status == CertificateStatus.FAILED.value,
            )
            .count()
        )

        job.total_count = total_certs
        job.success_count = success_certs
        job.failure_count = failed_certs
        job.completed_at = datetime.now(UTC)

        if failed_certs == 0 and success_certs > 0:
            job.status = JobStatus.COMPLETED.value
        elif success_certs > 0 and failed_certs > 0:
            job.status = JobStatus.COMPLETED_WITH_ERRORS.value
        elif success_certs == 0:
            job.status = JobStatus.FAILED.value

        final_db.commit()
        logger.info(
            f"[job_id={job_id}] Job completed with final status={job.status} "
            f"(total={total_certs}, success={success_certs}, failed={failed_certs})"
        )
    finally:
        final_db.close()


def dispatch_job(
    job_id: str,
    generator: CertificateGenerator | None = None,
    storage: Storage | None = None,
) -> None:
    """Dispatches job to thread pool or runs synchronously if SYNC_WORKER is set."""
    current_settings = get_settings()
    if current_settings.SYNC_WORKER:
        process_job(job_id=job_id, generator=generator, storage=storage)
    else:
        executor.submit(process_job, job_id, generator, storage)
