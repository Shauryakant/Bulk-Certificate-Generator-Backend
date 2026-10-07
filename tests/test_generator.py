import tempfile
from datetime import date

from app.services.generator import CertificateGenerator
from app.services.storage import LocalStorage


def test_certificate_generator_outputs_valid_pdf_bytes():
    generator = CertificateGenerator()
    pdf_bytes = generator.generate(
        recipient_name="Alice Smith",
        event_name="Python Masterclass 2026",
        issuer_name="Tech Institute",
        issue_date=date(2026, 10, 7),
        certificate_id="cert-12345-abc",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF files always start with the magic header %PDF
    assert pdf_bytes.startswith(b"%PDF")


def test_certificate_generator_handles_long_name_and_unicode():
    generator = CertificateGenerator()
    long_unicode_name = "Dr. Alexander Bartholomäus von Hapsburg-Lothringen III, PhD"

    pdf_bytes = generator.generate(
        recipient_name=long_unicode_name,
        event_name="International Genomic Science Summit 2026",
        issuer_name="Global Science Foundation",
        issue_date="2026-10-07",
        certificate_id="cert-long-name-999",
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_local_storage_atomic_save_and_retrieve():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalStorage(base_dir=temp_dir)
        job_id = "job-uuid-1"
        cert_id = "cert-uuid-1"
        data = b"%PDF-1.4 test certificate content"

        assert storage.exists(job_id, cert_id) is False

        saved_path = storage.save(job_id, cert_id, data)

        assert storage.exists(job_id, cert_id) is True
        assert saved_path.endswith(f"{job_id}\\{cert_id}.pdf") or saved_path.endswith(
            f"{job_id}/{cert_id}.pdf"
        )

        retrieved_bytes = storage.get_bytes(job_id, cert_id)
        assert retrieved_bytes == data
