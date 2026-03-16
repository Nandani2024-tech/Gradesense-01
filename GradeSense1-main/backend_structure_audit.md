# GradeSense Backend Structure Audit (MVP Readiness)

This document provides a comprehensive audit of the GradeSense backend, mapping its structure, pipelines, modularization status, and MVP readiness.

## 1. Folder → File → Purpose Mapping

### `app/layers/` (Domain Logic)
Core business rules and deterministic reasoning engines.
| File | Purpose | Key Classes/Functions | Status |
| :--- | :--- | :--- | :--- |
| `ai_structured/mark_resolver.py` | Deterministic mark calculation based on visual evidence. | `resolve_marks_from_packet` | Working |
| `ai_structured/mark_reasoner.py` | Logic for interpreting mark patterns (OR-groups, section caps). | `reason_over_marks` | Working |
| `ai_structured/engine.py` | Orchestrates the structural grading process. | `grade_images_with_locked_blueprint` | Working |
| `constants.py` | Centralized domain constants (thresholds, regex, timeouts). | N/A | Modularized |
| `resolver.py` | Switches between grading layers (UPSC, College, Universal). | `resolve_grading_layer` | Working |

### `app/adapters/` (Infrastructure & External Services)
Wrappers for external APIs and low-level extraction logic.
| File | Purpose | Key Classes/Functions | Status |
| :--- | :--- | :--- | :--- |
| `ocr_adapter.py` | Interfaces with Vision API for document text detection. | `ocr_pages` | Working |
| `visual_extractor.py` | Extracts visual entities (anchors, marks) from raw OCR lines. | `extract_visual_entities` | Working |
| `llm/` | Adapter for Gemini and Ollama interactions. | `LlmChat`, `send_message` | Working |

### `app/services/` (Orchestration)
Coordinates between layers and adapters to fulfill business use cases.
| File | Purpose | Key Classes/Functions | Status |
| :--- | :--- | :--- | :--- |
| `extraction/auto_extraction.py` | Background extraction of QPs and Model Answers. | `auto_extract_questions` | Working |
| `grading/grading_core.py` | Orchestrates the full AI grading pipeline. | `run_grading_orchestrator` | Working / Partial Refactor |
| `analytics/topic_extractor.py` | Extracts subjects/topics from rubrics for reporting. | `extract_topic_from_rubric` | Working |

### `app/utils/` (Cross-cutting Concerns)
Shared utilities used across various components.
| File | Purpose | Key Classes/Functions | Status |
| :--- | :--- | :--- | :--- |
| `safe_numeric.py` | Robust math expression and numeric parsing. | `parse_section_math_expression` | Working |
| `blueprint.py` | Utilities for structure validation and blueprint locking. | `compute_blueprint_health` | Working |

---

## 2. Core Pipelines

### Pipeline A: OCR → Extraction
**Goal:** Convert document images into structured blueprints (questions, marks, relationships).
1.  **Ingestion:** `uploads.py` receives images/PDFs.
2.  **Processing:** `auto_extraction.py` triggers background jobs.
3.  **OCR:** `ocr_adapter.py` calls the Vision API.
4.  **Visual Extraction:** `visual_extractor.py` identifies question anchors and margin marks.
5.  **Refinement:** `ai_extraction_service.py` (via Gemini) refines the visual blueprint into a final structure.
*   **Status:** Working End-to-End. Supports blueprint locking for stability.

### Pipeline B: Grading → Comparison
**Goal:** Evaluate student submissions against blueprints and model answers.
1.  **Trigger:** `grading.py` initiates a grading job.
2.  **Orchestration:** `grading_core.py` selects the appropriate layer.
3.  **Visual Grounding:** Uses OCR on student papers to find handwritten responses.
4.  **Evaluation:** Gemini (via `engine.py`) compares student text to model answers using structured rubrics.
5.  **Reasoning:** `mark_reasoner.py` and `mark_resolver.py` apply deterministic rules (e.g., best-of-N for OR groups).
*   **Status:** Working End-to-End. Features a fail-safe fallback to legacy logic.

### Pipeline C: Report Generation → Client Output
**Goal:** Aggregate grading results into actionable insights for teachers.
1.  **Dashboard:** `analytics.py` aggregates DB metrics (total exams, avg score).
2.  **Analysis:** Dynamic calculation of topic mastery, class distribution, and "bluff" indices.
3.  **AI Insights:** Gemini generates natural language summaries and practice recommendations.
*   **Status:** Working (Dynamic API responses). No static PDF generation found, but real-time dashboard is robust.

---

## 3. Modularization Status

| Feature | Status | Notes |
| :--- | :--- | :--- |
| **Layer Isolation** | Good | Domain logic (`ai_structured`) is strictly separated from LLM prompts. |
| **Adapter Separation** | Excellent | OCR and Visual Extraction are clearly decoupled from domain reasoning. |
| **Centralized Constants** | Fully Implemented | `app/layers/constants.py` is the single source of truth for thresholds. |
| **Utility Reusability** | High | `safe_numeric` and `blueprint` utils are used globally. |

---

## 4. Checklist for MVP Readiness

- [x] **End-to-End Extraction:** Successfully converts complex UPSC/College QPs into blueprints.
- [x] **Blueprint Stability:** Locking mechanism prevents grading against unstable structures.
- [x] **Deterministic Marking:** OR-groups and Section-caps handled correctly via resolvers.
- [x] **Background Processing:** All heavy OCR/Grading tasks run asynchronously via asyncio.
- [x] **Teacher Dashboard:** Comprehensive analytics for topic mastery and student performance.
- [/] **Testing Coverage:** Core layers have unit tests, but full E2E pipeline tests could be expanded.
- [ ] **Temp File Cleanup:** Ensure local OCR/PDF temp files are strictly cleaned post-processing.
- [x] **Multi-Client Concurrency:** Semaphore implemented in grading to prevent LLM rate limiting.

**Verdict:** The GradeSense backend is **MVP Ready**. The structural refactor has effectively isolated domain logic, making the system scalable and easier to debug.
