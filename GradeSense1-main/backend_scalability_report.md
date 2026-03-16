# GradeSense Backend: Scalability and Parallelism

This document evaluates the multi-client support, pipeline isolation, and statelessness of the GradeSense backend to ensure it can scale effectively for MVP and production loads.

## 1. Multi-Client Support

GradeSense supports concurrent requests from multiple clients using a combination of unique session identifiers and resource-based throttling.

| Module / Pipeline | Concurrency Mechanism | Status | Recommendation |
| :--- | :--- | :--- | :--- |
| **Grading Job Route** | UUID `job_id` + MongoDB status tracking | Works | Ensure `job_id` indices are present in MongoDB to optimize polling. |
| **Submission Pipeline**| UUID `submission_id` + isolated GridFS storage | Works | Excellent isolation; no cross-session interference. |
| **PDF Conversion** | `conversion_semaphore` (asyncio) | Partially Works | Semaphore is **process-local**. In a multi-worker setup, use a distributed semaphore if CPU becomes a bottleneck. |
| **Global Throttling** | `app.utils.concurrency.semaphores` | Works | Current implementation is thread/async-safe within a single process. |

### Status Summary
- **Primary Support**: Full multi-client support for uploads and grading through unique IDs.
- **Limitation**: Concurrency limits (semaphores) are defined in-memory. Multiple server instances will not share these limits unless a distributed locker is added.

---

## 2. Pipeline Isolation and Statelessness

The core grading and extraction pipelines are designed to be stateless, ensuring that one session cannot pollute another.

| Pipeline Group | State Management | Isolation Level | Recommendation |
| :--- | :--- | :--- | :--- |
| **Extraction Engine** | Fetches blueprint via `exam_id`; returns in-memory JSON. | **Stateless** | Ensure LLM sessions (`session_id`) are unique per call to avoid context bleed. |
| **Grading Engine** | Processes `vision_answers` (bytes/dicts) in-memory. | **Stateless** | Clear results from memory immediately after storage. |
| **Alignment Cache** | In-memory dict in `app.utils.cache`. | **Isolated per ID** | Moving to Redis would allow this cache to be shared across multiple workers/nodes. |

### Isolation Audit
*   **Temporary Data**: Image base64 strings and intermediate packet objects are passed as function arguments or stored in GridFS.
*   **Shared State**: No shared global variables are used for storing session-specific data.

---

## 3. Temp Files, Caches, and Global States

Potential conflicts are minimized by avoiding local filesystem usage and using unique keys for all caches.

| Component | File / Path | Potential Conflict | Mitigation / Recommendation |
| :--- | :--- | :--- | :--- |
| **Local Filesystem** | N/A | Low | The system does not use `/tmp` or local folders for processing; data stays in RAM/GridFS. |
| **In-Memory Cache** | `app.utils.cache.py` | Overwrite | Keys use `(exam_id, version, hash)` or `submission_id` to prevent collisions. |
| **Advisory Locks** | `processing_lock_owner` | Race conditions | Use MongoDB `find_one_and_update` for atomic lock acquisition to prevent two simultaneous jobs on the same exam. |
| **GridFS** | `app.infrastructure.storage` | Name collision | Filenames include UUIDs. Safe. |

### Recommendations for Scalability
1. **Distributed Caching**: Migrate `app.utils.cache` from in-memory dictionaries to a distributed cache (like Redis) to support multi-node deployments.
2. **Atomic State Transitions**: Strictly use atomic MongoDB operations for transitioning `processing_state` and acquiring `processing_lock_owner`.
3. **External Semaphores**: For high-load production, consider a distributed semaphore (e.g., via Redlock) to enforce global limits on heavy CPU/LLM tasks.
