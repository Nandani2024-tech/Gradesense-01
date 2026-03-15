# Audit Report: app/layers Folder

This report provides a strict inventory and assessment of the `app/layers` folder as of March 2026. The goal is to inform domain logic isolation and refactoring efforts.

## Summary of Findings

| Category | Count | Primary Responsibility |
| :--- | :--- | :--- |
| **Domain Logic** | 12 | Business rules, grading logic, schemas, and data transformations. |
| **Infrastructure / Adapter** | 18 | AWS calls, DB clients, Vision/OCR integrations, and image processing. |
| **Orchestration / Pipeline** | 32 | Engines and task runners coordinating workflow execution. |
| **Utility / Helper** | 15 | Parsing utilities, constants, and shared helper functions. |

## Detailed Module Inventory

### Root Modules
| Module | Classes/Functions | Category | Compliance Notes |
| :--- | :--- | :--- | :--- |
| `constants.py` | Various thresholds & types | Utility | Compliant. Centralized constants. |
| `grading_engine.py` | `GradingEngine` | Orchestration | **Red Flag**: Manages concurrency but has direct service dependencies. |
| `resolver.py` | `Resolver`, `GradingLayerContext` | Orchestration | Compliant. Clean routing logic. |

### ai_structured
| Module | Classes/Functions | Category | Compliance Notes |
| :--- | :--- | :--- | :--- |
| `mark_reasoner.py` | `MarkReasoner`, `build_audit_tree` | Domain Logic | **High Compliance**. Pure logic for mark reconciliation. |
| `schemas.py` | `QuestionSchema`, `AlignmentResult` | Domain Logic | Compliant. Pydantic models. |
| `grading_interface.py` | `process_grading_payload` | Orchestration | **Red Flag**: Contains LLM prompting logic mixed with grading flow. |
| `extraction_service.py`| `extract_question_structure` | Orchestration | **Red Flag**: Heavy coupling with OCR and JSON repair logic. |
| `engine.py` | `AiStructuredEngine` | Orchestration | **Red Flag**: Manages DB locks and persistence directly. |

### aws_pipeline
| Module | Classes/Functions | Category | Compliance Notes |
| :--- | :--- | :--- | :--- |
| `textract_client.py` | `start_document_analysis` | Infrastructure | Compliant. Pure AWS wrapper. |
| `s3_storage.py` | `upload_pdf_to_s3` | Infrastructure | Compliant. S3 storage adapter. |
| `engine.py` | `extract_aws_blueprint` | Orchestration | **Red Flag**: Mixed with file-system-like caching logic. |
| `layout_segmentation.py`| `build_span_graph` | Utility | **Red Flag**: Contains significant heuristic "magic numbers". |

### college / college_v3
| Module | Classes/Functions | Category | Compliance Notes |
| :--- | :--- | :--- | :--- |
| `structuring.py` | `structure_packet` | Domain Logic | **High Compliance**. Pure accounting logic. |
| `policy.py` | `enforce_upsc_strict_caps` | Domain Logic | **High Compliance**. Pure business rules. |
| `layout.py` | `detect_page_blocks` | Infrastructure | **Red Flag**: OpenCV logic tightly bound to "college" heuristics. |
| `normalization.py` | `normalize_answer_pages` | Infrastructure | Compliant. Image processing adapter. |
| `recovery.py` | `run_recovery` | Orchestration | **Red Flag**: Threshold-heavy orchestration. |

## Top 5 Red Flags & Refactoring Recommendations

1.  **Logic Duplication (Critical)**: `parse_payload`, `repair_json_payload`, and `_build_question_map` are duplicated across almost all pipeline engines.
    *   **Action**: Move to `app/utils/json_repair.py` and `app/layers/shared/mapping.py`.
2.  **Infrastructure Leakage**: OpenCV and AWS Boto3 calls are embedded in high-level pipeline modules.
    *   **Action**: Strictly isolate to `app/infrastructure/` and inject as dependencies.
3.  **Hardcoded Thresholds**: Sentiment, similarity, and alignment thresholds are scattered across modules.
    *   **Action**: Move all to `app/layers/constants.py` or use a configuration service.
4.  **Domain/Orchestration Confusion**: Modules like `mark_reasoner.py` (Domain) are at the same hierarchy level as `engine.py` (Orchestration).
    *   **Action**: Formalize an `app/domain/` sub-folder for pure business rules.
5.  **Subject-Targeted Logic**: Accounting-specific logic in `college/structuring.py` is hard-linked.
    *   **Action**: Implement a strategy pattern for different subjects (Accounting, Maths, etc.).
