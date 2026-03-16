# GradeSense Backend: Client-Specific Customization

This document outlines how the GradeSense backend handles multi-client support, specializing for different exam types, scoring rules, and report outputs to ensure MVP readiness.

## 1. Answer Sheet Formats

Client differentiation is primarily driven by the `exam_type` field (e.g., `upsc`, `college`, `universal`).

| Client / Exam Type | Supported Formats | Handling Modules | Status |
| :--- | :--- | :--- | :--- |
| **UPSC (Competitive)** | PDF, ZIP (Images), Google Drive | `app/routes/uploads.py`, `app/utils/files/` | Working |
| **College (Academic)** | PDF, ZIP (Images), Google Drive | `app/routes/uploads.py`, `layout.py` (heuristics) | Working |
| **Universal (General)**| PDF, ZIP (Images) | `app/routes/universal.py` | Working |

### Format Specifics
*   **PDF Conversion**: Centralized in `app/utils/files/converters.py` (DPI is configurable).
*   **Zip Handling**: `app/utils/files/zip_handler.py` extracts images for the pipeline.
*   **College-Specific Layout**: Uses OpenCV heuristics in `layout.py` to handle descriptive answer sheet structures typical in universities.

---

## 2. Scoring Rules

Scoring rules are resolved dynamically based on the exam context.

| Client Type | Implementation Module | Customizable Rules | Status |
| :--- | :--- | :--- | :--- |
| **UPSC** | `app/layers/resolver.py` | Strict grading mode, best-of-N selection, binary scoring | Configurable |
| **College** | `app/layers/ai_structured/` | Balanced grading, partial marks, OR-group math | Configurable |
| **Universal** | `app/services/score_normalization` | Standard backfilling, total marks enforcement | Fixed |

### Scoring Mechanisms
1. **Grading Layer Resolution**: `resolver.py` automatically selects the system prompt and grading mode (`strict` vs `balanced`) based on `exam_type` or inference from `exam_name`.
2. **Deterministic Validation**: `app/layers/ai_structured/validation.py` handles complex logic like `best_of` attempt rules and `or_group` mark resolution.
3. **Normalization**: `app/services/score_normalization/normalizer.py` ensures that all students are graded against the same blueprint, backfilling missing questions with zero marks.

---

## 3. Report Outputs

The backend focuses on providing rich data for frontend-rendered reports and dashboards.

| Report Type | Client Support | Generation Module | Status |
| :--- | :--- | :--- | :--- |
| **Teacher Dashboard** | All | `app/routes/analytics.py` | JSON-driven |
| **Class Performance**| All | `app/routes/analytics.py` | JSON-driven |
| **Peer Grouping** | Batch-based | `app/routes/analytics.py` | Customizable |
| **Topic Mastery** | All | `app/services/analytics/topic_extractor.py` | Customizable |
| **Misconceptions** | All | `app/routes/analytics.py` (AI-powered) | Fully AI-driven |

### Customization Status
- **JSON API**: All reports are available as curated JSON objects containing stats, trends, and AI insights.
- **Visualizations**: The backend provides categorized data (e.g., `score_distribution`) specifically formatted for frontend charts (Bar, Pie, Table).
- **Recommendation**: To support direct downloads, the backend should implement a generic CSV/PDF exporter utility in `app/utils/export.py` that can be triggered from current analytic routes.

---

## Recommendations for MVP Readiness
*   **Template Layering**: Formalize the `GradingLayerContext` into a more extensible plugin system to easily add new clients (e.g., `K-12`, `Corporate`).
*   **Rule Centralization**: Move hardcoded heuristics in `layout.py` to a client-specific configuration file.
*   **CSV/PDF Export**: Implement backend-side generation for static "Top Performer" and "Class Snapshot" reports for offline archiving.
