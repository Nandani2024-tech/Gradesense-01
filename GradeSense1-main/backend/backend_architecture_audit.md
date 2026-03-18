# Backend Architecture Audit Report

## 1. Executive Summary
**Overall Architectural Health Score: Needs Improvement**

The GradeSense backend demonstrates a solid foundation with clear intent toward a layered, service-oriented architecture. It successfully separates concerns in many areas (e.g., `routes` vs `services`, `models` as Pydantic entities, dedicated `adapters` for external integrations). However, the implementation suffers from several critical architectural "leaks" and violations of industry-standard dependency directions. Specifically, the relationship between `services` and `adapters` is often inverted, and the `models` layer contains dependencies on higher-level `schemas`. Several files have grown beyond manageable sizes, suggesting a need for further modularization.

---

## 2. Folder Responsibility Analysis

| Folder | Purpose | Observed Usage | Status |
| :--- | :--- | :--- | :--- |
| `routes/` | API endpoint layer, request parsing. | Defines FastAPI routes, delegates logic to services. | **Matches** |
| `services/` | Business logic and orchestration. | Contains core workflows and some low-level integrations (e.g., `services/llm`). | **Partial** |
| `domain/` | Core business rules and models. | Contains factories and domain-specific services (e.g., `blueprint_domain_service`). | **Matches** |
| `models/` | Database and persistence models. | Defines Pydantic models for DB entities. | **Matches** |
| `schemas/` | API contract (Request/Response). | Defines validation schemas for API communication. | **Matches** |
| `adapters/` | External system wrappers. | Wrappers for LLM and OCR; some logic incorrectly depends on `services`. | **Partial** |
| `layers/` | AI reasoning and grading abstractions. | Dedicated AI logic for different exam types (e.g., `ai_structured`). | **Matches** |
| `infrastructure/`| Low-level system infrastructure. | Handles caching, DB config, and core infrastructure logic. | **Matches** |
| `utils/` | Small reusable helper functions. | Nearly empty; logic often resides in `infrastructure/serialization` or inline. | **Unused** |
| `middleware/` | Request lifecycle interceptors. | CORS and metrics implementations. | **Matches** |
| `pipelines/` | Multi-step workflows. | Located under `services/pipelines/`; handles complex OCR/grading flows. | **Matches** |
| `workers/` | Background processing. | Async task processors for grading and uploads. | **Matches** |
| `core/` | System configuration/bootstrapping. | Configuration, exceptions, and logging setup. | **Matches** |

---

## 3. Architecture Violations

### Violation 1: Inverted Dependency Direction (Adapters → Services)
*   **File:** `app/adapters/llm_adapter.py`
*   **Issue:** The adapter (low-level) imports from `app.services.llm` (higher-level business/application logic). According to the reference model, `services` should call `adapters`, not the other way around. This makes the LLM integration logic difficult to swap or test in isolation.

### Violation 2: Circular/Inverted Dependency (Models → Schemas)
*   **File:** `app/models/exam.py`
*   **Issue:** The model imports from `app.schemas.exam.exam_create` and others as part of a "Re-export compatibility layer". Models should be the lowest level and should not depend on API schema definitions.

### Violation 3: Business Logic / Utilities in Pipelines
*   **File:** `app/services/pipelines/ai_structured_engine.py`
*   **Issue:** Contains raw logic such as `_question_structure_to_legacy_questions` and `_apply_audit_tree_marks` which should reside in `domain/factories` or a dedicated mapping service.

---

## 4. Dependency Direction Analysis

**Current Violations:**
1.  **`app/adapters/llm_adapter.py`** → `app.services.llm` (Adapter importing Service)
2.  **`app/models/exam.py`** → `app.schemas.*` (Model importing Schema)
3.  **`app/repositories/*.py`** → Many repositories are directly imported and instantiated in pipeline/service files instead of using dependency injection (e.g., `ai_structured_engine.py` instantiates `ExamRepo()` at the module level).

**Recommendation:** Enforce a strict `Services → Adapters` and `Services → Repositories` flow using Abstract Base Classes (ABCs) or dependency injection containers.

---

## 5. Large or Overloaded Files

| File Path | Line Count | Responsibility / Issue |
| :--- | :--- | :--- |
| `app/services/pipelines/ai_structured_engine.py` | ~1107 | **High Overload**: Orchestrates extraction, alignment, and persists data. Contains internal helper functions for data transformation that should be externalized. |
| `app/adapters/visual_extractor.py` | ~590 | **Potential Overload**: Handles OCR collection, math parsing, and header detection in one file. |
| `app/routes/exams.py` | ~357 | **Moderate size**: Getting large; consider splitting student-mode routes into a separate file. |

---

## 6. Pipeline Architecture Review

The system uses a robust pipeline architecture for AI grading, particularly the **AI Structured Engine**.
*   **Strengths:** Clear separation of steps (Extraction → Alignment → Grading). Use of locking mechanisms (`_acquire_exam_lock`) to prevent race conditions.
*   **Weaknesses:** The `ai_structured_engine.py` is a monolithic orchestrator. It manages state transitions, DB interactions, and log generation all within a single file, making it a high-risk failure point and difficult to unit test.

---

## 7. Utility Folder Review

The `app/utils` folder is currently a "ghost" directory (containing only `__init__.py`).
*   **Finding:** Logic that typically belongs in `utils` (e.g., `safe_numeric`, `file_utils`) has been moved to `app/infrastructure/serialization/` or is implemented as private helpers within large files.
*   **Verdict:** While avoiding a "dumping ground" is good, the lack of a centralized utility layer has led to logic duplication or bloating of service/pipeline files.

---

## 8. Strengths of the Architecture

*   **Clean Layering (Routes/Services/Repos):** The general flow of data from FastAPI routes to services and then to repositories is consistent across the codebase.
*   **Excellent Domain Separation:** The `layers/` folder correctly isolates specific AI reasoning logic from the rest of the application.
*   **Robust Background Processing:** Use of `workers/` for asymmetric tasks provides good scalability for heavy AI workloads.
*   **Centralized Configuration:** The `core/` folder effectively manages environment variables and system-wide settings.

---

## 9. Weaknesses and Risks

*   **Tight Coupling:** The direct instantiation of repositories and services in module scopes (e.g., `exam_repo = ExamRepo()`) makes mocking and testing difficult.
*   **Monolithic Pipelines:** The 1100+ line pipeline engine is hard to maintain and prone to regressions.
*   **Layer Leakage:** The `models` layer's awareness of `schemas` and `adapters` awareness of `services` are significant architectural debts that will cause maintenance issues as the system grows.

---

## 10. Final Architecture Score

| Category | Score (1-10) |
| :--- | :--- |
| **Architecture Maturity** | 6 |
| **Maintainability** | 5 |
| **Scalability** | 7 |
| **Separation of Concerns** | 6 |
| **Industry Best Practice Alignment**| 5 |

**Overall Evaluation: Fair**
The system is functional and production-ready but requires a refactoring phase to decouple layers and modularize the core pipelines to meet high-level engineering standards.
