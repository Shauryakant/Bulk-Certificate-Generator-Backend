# Bulk Certificate Generator (Backend API)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![ReportLab](https://img.shields.io/badge/ReportLab-4.0+-orange.svg)](https://www.reportlab.com/)

A high-performance, asynchronous bulk certificate generation API designed for scale. Accepts a single API request with thousands of recipients, validates data upfront with recipient-level failure isolation, generates PDF certificates in parallel using ReportLab, tracks job status and progress, and streams generated certificates individually or as a ZIP archive.

---

## Architecture Overview

```mermaid
flowchart TD
    Client["Client / Frontend"] -->|POST /api/v1/jobs| API["FastAPI Application"]
    API -->|1. Validate Request| Val["Validation Service"]
    API -->|2. Store Job & Recipients| DB[("Relational DB (SQLite/Postgres)")]
    API -->|3. Return 202 Accepted| Client
    API -->|4. Dispatch Job| Worker["ThreadPoolExecutor Worker"]
    
    subgraph Background Processing
        Worker -->|Fetch Pending Cert| CertLoop["Certificate Loop"]
        CertLoop -->|Render PDF| Gen["ReportLab Generator"]
        CertLoop -->|Atomic Write| Storage["Local Storage / S3"]
        CertLoop -->|Isolated Transaction| DB
    end

    Client -->|GET /jobs/{id}| API
    Client -->|GET /jobs/{id}/certificates| API
    Client -->|GET /certificates/{id}/download| API
    Client -->|GET /jobs/{id}/download| API
```

---

## Tech Stack & Architectural Justifications

- **FastAPI**: Asynchronous Python framework providing ultra-low latency, automatic OpenAPI documentation, and typed validation.
- **SQLAlchemy 2.0 (Typed ORM Style)**: Fully typed ORM schema definitions (`Mapped[...]`) with explicit relationship cascades and strict transaction controls. Compatible with SQLite (default) and PostgreSQL via `DATABASE_URL`.
- **Alembic**: Database migrations management allowing seamless schema versioning and deployment migration pipelines.
- **Pydantic v2 & `pydantic-settings`**: Fast data validation and environment settings management.
- **ReportLab**: Pure Python PDF rendering library with no C system dependencies or headless browser dependencies, making it light, fast, and easy to deploy.
- **Pytest & FastAPI TestClient (`httpx`)**: Complete unit and integration testing suite using isolated SQLite in-memory databases (`StaticPool`) and temporary filesystem fixtures.

---

## Prerequisites & Installation

### Prerequisites
- Python 3.11+
- `git`
- (Optional) Docker & Docker Compose

### Local Environment Setup

1. **Clone the repository**:
   ```bash
   git clone <repository_url>
   cd Aereo
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Set up Environment Variables**:
   Copy the `.env.example` template:
   ```bash
   cp .env.example .env
   ```

5. **Run Database Migrations**:
   ```bash
   alembic upgrade head
   ```

---

## Running the Application

### Local Development Server
Start the Uvicorn server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API docs will be available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Docker & Docker Compose
Run the API using Docker Compose:
```bash
docker-compose up --build -d
```

---

## Running Tests

Execute the full test suite with Pytest:
```bash
pytest
```

To run with verbose output and code coverage:
```bash
pytest -v --cov=app
```

---

## API Reference & `curl` Examples

### 1. Health Check
Checks service liveness.

- **URL**: `GET /health`
- **Response**: `200 OK`
```json
{
  "status": "ok"
}
```

```bash
curl -X GET "http://localhost:8000/health"
```

---

### 2. Submit Bulk Job
Submits a bulk job containing many recipients for certificate generation.

- **URL**: `POST /api/v1/jobs`
- **Status Code**: `202 Accepted`

**Sample Request Body**:
```json
{
  "event_name": "Advanced Python & Distributed Systems Workshop",
  "issuer_name": "Global Tech Academy",
  "issue_date": "2026-10-07",
  "recipients": [
    {
      "name": "Alice Johnson",
      "email": "alice@example.com"
    },
    {
      "name": "Bob Smith",
      "email": "bob@example.com"
    },
    {
      "name": "   ",
      "email": "invalid-blank-name@example.com"
    },
    {
      "name": "Charlie Brown",
      "email": "charlie-invalid-email"
    },
    {
      "name": "Alice Johnson",
      "email": "alice@example.com"
    }
  ]
}
```

**Sample Response**:
```json
{
  "job_id": "4cf4358f-94b8-4f1e-a5e9-503520d91e16",
  "status": "PENDING",
  "total_count": 5,
  "status_url": "/api/v1/jobs/4cf4358f-94b8-4f1e-a5e9-503520d91e16"
}
```

```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Distributed Systems Bootcamp",
    "issuer_name": "Tech Institute",
    "recipients": [
      {"name": "Alice Johnson", "email": "alice@example.com"},
      {"name": "Bob Smith", "email": "bob@example.com"}
    ]
  }'
