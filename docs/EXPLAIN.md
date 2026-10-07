# Interview Explanation Guide & Technical Deep-Dive (`EXPLAIN.md`)

This guide is designed as an interview preparation cheat sheet for explaining, debugging, and expanding the **Bulk Certificate Generator API**.

---

## 1. Request Lifecycle (Step-by-Step)

```
[Client] ---> POST /api/v1/jobs 
               |
               v
       (1) app/api/jobs.py: submit_job()
               |
               +---> (2) app/services/job_service.py: create_job()
               |          |
               |          +---> (2a) validate_request_level() -> 422 if invalid top-level
               |          +---> (2b) validate_and_normalise_recipients() -> flags bad rows upfront
               |          +---> (2c) Insert Job (PENDING) & Certificates in DB
               |
               +---> (3) app/services/worker.py: dispatch_job()
               |          |
               |          +---> Submits process_job() to ThreadPoolExecutor
               |
               v
       Return HTTP 202 Accepted {job_id, status: "PENDING", status_url}
               |
               v
  [Background Worker Thread] process_job()
               |
               +---> Updates Job status to PROCESSING
               +---> Iterates over PENDING certificates:
               |          |
               |          v  (In isolated DB Session per certificate)
               |       (a) CertificateGenerator.generate() -> ReportLab PDF bytes
               |       (b) LocalStorage.save() -> Atomic write (.tmp -> .pdf)
               |       (c) Commit Certificate GENERATED state
               |          (If Exception -> Rollback, Commit Certificate FAILED state)
               |
               +---> Finalize Job status (COMPLETED / COMPLETED_WITH_ERRORS / FAILED)
```

---

## 2. Key Design Decisions & Why They Were Made

### Q1: Why asynchronous background processing instead of synchronous HTTP response?
- **Answer**: Rendering 5,000 PDF certificates in ReportLab requires CPU calculation and file I/O that can take tens of seconds or minutes. Running this inside a synchronous HTTP request handler would block worker threads, cause client HTTP request timeouts (e.g. 30s gateway timeout), and break scalability. Returning HTTP `202 Accepted` immediately with a `job_id` provides optimal UX and scalability.

### Q2: Why ThreadPoolExecutor instead of Celery/Redis for this scope?
- **Answer**: ThreadPoolExecutor gives asynchronous background processing out of the box with zero external infrastructure dependencies (like Redis or RabbitMQ). For a single-node API server or take-home assignment, this keeps setup minimal while fulfilling non-blocking background requirements.
- **Production Upgrade Path**: Replace ThreadPoolExecutor with Celery/RQ + Redis/RabbitMQ when scaling to multi-server horizontally autoscaled deployment clusters.

### Q3: Why per-certificate database transactions?
- **Answer**: If all 5,000 certificates were processed inside one giant database transaction, a single failure on recipient #4,999 would cause a rollback of all previous 4,998 generated certificates. By isolating each certificate in its own `try...except` block and DB transaction (`SessionLocal()`), failures are isolated and partial progress is preserved.

### Q4: Why atomic file writes (`.tmp` + `os.replace`)?
- **Answer**: Writing PDF bytes directly to the final file path can leave a partially written 0-byte or corrupted file on disk if the process crashes mid-write. Writing to a `.tmp` file and using atomic rename (`os.replace`) guarantees that any file present at `STORAGE_DIR/{job_id}/{cert_id}.pdf` is 100% complete and valid for client downloads.

---

## 3. Likely Interview Questions & Answers

### Q: "How would this scale to 1 Million recipients?"
1. **Chunked Ingestion**: Instead of receiving 1M rows in a single JSON body, accept file uploads (CSV/S3 URL) or chunk requests (e.g. 5,000 per request).
2. **Distributed Task Queue**: Replace ThreadPoolExecutor with Celery/RabbitMQ. Partition the 1M job into batches of 500 certificates dispatched to worker nodes across Kubernetes pods.
3. **Cloud Object Storage**: Swap `LocalStorage` for `S3Storage` using multipart uploads or presigned S3 download URLs.
4. **Database Indexing & Partitioning**: Index `(job_id, status)` and partition `certificates` table by range/hash or `job_id`.

### Q: "What happens if the application server crashes mid-job?"
- **Answer**: On startup, FastAPI's `lifespan` context manager invokes `recover_interrupted_jobs()`. It queries the DB for any jobs left in `PROCESSING` status, finds their `PENDING` certificates, and re-queues them to the worker pool without duplicating completed work.

### Q: "How would you implement a Retry endpoint for failed certificates?"
- **Answer**: Add `POST /api/v1/jobs/{job_id}/retry-failed`:
  1. Fetch all certificates for `job_id` with `status == FAILED`.
  2. Reset their status to `PENDING` and set `error_message = None`.
  3. Reset `Job.status = PROCESSING`.
  4. Call `dispatch_job(job_id)`.

### Q: "How would you support multiple certificate templates?"
- **Answer**:
  1. Add a `Template` interface with a `render(data) -> bytes` method.
  2. Implement concrete classes: `StandardTemplate`, `GoldBadgeTemplate`, `ModernMinimalTemplate`.
  3. Store `template_id` on the `Job` model and pass it to `CertificateGenerator.generate()`.

---

## 4. Code Map: Where to Change Things

| Requirement Change | File Location | Key Function / Class |
| :--- | :--- | :--- |
| Change PDF design, colors, font, layout | `app/services/generator.py` | `CertificateGenerator.generate()` |
| Add S3 or Cloud storage support | `app/services/storage.py` | Implement `Storage` interface |
| Change recipient validation rules | `app/services/validation.py` | `validate_and_normalise_recipients()` |
| Change worker thread count | `.env` / `app/core/config.py` | `WORKER_THREADS` |
| Add new API endpoints | `app/api/jobs.py` / `certificates.py` | FastAPI APIRouter handlers |
| Modify DB models & schema | `app/db/models.py` | `Job`, `Certificate` (run Alembic afterwards) |
