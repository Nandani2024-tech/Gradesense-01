# Flow: Dashboard Load

## STEP 1: Entry Point

**UI Interaction**: User lands on `/teacher/dashboard` after login or by direct navigation.
**Initial State**: Authenticated teacher session with valid `session_token` cookie.

---

## STEP 2: UI → Frontend Trace

* [App.js](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/App.js#L191) → **Route Handler**: Matches the `/teacher/dashboard` path and renders the `Dashboard` component.
* [Dashboard.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/Dashboard.jsx#L51) → **Lifecycle Hook**: `useEffect` triggers three parallel fetch operations: `fetchDashboard()`, `fetchClassSnapshot()`, and `fetchBatches()`.
* [Dashboard.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/Dashboard.jsx#L57) → **Data Request**: Uses `axios.get` to query the specific analytics endpoints.

---

## STEP 3: API Call

* **Primary Endpoint**: `GET /api/analytics/dashboard`
* **Snapshot Endpoint**: `GET /api/dashboard/class-snapshot`
* **Payload**: None (Identity determined by session cookie).

---

## STEP 4: Backend Trace

* [analytics.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/analytics.py#L35) → **Route Handler**: `get_dashboard_analytics` verifies the user role is "teacher".
* [deps.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/deps.py#L13) → **Dependency**: `get_current_user` extracts `user_id` from the session cookie.
* [analytics_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/analytics/analytics_service.py#L16) → **Service Logic**: `get_dashboard_analytics` coordinates calls to multiple repositories to aggregate counts (exams, students, submissions).
* [analytics_repo.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/repositories/analytics_repo.py) → **Data Access**: Provides raw counts and filtered results for dashboard cards.

---

## STEP 5: Database

* **Query**: `db.exams.count_documents({"teacher_id": "user_..."})`
* **Table**: `exams`
* **Why**: To display the "Total Exams" count on the dashboard card.
* **Query**: `db.submissions.find({"exam_id": {"$in": exam_ids}}).sort("graded_at", -1).limit(10)`
* **Table**: `submissions`
* **Why**: To populate the "Recent Submissions" table with the latest AI-graded results.

---

## STEP 6: Response Flow Back

* **Backend**: Returns a `DashboardAnalyticsResponse` object containing a `stats` dictionary and an array of `recent_submissions`.
* **Frontend**: `Dashboard.jsx` calls `setAnalytics(response.data)`, which triggers a React re-render.
* **UI**: Skeleton loaders are replaced by data cards (e.g., "75 Students across 4 Batches") and a list of student names with their corresponding scores.

---

## STEP 7: Edge Cases

* **No Data**: If the teacher has no exams yet, the service returns zeroed stats. `Dashboard.jsx` renders an empty state with an "Upload your first paper" call-to-action button.
* **Database Timeout**: If the aggregation of tens of thousands of submissions is too slow, the frontend timeout (15s) might trigger, showing an error toast.
* **Unauthorized Role**: If a student manually navigates to this URL, the backend returns a `403 Forbidden` error, and the UI remains empty or redirects.