```

---

### 3. Get Job Status & Progress
Polls job processing status, counts, and completion percentage.

- **URL**: `GET /api/v1/jobs/{job_id}`
- **Response**: `200 OK`

```json
{
  "job_id": "4cf4358f-94b8-4f1e-a5e9-503520d91e16",
  "status": "COMPLETED_WITH_ERRORS",
  "event_name": "Advanced Python & Distributed Systems Workshop",
  "issuer_name": "Global Tech Academy",
  "issue_date": "2026-10-07",
  "total_count": 5,
  "generated_count": 2,
  "failed_count": 3,
  "pending_count": 0,
  "progress_percent": 100.0,
  "created_at": "2026-10-07T14:50:20Z",
  "started_at": "2026-10-07T14:50:20Z",
  "completed_at": "2026-10-07T14:50:22Z"
}
```

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/4cf4358f-94b8-4f1e-a5e9-503520d91e16"
```

---

### 4. List Job Certificates
Lists certificates for a job with optional status filter and pagination.

- **URL**: `GET /api/v1/jobs/{job_id}/certificates?status=FAILED&page=1&page_size=20`
- **Response**: `200 OK`

```json
{
  "items": [
    {
      "id": "c1f7a0de-8899-4a11-b203-902183abc111",
      "recipient_name": "   ",
      "recipient_email": "invalid-blank-name@example.com",
      "status": "FAILED",
      "error_message": "Recipient name cannot be empty or whitespace-only.",
      "download_url": null
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/4cf4358f-94b8-4f1e-a5e9-503520d91e16/certificates?status=GENERATED"
```

---

### 5. Download Single Certificate
Streams a single generated PDF certificate.

- **URL**: `GET /api/v1/certificates/{certificate_id}/download`
- **Response**: `200 OK` (`application/pdf`)
- **Error Statuses**: `404 Not Found` (missing cert/file), `409 Conflict` (still pending or failed).

```bash
curl -X GET "http://localhost:8000/api/v1/certificates/0fe9638d-e6fe-44ac-9652-49d5be51c016/download" \
  --output certificate.pdf
```

---

### 6. Download Job ZIP Archive
Streams a ZIP file containing all successfully generated PDFs for a job.

- **URL**: `GET /api/v1/jobs/{job_id}/download`
- **Response**: `200 OK` (`application/zip`)
- **Error Statuses**: `404 Not Found` (job not found), `409 Conflict` (job still running or 0 generated certs).

```bash
curl -X GET "http://localhost:8000/api/v1/jobs/4cf4358f-94b8-4f1e-a5e9-503520d91e16/download" \
  --output certificates.zip
```

---

## Design Decisions & Trade-Offs

### 1. Asynchronous ThreadPool Processing vs. Synchronous vs. Celery/Redis
- **Why Background ThreadPoolExecutor**: Bulk processing 5,000 certificates synchronously inside a single HTTP request would cause HTTP connection timeouts, block API server threads, and degrade client experience. Using an in-app bounded `ThreadPoolExecutor` backed by database state persistence eliminates extra infrastructure overhead (Redis/RabbitMQ/Celery) while guaranteeing HTTP `202 Accepted` response within milliseconds.
- **Production Upgrade Path**: Replace `ThreadPoolExecutor` with a dedicated task queue (Celery + Redis / RQ) and standard object storage (AWS S3 / Google Cloud Storage).

### 2. Recipient-Level vs. Request-Level Validation (Partial Failure Semantics)
- **Request-Level (422)**: Rejects the request immediately if top-level structure is invalid (missing `event_name`, missing `issuer_name`, empty `recipients` array, or exceeding `MAX_RECIPIENTS_PER_REQUEST`).
- **Recipient-Level (Partial Success)**: Invalid recipient rows (blank names, invalid email formats, duplicate emails in request) are flagged as `FAILED` with explicit `error_message` strings in the DB without blocking valid recipients.

### 3. Per-Certificate Database Transaction Isolation
- Each certificate in a job is processed in its own `try...except` block with its own isolated database transaction (`SessionLocal()`). A rendering exception or disk error on one recipient never rolls back previously generated certificates or stops execution for remaining recipients.

### 4. Atomic File Writes
- Certificates are rendered into temporary files (`.tmp`) in the storage folder before being atomically renamed (`os.replace`) to `STORAGE_DIR/{job_id}/{certificate_id}.pdf`. This ensures HTTP download endpoints never serve incomplete or corrupted PDF files.

---

## Known Limitations & Future Improvements

1. **Celery / Redis Queue Integration**: For massive multi-instance horizontal scaling.
2. **AWS S3 Storage Abstraction**: Swap `LocalStorage` for `S3Storage` by implementing the `Storage` interface.
3. **Authentication & Rate Limiting**: Add OAuth2/JWT or API Key authentication and Redis token-bucket rate limiting.
4. **Webhooks & Email Delivery**: Notify external systems or send email attachments upon job completion.
5. **Retry Endpoint**: `POST /jobs/{job_id}/retry-failed` to re-trigger generation for certificates with `FAILED` status.

---

## License
MIT License.
