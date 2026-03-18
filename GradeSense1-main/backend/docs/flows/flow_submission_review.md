# Flow: Review & Results Publishing

## STEP 1: Entry Point

**UI Interaction**: Teacher navigates to `ReviewPapers.jsx`, selects a submission, and clicks on a question to adjust marks or adds a comment.
**Initial State**: Submission exists with status `ai_graded`.

---

## STEP 2: UI → Frontend Trace

* [ExamSubmissionsView.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ExamSubmissionsView.jsx) → **List View**: Displays all student results for a specific exam.
* [ReviewPapers.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ReviewPapers.jsx#L85) → **Review Interface**: Loads the submission details, including the annotated PDF images and AI feedback.
* [ReviewPapers.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ReviewPapers.jsx#L140) → **Update Action**: Teacher modifies a score and clicks "Save Changes".

---

## STEP 3: API Call

* **Endpoint (Fetch)**: `GET /api/submissions/{submission_id}`
* **Endpoint (Update)**: `PUT /api/submissions/{submission_id}`
* **Endpoint (Publish)**: `POST /api/exams/{exam_id}/publish-results`
* **Payload (Update)**:
  ```json
  { "updates": { "question_scores": [...], "status": "reviewed" } }
  ```

---

## STEP 4: Backend Trace

* [submissions.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/submissions.py#L64) → **Route Handler**: `update_submission` receives the manual adjustments.
* [submission_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/submissions/submission_service.py) → **Business Logic**: Re-calculates total marks and percentage based on the new manual scores.
* [exams.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/exams.py#L329) → **Publish Handler**: `publish_exam_results` updates the exam metadata to make results visible to students.

---

## STEP 5: Database

* **Query**: `db.submissions.update_one({"submission_id": "..."}, {"$set": {"total_score": 18.5, "status": "reviewed"}})`
* **Table**: `submissions`
* **Why**: To persist the human-verified marks over the AI-generated ones.
* **Query**: `db.exams.update_one({"exam_id": "..."}, {"$set": {"results_published": true}})`
* **Table**: `exams`
* **Why**: To enable the "View Results" button on the student-facing dashboard.

---

## STEP 6: Response Flow Back

* **Backend**: Returns a success message and the updated submission object.
* **Frontend**: `ReviewPapers.jsx` shows a "Saved" toast notification.
* **UI (Student)**: The next time the student logs in, their dashboard shows the latest result for this exam.

---

## STEP 7: Edge Cases

* **Bulk Approval**: Teacher can click "Approve All" which triggers `bulk_approve_submissions` (marking all `ai_graded` as `reviewed` in one query).
* **Unpublish**: If the teacher finds a systemic error, they can "Unpublish", which immediately hides the scores from all student portals.
* **Manual Override Audit**: The system maintains the original AI logs in `grading_logs`, allowing teachers to see what the AI initially thought even after a manual override.
