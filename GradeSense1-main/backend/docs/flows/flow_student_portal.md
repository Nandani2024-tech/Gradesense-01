# Flow: Student Portal & Results

## STEP 1: Entry Point

**UI Interaction**: Student logs in and lands on their personal dashboard in `StudentDashboard.jsx`.
**Initial State**: Authenticated student with a `session_token` cookie.

---

## STEP 2: UI → Frontend Trace

* [App.js](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/App.js#L203) → **Route Handler**: Matches `/student/dashboard` and renders the student version of the dashboard.
* [StudentDashboard.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/student/Dashboard.jsx#L31) → **Data Fetch**: `useEffect` calls `fetchStudentAnalytics()` to populate the "Subject Health" and "Recent Results" sections.
* [Results.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/student/Results.jsx#L45) → **Detail View**: Student clicks "View Details" on an exam card to see question-by-question marks and AI feedback.

---

## STEP 3: API Call

* **Primary Endpoint**: `GET /api/analytics/student-dashboard`
* **Detail Endpoint**: `GET /api/submissions/{submission_id}`
* **Payload**: None (Identity determined by session cookie).

---

## STEP 4: Backend Trace

* [student_portal.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/student_portal.py#L30) → **Route Handler**: `get_student_dashboard` verifies the user role is "student".
* [dashboard_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/analytics/dashboard_service.py) → **Business Logic**: Aggregates the student's history, weak topics, and recent peer comparisons.
* [submission_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/submissions/submission_service.py#L51) → **Detail Fetch**: `get_submission` is called with `user_role="student"`. This triggers a specific check to ensure `results_published` is `true` for the parent exam.

---

## STEP 5: Database

* **Query**: `db.submissions.find({"student_id": "user_..."}).sort("graded_at", -1)`
* **Table**: `submissions`
* **Why**: To list all exams the student has completed and their final status (AI Graded / Reviewed).
* **Query**: `db.exams.find_one({"exam_id": "..."})`
* **Table**: `exams`
* **Why**: To verify the `results_published` flag before showing marks to the student.

---

## STEP 6: Response Flow Back

* **Backend**: Returns a `StudentDashboardResponse` with a clean view of their performance.
* **Frontend**: `Dashboard.jsx` updates state and displays a line chart of the student's "Journey" (progress over time).
* **UI**: Student sees their percentile, average score, and a list of "Topic Mastery" heatmaps.

---

## STEP 7: Edge Cases

* **Results Not Published**: If the student tries to access a submission ID via URL before the teacher clicks "Publish", the backend returns a `403 Forbidden` with the message "Results for this exam are not yet available".
* **No Submissions**: For a new student, the dashboard shows a "Welcome" view with "0 Exams Taken" and advice on how to get started.
* **Topic Drilldown**: Students can click on a specific topic (e.g., "Polity") to see all questions they've answered in that topic across multiple exams.
