# GradeSense Backend Analysis Report: Duplications, Overrides, and Dead Code

This report provides a comprehensive analysis of the GradeSense backend to identify redundancies, inconsistent overrides, and dead code. It serves as a reference for modularization and MVP readiness.

## 1. Duplicate Implementations

The following functions and classes exist in multiple modules with the same or very similar functionality.

| Name | Modules/Files | Purpose | Recommendation |
| :--- | :--- | :--- | :--- |
| `_b64_to_cv2` | `region_ocr.py`, `image_utils.py`, `college_layout.py`, `college_normalization.py` | Converts base64 encoded images to OpenCV numpy arrays. | **Consolidate**: Move to a central `app/utils/image_processing.py` and import everywhere. |
| `_cv2_to_b64` | `region_ocr.py`, `image_utils.py`, `college_normalization.py` | Converts OpenCV numpy arrays back to base64 strings with configurable quality. | **Consolidate**: Move to a central `app/utils/image_processing.py`. |
| `validate_structure` | `ai_structured/validation.py`, `ai_structured/structure_validator.py` | Validates the extracted exam structure (questions, marks, or-groups). | **Consolidate**: Merge into a single `structure_validator.py`. Currently, `ai_structured_engine.py` uses one, while `ai_extraction_service.py` uses the other. |
| `_contiguous` | `ai_structured/validation.py`, `ai_structured/structure_validator.py` | Checks if a list of numbers is contiguous. | **Consolidate**: Dedup after merging validation files. |
| `_to_float` | `services/pipelines/ai_structured_engine.py`, `ai_structured/mark_resolver.py` | Safely converts values to float with defaults. | **Consolidate**: Use a single utility from `app/utils/safe_numeric.py`. |

## 2. Method Overrides

Analysis of inheritance and method overrides in the system.

| Class Name | Method Name | Parent Class | Difference in Behavior | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| `VisionOCRService` | `detect_text_from_base64` | `BaseOCR` | Implements Google Vision API logic with retry and timeout. | **Keep**: Correct implementation of the interface. |
| `PaddleOCRService` | `detect_structure_from_base64` | `BaseOCR` | Implements table detection using PPStructure. | **Keep**: Core functionality for Paddle provider. |
| `ExamQuestion` | (Class Definition) | `DomainExamQuestion` | Adds `question_uuid` field and `model_config` for DB compatibility. | **Keep**: Document this layer separation. |
| `SubQuestion` | (Class Definition) | `DomainSubQuestion` | Adds `model_config` and ignores extra fields during Pydantic parsing. | **Keep**: Standard architectural pattern for DB vs Domain models. |

> [!NOTE]
> Most overrides are consistent with the `BaseOCR` abstract base class. However, `detect_structure_from_base64` returns empty tables in `VisionOCRService` as it's not supported natively, which is a correct "graceful fallback".

## 3. Dead Code

Functions or classes identified as unused or candidates for removal.

| Name | Module/File | Observed Context | Suggested Action |
| :--- | :--- | :--- | :--- |
| `check_counts.py` | `backend/` | Development script for checking counts. | **Remove** (or move to `scripts/`). |
| `testt.py` | `backend/` | Scratch file. | **Remove**. |
| `raw_layer_version` | `models/exam.py` | Field in `Exam` model. | **Check Usage**: If unused in frontend/logic, remove. |
| `_dedupe_subparts` | `ai_structured/structure_repair.py` | Helper for repair. | **Keep**: It is used within `apply_structure_repairs` but should be audited for efficacy. |

> [!IMPORTANT]
> Several files in the `backend/` root (e.g., `check_mongo.py`, `layers_files.txt`) should be moved to a `scripts/` or `docs/` folder to keep the production root clean.

## 4. Duplicate Constants

Constants or thresholds defined in multiple locations, causing potential inconsistency.

| Constant Name | Modules/Files | Value Differences | Recommendation |
| :--- | :--- | :--- | :--- |
| `ALIGNMENT_COVERAGE_GATE` | `layers/constants.py`, `services/pipelines/ai_structured/alignment_service.py` | 0.7 vs (0.7 from import) | **Centralize**: Ensure all services import from `layers/constants.py`. |
| `MAPPING_COVERAGE_GATE_MIN` | `services/grading/constants.py` | 0.75 (env-configurable) | **Unify**: Resolves conflict with `ALIGNMENT_COVERAGE_GATE`. One source of truth is needed. |
| `MCQ_OPTIONS` | `services/config/pipeline_constants.py` | `["A", "B", "C", "D"]` | **Centralize**: Move to `layers/constants.py` for global access. |
| `DEFAULT_QUESTION_TYPE` | `layers/constants.py` | `"descriptive"` | **Keep**: Canonical definition. |

## Conclusion

The GradeSense backend is in a good state for MVP but suffers from "utility drift" where common operations (base64 conversion, numeric safety) are re-implemented locally. Consolidating these into `app/utils/` and merging the two structure validation modules in `app/layers/ai_structured/` will significantly improve maintainability and readiness.
