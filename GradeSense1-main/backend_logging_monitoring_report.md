# GradeSense Backend: Logging, Monitoring, and Error Handling

This document provides a technical audit of the logging, traceability, and error handling mechanisms within the GradeSense backend to ensure MVP readiness.

## 1. Logging Audit

The system uses a centralized logging configuration defined in `app/core/logging_config.py`.

| Module Group | File Name | Logging Method | Key Events Logged | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Global Config** | `app/core/logging_config.py` | `logging.basicConfig` | Global level and format initialization | Working |
| **API Routes** | `app/routes/grading.py` | Central `logger` | Job start/stop, blueprint locking, submission regrading | Good |
| **API Routes** | `app/routes/uploads.py` | Central `logger` | File uploads, GridFS storage events, processing starts | Good |
| **Core Pipeline** | `app/services/pipelines/ai_structured_engine.py` | Central `logger` | ALIGNMENT_GATE checks, LLM structured results | Needs IDs |
| **OCR Services** | `app/utils/ocr_provider/core.py` | Central `logger` | Provider initialization, failover to fallback, Gemini triggers | Working |
| **Background Jobs**| `app/routes/grading.py` (BG logic) | Central `logger` + DB Status | Job progress, success/failure counts, parallel task errors | Detailed |
| **Utilities** | `app/utils/retry.py` | Central `logger` | Exponential backoff attempts (RETRY_STAGE) | Working |

### Recommendations
1. **Remove Print Statements**: Ensure all remaining `print()` calls in old utility modules are replaced with `logger.debug()` or `logger.info()`.
2. **Standardize Field Tags**: Use consistent tags like `[OCR]`, `[LLM]`, or `[PIPELINE]` in log messages for easier filtering.

---

## 2. Traceability (Answer Sheet Life Cycle)

Traceability allows an engineer to follow a single answer sheet from upload to final score.

| Pipeline Stage | Critical Identifiers | Logs Inputs/Outputs | Tracing Ease | Improvement |
| :--- | :--- | :--- | :--- | :--- |
| **API Entry** | `user_id`, `exam_id` | Yes (Metadata) | High | N/A |
| **Job Queuing** | `job_id`, `exam_id` | Yes (Status) | High | N/A |
| **Student Info** | `student_id`, `filename` | Yes (Parsed ID) | Medium | Log `student_id` in same line as `submission_id`. |
| **Extraction** | `exam_id` | Often missing ID | Low | Deep LLM logic needs `exam_id` in every warning/error. |
| **Grading** | `submission_id` | Result totals | Medium | Include `blueprint_version` in final grading log summary. |

### Recommendations to Improve Traceability
*   **Correlation IDs**: Deep service functions (like `extract_question_structure`) should accept an optional `correlation_id` (e.g., `exam_id`) and include it in all log messages.
*   **Log Contextual IDs**: Standardize patterns like `logger.info(f"[{exam_id}] Step description")` across all pipeline modules.

---

## 3. Error Handling & Robustness

GradeSense implements a layered approach to error handling to prevent pipeline crashes.

| Stage / Module | Type of Errors Handled | Handling Strategy | Missing Coverage | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **AI Stage Call** | `Exception`, `ValueError` | `run_with_retry` (Retry) | Rate limit (429) | Add jitter to backoff. |
| **PDF Conversion**| `Exception` | `conversion_semaphore` (Retry) | Memory exhaustion | Kill worker if PDF-top-image fails too many times. |
| **Background Job** | `Global Exception` | `db.grading_jobs` update (Graceful Fail) | Interrupted processes | Add a heartbeat or "stale" job reaper. |
| **Database** | Connection errors | Bubbles up to route | N/A | Use standard FastAPI exception handlers. |
| **LLM Output** | `JSONDecodeError` | Partial Recovery / Repair | Complex hallucinations | Schema-validating repair logic is working well. |

### Common Handling Patterns
*   **Bubble-up to Route**: Routes catch all exceptions, log the stack trace, and return 500.
*   **Job Status Update**: If a single paper in a batch fails, the system increments the `failed` count and continues with the next paper instead of crashing the whole job.

### Recommendations for Robustness
1. **Specific Exceptions**: Replace broad `except Exception:` with specific types (e.g., `JSONDecodeError`, `FileNotFoundError`) where possible.
2. **Boundary Cleanup**: Ensure file locks or temporary directories are cleaned up in a `finally` block if a stage fails.
3. **User-Facind Error Mapping**: Map internal errors (e.g., `GeminiOCRService unavailable`) to user-friendly messages in the API response.
