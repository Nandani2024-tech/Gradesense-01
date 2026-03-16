# Backend Architecture Audit Report

## 1. Executive Summary
**Overall Architectural Health Score: Needs Improvement**

The GradeSense backend follows a partially realized Clean/Layered Architecture. While there is a clear attempt to segregate concerns into folders like `routes`, `services`, and `domain`, the implementation suffers from significant logic leakage. The API layer (`routes`) is heavily overloaded with orchestration and business rules that should reside in services or domain models. The `domain` layer is underdeveloped, with much of the "core business logic" actually residing in `services` or `utils`. The system is modular but lacks a strict enforcement of dependency directions and layer responsibilities, which may pose maintenance risks at scale.

---

## 2. Folder Responsibility Analysis

| Folder | Purpose | Observed Usage | Matches Practice? |
| :--- | :--- | :--- | :--- |
| **routes/** | API endpoints, parsing, formatting | Contains significant business logic and orchestration. | ❌ No (Overloaded) |
| **services/** | Business workflows & orchestration | Fragmented; many sub-services; some orchestration leaked to routes. | ⚠️ Partial |
| **domain/** | Core business rules (Pure logic) | Pure but very sparse. Missing many core rules. | ⚠️ Partial |
| **models/** | DB schemas and persistence models | Standard Pydantic/Mongo models; some re-export clutter. | ✅ Yes |
| **schemas/** | Data validation & API contracts | Standard request/response schemas. | ✅ Yes |
| **adapters/** | External system wrappers (LLM, OCR) | Well-isolated wrappers for AWS, LLM, and CV. | ✅ Yes |
| **layers/** | AI/Reasoning logic | Isolated AI grading logic for different exam types. | ✅ Yes |
| **infrastructure/** | Low-level system infra (DB, Storage) | Very sparse, but correctly focused on storage/DB. | ✅ Yes |
| **utils/** | Reusable helper functions | Contains business logic (e.g., blueprint workflows). | ❌ No (Dump Ground) |
| **middleware/** | Request lifecycle interceptors | Standard CORS and metrics middleware. | ✅ Yes |
| **pipelines/** | Multi-step processing workflows | Split between top-level folders and services. | ⚠️ Partial |
| **workers/** | Background processing | Identified under `services/workers/`. Correct usage. | ✅ Yes |
| **core/** | System config and bootstrapping | Standard config, database, and logging setup. | ✅ Yes |

---

## 3. Architecture Violations

### Rule 1 — Layer Responsibility
- **Violation in `app/routes/grading.py`**: The `grade_papers_background` function (Lines 218-510) contains extensive orchestration logic including file validation, student identification, submission insertion, and job management. This belongs in a `GradingService`.
- **Violation in `app/routes/grading.py`**: `_ensure_locked_blueprint_or_raise` (Lines 70-215) performs complex business state transitions and database updates.
- **Violation in `app/routes/exams.py`**: Logic for risky question overrides and blueprint health checks is embedded in `update_exam`.

### Rule 3 — Separation of Concerns
- **File: `app/routes/grading.py`**: Mixes HTTP handling, Database queries, and AI pipeline orchestration in single endpoint handlers.
- **File: `app/services/grading/grading_core.py`**: Mixes orchestration logic with low-level annotation normalization logic.

### Rule 7 — Utility Misuse
- **File: `app/utils/blueprint.py`**: Contains complex business logic for computing blueprint health, attempt rules, and effective marks. This is quintessential domain-service logic, not a generic "utility".
- **File: `app/utils/aws_question_identity.py`**: Highly specific integration logic buried in utils.

---

## 4. Dependency Direction Analysis
**Current Direction**: `routes → services → adapters / layers / domain`
**Violations Found**:
- **Implicit Domain dependencies on Services**: Many "domain" rules are implemented in `services`, forcing services to depend on each other horizontally rather than depending on a robust central domain.
- **Model Re-exports**: `app/models/exam.py` imports and re-exports `app/schemas/exam/exam_create.py`, crossing persistence and contract layers unnecessarily.

---

## 5. Large or Overloaded Files
- **`app/routes/grading.py` (856 lines)**: Too heavy. Handles job status, background grading, simple grading, and regrading.
- **`app/routes/exams.py` (925 lines)**: Too heavy. Handles CRUD, blueprint locking/unlocking, extraction, and student workflows.
- **`app/services/grading/grading_core.py` (310 lines)**: Orchestrator that is becoming a "God Object" for grading logic.
- **`app/adapters/visual_extractor.py` (21.8 KB)**: Indicates high complexity in a single adapter file.

---

## 6. Pipeline Architecture Review
The pipeline architecture is **moderately structured**.
- **Strength**: Use of `GradingEngine` in `services/grading_pipeline/pipeline_runner.py` shows a good attempt at orchestration classes.
- **Weakness**: Pipeline orchestration is fragmented. Some pipelines are in `services/`, others are vertical slices like `ocr/` or `mapping/`. This inconsistency makes it hard to trace the "Grand Pipeline" for grading.

---

## 7. Utility Folder Review
The `utils` folder is currently a **dumping ground**.
It contains:
- `blueprint.py`: Business rules for exams.
- `paddle_service.py` / `vision_ocr_service.py`: Should be in `adapters`.
- `auth/`: Should be in `middleware` or `services`.
- **Verdict**: Utils should be restricted to generic helpers (date, math, string manipulation). Business-aware logic should be relocated.

---

## 8. Strengths of the Architecture
- **Adapter Pattern**: Excellent isolation of external dependencies (Textract, Gemini, OCR).
- **Service Verticality**: Modular folders like `ocr`, `student`, and `mapping` provide good feature-level isolation.
- **Domain Purity**: Existing domain models in `domain/` are remarkably clean and framework-independent.
- **Factory Usage**: `ExamFactory` and `SubmissionFactory` usage in routes shows a move toward proper domain object construction.

---

## 9. Weaknesses and Risks
- **Route Bloat**: High risk of bugs when HTTP-level changes impact business logic.
- **Incomplete Domain Layer**: Core rules are hard to find and duplicate across different pipelines.
- **Difficult Testing**: Logic in routes is significantly harder to unit test than logic in pure service or domain layers.

---

## 10. Final Architecture Score

| Category | Score |
| :--- | :--- |
| **Architecture Maturity** | 6/10 |
| **Maintainability** | 5/10 |
| **Scalability** | 7/10 |
| **Separation of Concerns** | 4/10 |
| **Industry Practice Alignment** | 5/10 |

**Verdict**: The architecture is functional and modular but lacks the discipline of a production-grade Clean Architecture. Refactoring logic out of `routes` into `services` and strengthening the `domain` layer are critical next steps.
