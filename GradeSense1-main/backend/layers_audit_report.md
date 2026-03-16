# Domain Layer Audit Report: app/layers

## Executive Summary

**Purpose:**
The `app/layers` folder is intended to encapsulate the pure domain logic of GradeSense, including grading rules, structure validation, and mark reconciliation. It serves as the heart of the "Clean Architecture" approach, isolated from infrastructure (AWS, DB) and orchestration (Pipelines, API).

**Architecture Health:** Moderate

**Compliance Score:** 74/100

**Verdict:**
**Minor Improvements Needed**. While the core logic is well-isolated in `ai_structured` and `universal` layers, several broken imports in folder `__init__.py` files and leaking domain logic in `app/services/grading` prevent a "Production Ready" status.

---

## 2. Folder Structure Overview

```
app/layers/
├── ai_structured/        # Core AI structure reasoning and validation
│   ├── mark_reasoner.py
│   ├── schemas.py
│   ├── structure_repair.py
│   ├── structure_validator.py
│   └── validation.py
├── college/              # College-specific grading rules
│   └── grader.py
├── college_v3/           # Vision-OCR based college contracts
│   └── contracts.py
├── universal/            # Generic objective/deterministic grading
│   └── grader.py
└── upsc/                 # UPSC specific strict policy enforcement
    └── policy.py
```

**Role of Folders:**
- `ai_structured`: Handles the reconciliation of conflicting mark sources (margin, OCR, inferred) and ensures JSON structure integrity.
- `college`: Contains legacy and current college-specific validation logic.
- `college_v3`: Defines the data contracts for the advanced Vision-OCR pipeline.
- `universal`: Provides a baseline grading path for objective questions.
- `upsc`: Implements the complex "strict mode" scoring caps required for UPSC exams.

---

## 3. File-Level Responsibility Analysis

| File | Responsibility | Type | Compliance |
| ---- | -------------- | ---- | ---------- |
| `ai_structured/mark_reasoner.py` | Deterministic mark reconciliation | Domain Logic | ✅ |
| `ai_structured/schemas.py` | Pydantic models for structure | Schema | ✅ |
| `ai_structured/structure_repair.py` | Auto-repair for OCR mismatches | Domain Logic | ✅ |
| `ai_structured/structure_validator.py` | Logical consistency checks | Validation | ✅ |
| `ai_structured/validation.py` | Payload normalization | Validation | ✅ |
| `college/grader.py` | College-specific validations | Validation | ✅ |
| `college_v3/contracts.py` | Data classes for Vision OCR | Contracts | ✅ |
| `universal/grader.py` | Objective grading logic | Domain Logic | ✅ |
| `upsc/policy.py` | Strict scoring caps | Domain Logic | ✅ |

---

## 4. Domain Purity Check

Modules were scanned for infrastructure or orchestration dependencies.

| File | Forbidden Import | Severity | Action Needed |
| ---- | -------------- | -------- | ------------- |
| (All) | None | N/A | OK |

**Result:** 0 forbidden imports from infrastructure/adapters. Strictly follows dependency direction.

---

## 5. Utility Canonicalization Check

| Helper | Found in Layers | Canonical Location | Status |
| ------ | --------------- | ------------------ | ------ |
| `to_float` | Yes | `app/utils/safe_numeric.py` | OK |
| `to_int` | Yes | `app/utils/safe_numeric.py` | OK |
| `parse_tolerant_json` | Yes | `app/utils/json_helpers.py` | OK |

**Result:** High compliance. Modules correctly use `app.utils` instead of local reimplementations.

---

## 6. Constants Compliance

| Constant | Location | Canonical | Status |
| -------- | -------- | --------- | ------ |
| `MAPPING_CONFIDENCE_THRESHOLD` | `app/constants/layers.py` | Yes | OK |
| `QUESTION_TYPE_LITERAL` | `ai_structured/schemas.py` | No | Move to constants |
| `_EXPLICIT_SOURCES` | `ai_structured/mark_reasoner.py` | No | Move to constants |

---

## 7. Infrastructure Leak Detection

| Finding | File | Type |
| ------- | ---- | ---- |
| "Vision OCR" in docstring | `college_v3/contracts.py` | Doc Leak |
| "OCR" as source label | `ai_structured/mark_reasoner.py` | Conceptual Leak |

**Analysis:** No direct leaks of `boto3`, `pymongo`, or `opencv` were detected in the `app/layers` folder.

---

## 8. Import Integrity Check

| File | Broken Import | Suggested Fix |
| ---- | ------------- | ------------- |
| `college/__init__.py` | `from .grader import grade_submission` | `grade_submission` is missing in `grader.py`. |
| `college_v3/__init__.py` | `from .engine import ...` | `engine.py` is missing in `college_v3`. |

---

## 9. Dependency Direction Analysis

**Current Pattern:**
`services` (e.g., `grading_core.py`) → `layers` (e.g., `upsc/policy.py`) ✅
`layers` → `utils` ✅
`layers` → `constants` ✅

**Issues Found:**
Domain logic for score clamping discovered in `app/services/grading/score_validator.py` instead of being inside `app/layers/universal/grader.py`.

---

## 10. Layer Design Evaluation

**Strengths:**
- Strong isolation of business logic in `ai_structured`.
- Use of Pydantic for schema validation.
- Consistent use of safe utility helpers.

**Weaknesses:**
- `ai_structured/mark_reasoner.py` is overly large (>1100 lines), making it hard to maintain.
- Broken entry points in sub-package `__init__.py` files.
- Leaked clamping logic in services.

---

## 11. Final Compliance Score

| Category | Score |
| -------- | ----- |
| Domain Purity | 18/20 |
| Import Integrity | 10/20 |
| Utility Canonicalization | 19/20 |
| Constants Centralization | 15/20 |
| Architecture Compliance | 12/20 |

**Total Score: 74 / 100**

---

---

## 13. Additional Observations

### Stale Cache Files
The `__pycache__` directory at the root of `app/layers` contains entries for:
- `grading_engine.py`
- `resolver.py`
- `constants.py`

These source files are currently **MISSING** from the workspace, suggesting they were recently moved (likely to `app/services`) but the package was not fully cleaned up.

### Stale Internal Documentation
The existing `app/layers/audit_report.md` is **STALE**. It references several large modules (like `grading_engine.py` as Orchestration) as if they were still present in the domain layer. This discrepancy should be addressed to avoid confusion for future developers.

---

## Final Verdict: **Minor Improvements Needed**

**Reasoning:**
The layer logic is theoretically clean but practically broken due to missing files (`engine.py` in `college_v3`) and missing function definitions (`grade_submission`). Additionally, pure domain rules (score clamping) are still residing in the service layer, violating the principle of a "fat" domain layer and "thin" service layer. The presence of stale cache files and outdated internal audit reports indicates a refactoring state that needs final consolidation.
