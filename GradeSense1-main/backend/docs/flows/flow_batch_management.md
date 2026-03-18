# Flow: Batch Management

## STEP 1: Entry Point

**UI Interaction**: User navigates to `/teacher/batches` and clicks "Create New Batch" or "Add Students".
**Initial State**: Teacher is on the Batch Management screen viewing a list of existing class groups.

---

## STEP 2: UI → Frontend Trace

* [ManageBatches.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ManageBatches.jsx) → **Main Page**: Displays the grid of batches.
* [AddBatch.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/AddBatch.jsx#L45) → **Form Submission**: `handleSubmit` captures the batch name and calls the API to create it.
* [ManageStudentsInBatch.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/teacher/ManageStudentsInBatch.jsx#L60) → **Student Registration**: Handles bulk student entry or individual "Add Student" clicks for a specific batch.

---

## STEP 3: API Call

* **Endpoint**: `POST /api/batches`
* **Payload**: 
  ```json
  { "name": "Class 10-A Science" }
  ```
* **Endpoint (Add Student)**: `POST /api/batches/{batch_id}/students`
* **Payload**:
  ```json
  { "student_id": "stud_xyz123" }
  ```

---

## STEP 4: Backend Trace

* [batches.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/batches.py#L32) → **Route Handler**: `create_batch` receives the Pydantic model and calls the Batch Service.
* [batch_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/batches/batch_service.py) → **Logic Layer**: `create_batch` generates a unique `batch_id` and prepares the document for MongoDB.
* [analytics_repo.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/repositories/analytics_repo.py) → **Persistence**: Inserts the batch record (Note: Batch data is stored in the analytics repo layer due to its cross-cutting nature).

---

## STEP 5: Database

* **Query**: `db.batches.insert_one({"batch_id": "batch_...", "name": "...", "teacher_id": "...", "status": "active"})`
* **Table**: `batches` (Referenced via analytics_repo)
* **Why**: To create the shared grouping context for students and exams.
* **Query**: `db.users.update_one({"user_id": "student_..."}, {"$addToSet": {"batches": "batch_id"}})`
* **Table**: `users`
* **Why**: To link students to multiple batches they might be part of.

---

## STEP 6: Response Flow Back

* **Backend**: Returns a `BatchBaseResponse` with the newly created `batch_id`.
* **Frontend**: `AddBatch.jsx` receives the ID and redirects the teacher back to the list or to the new Batch View.
* **UI**: The new batch card appears in the list with "0 Students" and "0 Exams" initial stats.

---

## STEP 7: Edge Cases

* **Duplicate Names**: The service level handles duplicate name rejection if necessary, but currently allows distinct IDs for same names.
* **Batch Closing**: Closing a batch doesn't delete it but updates `status: "closed"`, hiding it from active dashboards.
* **Empty Batch Deletion**: The system prevents deleting batches that still have students or exams linked to them.
