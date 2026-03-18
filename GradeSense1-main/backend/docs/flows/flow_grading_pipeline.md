# Flow: Multi-Paper Grading Pipeline

## STEP 1: Entry Point

**UI Interaction**: Teacher selects multiple student PDF files in `UploadGrade.jsx` and clicks "Process & Grade".
**Initial State**: Exam blueprint is locked, and teacher has selected the target batch.

---

## STEP 2: UI → Frontend Trace

* [UploadGrade.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/UploadGrade.jsx#L200) → **Job Submission**: `handleBulkUpload` collects all files and pushes them to the background grading route.
* [Dashboard.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/Dashboard.jsx) → **Progress Polling**: Once the job starts, the UI switches to a "Processing" view that polls the job status every 3 seconds.

---

## STEP 3: API Call

* **Endpoint (Start)**: `POST /api/exams/{exam_id}/grade-papers-bg`
* **Endpoint (Poll)**: `GET /api/grading-jobs/{job_id}`
* **Payload**: `Multipart/FormData` with the array of student PDFs.

---

## STEP 4: Backend Trace

* [grading.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/grading.py#L23) → **Route Handler**: `grade_papers_background` receives files and immediately returns a `job_id`.
* [grading_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/grading/grading_service.py#L22) → **Queue Logic**: Validates files, creates the job record, and spawns the background task via `asyncio.create_task`.
* [grading_worker.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/workers/grading_worker.py#L14) → **Worker Orchestrator**: Runs `run_grading_pipeline` which manages concurrency (Semaphore of 2).
* [services/grading_pipeline.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/grading_pipeline.py) → **AI Pipeline**:
    1. **OCR**: Extracts handwritten text.
    2. **Alignment**: Maps student answers to blueprint questions.
    3. **Evaluation**: Uses Gemini LLM to grade against the rubric/model answer.
* [student_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/students/student_service.py) → **Identity Resolution**: Attempts to find the student ID in the OCR text or uses the filename as fallback.

---

## STEP 5: Database

* **Query**: `db.grading_jobs.insert_one({"job_id": "...", "status": "processing", "total_papers": 10})`
* **Table**: `grading_jobs`
* **Why**: To track lifecycle progress for the frontend polling.
* **Query**: `db.submissions.insert_one({"submission_id": "...", "question_scores": [...], "status": "ai_graded"})`
* **Table**: `submissions`
* **Why**: To store the permanent record of the student's result and AI feedback.

---

## STEP 6: Response Flow Back

* **Backend**: Polling endpoint returns `{ "status": "processing", "progress": 0.5, ... }`.
* **Frontend**: The progress bar in `UploadGrade.jsx` or `Dashboard.jsx` increments.
* **UI**: When progress hits 100%, the UI shows a "Grading Complete" success message and a link to "Review Results".

---

## STEP 7: Edge Cases

* **Pipeline Crash**: If a specific paper fails (e.g., corrupt PDF), the worker logs the error, increments the `failed` counter, and continues with the next paper.
* **LLM Rate Limit**: The worker implements a Semaphore to prevent hitting Gemini API limits.
* **No Student Found**: If `orchestrate_student_id` fails, the submission is saved with `student_name: "Unknown (Filename)"` and `status: "needs_review"`.
