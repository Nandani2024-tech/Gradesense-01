# Flow: Authentication

## STEP 1: Entry Point

**UI Interaction**: User clicks "Sign in as Teacher" or "Sign in as Student" on the Login Page.
**Initial State**: User selects an exam type (UPSC/College) which is stored in `localStorage` for post-auth context.

---

## STEP 2: UI → Frontend Trace

* [LoginPage.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/LoginPage.jsx#L48) → **Initiates Google OAuth**: `handleGoogleLogin` builds the Google Auth URL with `client_id`, `redirect_uri`, and `state` (containing role/exam_type).
* [AuthCallback.jsx](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/pages/AuthCallback.jsx#L15) → **Handles Redirect**: Google redirects to `/callback?code=...`. This component extracts the code and state.
* [axios.js](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/frontend/src/App.js#L49) → **Global Config**: Ensures `withCredentials: true` is set for all subsequent requests to handle HttpOnly cookies.

---

## STEP 3: API Call

* **Endpoint**: `POST /api/auth/google/callback`
* **Payload**: 
  ```json
  {
    "code": "4/0AeaYSH...",
    "state": "{\"role\":\"teacher\",\"exam_type\":\"upsc\",\"timestamp\":17107...}",
    "redirect_uri": "http://localhost:3000/callback"
  }
  ```

---

## STEP 4: Backend Trace

* [routes/auth.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/routes/auth.py#L26) → **Route Handler**: `google_oauth_callback` receives the payload and delegates to the Auth Service.
* [auth_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/auth/auth_service.py#L20) → **Logic Orchestrator**: `process_google_oauth` exchanges the code for a Google token and fetches user info from Google's `/v2/userinfo` endpoint.
* [auth_service.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/auth/auth_service.py#L92) → **User Sync**: `_get_or_create_google_user` handles identifying if the user is new or returning.
* [admin_repo.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/repositories/admin_repo.py) → **Data Access**: Performs MongoDB operations to find/create user and session records.

---

## STEP 5: Database

* **Query**: `db.users.find_one({"email": "user@gmail.com"})`
* **Table**: `users`
* **Why**: To check if the user is already registered or needs a new profile.
* **Query**: `db.user_sessions.insert_one({"session_token": "session_...", "user_id": "user_...", ...})`
* **Table**: `user_sessions`
* **Why**: To persist the login session for cookie-based authentication.

---

## STEP 6: Response Flow Back

* **Backend**: `auth.py` sets an `HttpOnly` cookie named `session_token` and returns the user object as JSON.
* **Frontend**: `AuthCallback.jsx` receives the user object, stores the exam type in `localStorage`, and calls `navigate("/teacher/dashboard")`.
* **UI**: The user is redirected to the dashboard, and the `ProtectedRoute` in `App.js` allows the navigation because the session cookie is now present.

---

## STEP 7: Edge Cases

* **Invalid Code**: If the code is expired or used twice, `process_google_oauth` throws a `CustomServiceException` (400), and `AuthCallback.jsx` shows an alert and redirects to login.
* **New User Redirect**: If `profile_completed` is `false`, `AuthCallback.jsx` redirects to `/profile/setup` instead of the dashboard.
* **Expired Session**: On app reload, if `auth/me` returns `401`, the `ProtectedRoute` clears the auth state and forces a redirect to `/login`.
