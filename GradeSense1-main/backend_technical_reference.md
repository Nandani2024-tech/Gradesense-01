# GradeSense Backend Technical Reference

This document provides a detailed technical reference of the GradeSense backend, documenting functions, classes, constants, and pipelines for MVP readiness.

## 1. Functions & Methods Reference

### [Module] `app.layers.ai_structured.mark_resolver`
*Purpose: Resolves visual marks and overrides AI marks where evidence exists.*

| Function | Purpose | Inputs | Outputs | Answer Sheet Type |
| :--- | :--- | :--- | :--- | :--- |
| `resolve_visual_marks` | Orchestrates visual mark resolution. | `question_structure`, `images` | `Dict` (Resolved Structure) | All (College/School) |
| `_detect_header_total` | Detects total marks from paper header. | `List[OCRLine]` | `Tuple` (Mark, Evidence, Score, Source) | All |
| `_parse_section_math` | Parses "n x m = total" expressions. | `List[OCRLine]` | `List[Dict]` (Math Blocks) | All |
| `_find_question_anchors`| Locates question numbers on page. | `List[OCRLine]`, `valid_questions` | `List[Dict]` (Anchors) | All |
| `_detect_visual_or_groups`| Detects visual "OR" indicators. | `List[OCRLine]`, `anchors` | `Dict` (OR Mapping) | All |

### [Module] `app.layers.ai_structured.mark_reasoner`
*Purpose: Deterministic mark reasoning and audit tree generation.*

| Function | Purpose | Inputs | Outputs | Answer Sheet Type |
| :--- | :--- | :--- | :--- | :--- |
| `_redistribute_subparts_only`| Evens marks across subparts. | `question` | `bool` (Success) | All |
| `_apply_section_rule_conflicts`| Resolves math rule overlaps. | `rules`, `qnums`, `margin_marks` | `Tuple` (Assignments, Rules) | All |
| `_initial_mark_pass` | First pass of mark assignment. | `qnums`, `base_marks`, `margin/section/instr`| `None` (Updates state) | All |

### [Module] `app.services.grading.grading_applier`
*Purpose: Applies deterministic scoring contract to quality results.*

| Function | Purpose | Inputs | Outputs | Answer Sheet Type |
| :--- | :--- | :--- | :--- | :--- |
| `apply_grading_contract` | Orchestrates contract application. | `contract`, `quality`, `sub_qualities` | `Dict` (Scores/Marks) | All |
| `_rubric_mark` | Calculates mark from quality %. | `quality`, `max_marks`, `fractional_flag` | `float` (Mark) | All |
| `_binary_mark` | Calculates mark for MCQ/Objective. | `quality`, `max_marks` | `float` (0 or Max) | MCQ/Objective |

## 2. Classes & Data Models

### [Module] `app.layers.ai_structured.schemas`
*Responsibilities: Defines Pydantic models for structure, alignment, and grading.*

| Class | Responsibilities | Key Relationships |
| :--- | :--- | :--- |
| `QuestionV2` | Contains metadata for a single question. | Composition: `SubQuestionV2`, `EvidenceRef` |
| `EvidenceRef` | Links data to visual coordinates on a page. | Used by `QuestionV2`, `SubQuestionV2` |
| `QuestionStructureV2`| Represents the entire exam blueprint. | Composition: `QuestionV2`, `SectionMathBlock` |
| `AlignmentResultV2` | Represents results of mapping student answers. | Composition: `AlignedAnswerV2` |

### [Module] `app.services.llm.llm_service.LlmChat`
*Responsibilities: Low-level interface for Gemini LLM interactions.*

- **Methods**:
    - `with_model(provider, model_name)`: Configures the LLM backend.
    - `send_message(message)`: Sends text/image prompt, returns raw response.
    - `send_message_structured(message, response_schema)`: Sends prompt, returns Pydantic-validated object.

## 3. Constants Reference

### [Module] `app.layers.constants`
| Constant | Value | Purpose |
| :--- | :--- | :--- |
| `MARGIN_MARK_CONF_THRESHOLD` | `0.45` | Minimum confidence to accept a margin mark. |
| `VISUAL_HEADER_HEIGHT_RATIO` | `0.15` | Defines the "header" area of the first page. |
| `PRECISION_ROUNDING` | `4` | Standard rounding precision for marks. |

### [Module] `app.services.grading.constants`
| Constant | Value | Purpose |
| :--- | :--- | :--- |
| `COLLEGE_V2_PIPELINE_ENABLED`| `Env-based`| Toggles the enhanced college grading pipeline. |
| `RANK_PENALTY_STATUS_NOT_FOUND`| `-8.0` | Heavy penalty for unmapped answers in ranking. |
| `GRADING_JOB_TIMEOUT_SECONDS` | `1800.0` | 30-minute timeout for background grading. |

## 4. Core Pipeline Flows

### Pipeline A: OCR → Parsing → Blueprinting
1. `ocr_adapter.py`: Ingests images, returns raw `OCRLine` list.
2. `mark_resolver.py`: Detects anchors, margin marks, and math rules.
3. `strict_visual_blueprint.py`: (College V2) Double-pass LLM validation of structure.
4. `auto_extraction.py`: Synthesizes visual evidence and LLM parsing into `QuestionStructureV2`.

### Pipeline B: Grading → Comparison → Reasoning
1. `grading_core.py`: Fetches submission images and blueprint.
2. `llm_evaluator.py`: Grades student answer vs. model answer (Quality scores).
3. `grading_applier.py`: Converts Quality % into Marks based on `aggregation_rule`.
4. `mark_reasoner.py`: Performs final deterministic check and audit tree update.

### Pipeline C: Analytics → Report Generation
1. `analytics.py` (Routes): Aggregates scores from `db.submissions`.
2. `dashboard.py`: Calculates class averages, distribution, and top performers.
3. `topic_extractor.py`: Tags questions with topics using LLM if missing.
4. `bluff-index`: Logic identifies high-length/low-relevance student answers.

## 5. MVP Readiness Status

- [x] **Modular Layers**: Domain logic isolated in `app/layers`.
- [x] **Deterministic Marking**: Logic in `grading_applier.py` ensures consistency.
- [x] **Centralized Constants**: All mapping/confidence thresholds in `constants.py`.
- [x] **Background Processing**: `asyncio` jobs with timeout protection are stable.
- [x] **Data Integrity**: Pydantic v2 used for all cross-service payloads.
- [x] **Auditability**: Audit trees generated for every grading decision.
