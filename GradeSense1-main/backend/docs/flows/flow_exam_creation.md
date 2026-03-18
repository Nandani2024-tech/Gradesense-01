# Flow: Exam & Blueprint Creation

## STEP 1: Entry Point

**UI Interaction**: User clicks "Create Exam" in `ManageExams.jsx`, fills the name/subject, then uploads a Question Paper PDF.
**Initial State**: Authenticated teacher with a target batch selected.

---

## STEP 2: UI → Frontend Trace

* [ManageExams.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ManageExams.jsx) → **Creation Modal**: Captures basic metadata (Name, Batch, Date).
* [UploadGrade.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/UploadGrade.jsx#L145) → **Upload Trigger**: Specifically for the Question Paper step, it calls the `upload-question-paper` endpoint.
* [axios.js](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/App.js) → **Multi-part Data**: Sends the file as `FormData`.

---

## STEP 3: API Call

* **Endpoint 1 (Meta)**: `POST /api/exams`
* **Endpoint 2 (File)**: `POST /api/exams/{exam_id}/upload-question-paper`
* **Payload**: `Multipart/FormData` containing the PDF file.

---

## STEP 4: Backend Trace

* [uploads.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/uploads.py#L38) → **Route Handler**: `upload_question_paper` receives the file and triggers the upload service.
* [upload_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/uploads/upload_service.py) → **Storage Logic**: Saves the PDF to GridFS and sets the `status` to `processing`.
* [exam_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/exams/exam_service.py#L422) → **Extraction Orchestrator**: `extract_questions` is triggered automatically (or via manual UI click).
* [services/extraction/auto_extraction.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/extraction/auto_extraction.py) → **AI Logic**: 
    1. Converts PDF to images.
    2. Runs OCR on images.
    3. Sends OCR text to LLM (Gemini) with a prompt to extract question numbers, marks, and content.

---

## STEP 5: Database

* **Query**: `db.exams.update_one({"exam_id": "..."}, {"$set": {"questions": [...], "question_extraction_status": "completed"}})`
* **Table**: `exams`
* **Why**: To persist the structured "Blueprint" of the exam which will guide all future grading.
* **Query**: `db.fs.files` / `db.fs.chunks`
* **Table**: GridFS (Exams data)
* **Why**: To store the high-resolution Question Paper images for later display in the review portal.

---

## STEP 6: Response Flow Back

* **Backend**: Returns an `ExtractionResponse` containing the number of questions found (e.g., "Extracted 15 questions").
* **Frontend**: The UI refreshes the "Blueprint" tab, showing a table of questions with their max marks.
* **UI**: Teacher reviews the extracted table, edits any AI mistakes, and clicks "Lock Blueprint".

---

## STEP 7: Edge Cases

* **Blurry PDF**: If OCR fails, the LLM might return an empty list or gibberish. The `extraction_status` is marked as `failed`, and the teacher is prompted to manually enter questions.
* **Blueprint Locked**: If the teacher tries to re-extract after starting grading, the `validation_service` throws a `CustomServiceException` (409) to prevent data inconsistency.
* **Missing Marks**: The system defaults to 1.0 mark per question if not found by the AI.
