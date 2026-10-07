import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.models import Certificate, Job  # noqa: F401
from app.db.session import get_db
from app.main import app


@pytest.fixture
def temp_storage_dir() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def test_settings(temp_storage_dir: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(
        APP_NAME="Test Certificate API",
        ENV="testing",
        DEBUG=True,
        DATABASE_URL="sqlite:///:memory:",
        STORAGE_DIR=temp_storage_dir,
        MAX_RECIPIENTS_PER_REQUEST=100,
        WORKER_THREADS=2,
        SYNC_WORKER=True,  # Run worker synchronously in tests
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.worker.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.jobs.get_settings", lambda: settings)
    return settings


@pytest.fixture
def db_session(test_settings: Settings) -> Generator[Session, None, None]:
    # Use SQLite memory engine with StaticPool so all connections share the same in-memory DB
    engine = create_engine(
        test_settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    import app.db.session
    import app.services.worker

    orig_session_local = app.db.session.SessionLocal
    orig_worker_session_local = app.services.worker.SessionLocal

    app.db.session.SessionLocal = TestingSessionLocal
    app.services.worker.SessionLocal = TestingSessionLocal

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.db.session.SessionLocal = orig_session_local
        app.services.worker.SessionLocal = orig_worker_session_local


@pytest.fixture
def client(db_session: Session, test_settings: Settings) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db_session.expire_all()
        yield db_session

    def override_get_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
