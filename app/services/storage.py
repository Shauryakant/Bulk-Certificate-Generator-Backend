import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings


class Storage(ABC):
    """Abstract storage interface for generated certificate PDFs."""

    @abstractmethod
    def save(self, job_id: str, certificate_id: str, pdf_bytes: bytes) -> str:
        """Saves PDF bytes atomically and returns the stored file path."""
        pass

    @abstractmethod
    def get_path(self, job_id: str, certificate_id: str) -> str:
        """Returns the file path for a given certificate."""
        pass

    @abstractmethod
    def exists(self, job_id: str, certificate_id: str) -> bool:
        """Checks if a certificate file exists."""
        pass

    @abstractmethod
    def get_bytes(self, job_id: str, certificate_id: str) -> bytes:
        """Reads and returns the bytes of a stored certificate."""
        pass


class LocalStorage(Storage):
    """Local filesystem implementation of Storage using atomic writes."""

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            base_dir = get_settings().STORAGE_DIR
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_path(self, job_id: str, certificate_id: str) -> str:
        return str(self.base_dir / job_id / f"{certificate_id}.pdf")

    def exists(self, job_id: str, certificate_id: str) -> bool:
        return Path(self.get_path(job_id, certificate_id)).exists()

    def save(self, job_id: str, certificate_id: str, pdf_bytes: bytes) -> str:
        target_path = Path(self.get_path(job_id, certificate_id))
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file in same directory then replace
        temp_fd, temp_path = tempfile.mkstemp(dir=target_path.parent, prefix="cert_", suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(pdf_bytes)
            os.replace(temp_path, target_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return str(target_path)

    def get_bytes(self, job_id: str, certificate_id: str) -> bytes:
        path = Path(self.get_path(job_id, certificate_id))
        if not path.exists():
            raise FileNotFoundError(f"Certificate file not found: {path}")
        return path.read_bytes()
