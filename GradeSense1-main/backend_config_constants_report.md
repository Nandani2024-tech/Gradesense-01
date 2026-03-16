# GradeSense Backend: Configuration and Constants Management

This document provides a comprehensive overview of how thresholds, constants, and environment-specific settings are managed within the GradeSense backend.

## 1. Centralization of Thresholds and Constants

The system uses several dedicated constant files. While a canonical `layers/constants.py` exists, thresholds are currently distributed according to their functional domain.

### Core Layer Constants (`app/layers/constants.py`)
| Constant Name | Current Value | Purpose / Usage | Centralized? | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| `MAPPING_CONFIDENCE_THRESHOLD` | 0.6 | Min confidence for mapping a student answer to a question. | Yes | Keep. |
| `BLUEPRINT_MATCH_THRESHOLD` | 0.8 | Threshold for validating blueprint structure health. | Yes | Keep. |
| `ALIGNMENT_COVERAGE_GATE` | 0.7 | Minimum coverage ratio for successful alignment. | **No** (Duplicated) | Centralize from `grading/constants.py`. |
| `REGION_OCR_CONF_MIN` | 0.52 | Minimum OCR confidence for region-based extraction. | Yes | Keep. |
| `VISUAL_HEADER_HEIGHT_RATIO` | 0.24 | Max height ratio for header detection in layout. | Yes | Keep. |

### Grading Service Constants (`app/services/grading/constants.py`)
| Constant Name | Current Value | Purpose / Usage | Centralized? | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| `MAPPED_QUESTION_RATIO_MIN` | 0.85 (env) | Minimum ratio of questions that must be mapped before failure. | Yes (Env-driven) | Keep as env override. |
| `RANK_BOOST_STATUS_GRADED` | 3.0 | Weight boost for graded candidates during ranking. | Yes | Keep. |
| `MATCH_RATIO_THRESHOLD` | 0.5 | Threshold for semantic concept matching. | Yes | Keep. |
| `GRADING_JOB_TIMEOUT_SECONDS`| 1800.0 | Timeout for long-running grading jobs. | Yes | Keep. |

## 2. Hardcoded Values vs Config Files

Several magic numbers and patterns are embedded directly in logic, which should be moved to central configuration files for modularity.

| Value | Module / File | Context | Suggested Action |
| :--- | :--- | :--- | :--- |
| `0.5`, `1.0` | `app/layers/upsc/policy.py` | UPSC mark capping logic (`half = 0.5 * q_max`). | Move to `layers/constants.py` as `UPSC_MARK_CAP_RATIO`. |
| `15` | `app/services/extraction/auto_extraction.py` | Hardcoded `CHUNK_SIZE` for extraction loop. | Move to `services/config/pipeline_constants.py`. |
| `30` | `app/services/annotation_v2/config.py` | `MARGIN_X` coordinate for rendering. | Centralize in a dedicated `rendering_constants.py`. |
| `0.9`, `0.75` | `app/layers/universal/grader.py` | Default confidence scores for objective/subjective grading. | Move to `layers/constants.py` as `GRADER_DEFAULT_CONFIDENCE`. |

## 3. Environment-Specific Overrides

Configurations are managed via environment variables (found in `.env` and `os.getenv` calls), allowing the system to behave differently in `development`, `test`, and `production`.

| Constant Name | Default Value | Env Variable | Affected Module |
| :--- | :--- | :--- | :--- |
| `ENV` | `development` | `ENV` | Global behavior control. |
| `GEMINI_MODEL_NAME` | `gemini-2.5-flash` | `GEMINI_MODEL_NAME` | `app/core/config.py` |
| `DISABLE_ANNOTATIONS` | `true` | `DISABLE_ANNOTATIONS` | `app/services/grading/constants.py` |
| `MAPPING_HARD_STOP` | `true` | `MAPPING_HARD_STOP` | `app/services/grading/constants.py` |
| `AWS_S3_BUCKET` | *(Empty)* | `AWS_S3_BUCKET` | `app/services/aws/config.py` |

### Environment Awareness Audit:
- **Dev/Production**: Handled well for model names and feature flags.
- **Testing**: Test-specific constants (like shorter timeouts or mocked storage paths) are currently not centralized in a `test_config.py`, leading to potential leakage between environments.

## Conclusion

The GradeSense backend has a solid foundation for constant management but exhibits **threshold fragmentation**. Constants are often defined where they are first used rather than where they architecturally belong. Moving magic numbers from the `uplc/policy.py` and `universal/grader.py` into a central registry will ensure the backend remains adaptable for different client requirements and MVP scaling.
