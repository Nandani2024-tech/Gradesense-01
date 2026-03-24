# AI Grading System: Zero-Assumption Audit Report

This audit was conducted under strict "zero-assumption" rules. Every finding is backed by direct code tracing and evidence from the `backend/app` directory.

---

## 🏗️ SYSTEM ARCHITECTURE VERDICT

| Metric | Status | Evidence / Observation |
| :--- | :--- | :--- |
| **System Classification** | **Highly Fragmented** | 3+ active pipelines (`ai_structured`, `college_v3`, `aws`) coexist with conflicting logic. |
| **Production Readiness** | **🚨 NOT READY** | Critical SSOT breakage, signature mismatches, and hardcoded "safe exits" that mask failures. |
| **Maintainability** | **Maintenance Nightmare** | Logic is scattered across duplicate files; prompts and schemas are non-unified. |
| **Determinism** | **Partially Deterministic** | Mixing LLM reasoning with hardcoded confidence gates (< 0.2 = 0 marks). |

---

## 🔍 TOP 20 ARCHITECTURAL ISSUES: FINAL STATUS

### 1. Multiple Main Pipelines: ❌ NOT RESOLVED
The system contains three distinct grading pipelines:
- `app/services/pipelines/ai_structured/` (Newest)
- `app/services/pipelines/college_v3/` (Legacy/Active - hardcoded in `ExamService`)
- `app/services/pipelines/aws_blueprint_builder.py` (Unverified/Dead)

### 2. No Real Fallback System: ❌ NOT RESOLVED
`grading/grading_core.py` (legacy) catches exceptions but simply logs them and re-raises/fails because the implementation is "missing" or "incomplete". There is no graceful degradation to a simpler model.

### 3. Trigger-Based Pipeline Selection: ❌ NOT RESOLVED
Pipeline selection is hardcoded in the `grading_worker.py` and `task_worker.py` based on task names or simple flags, rather than a centralized orchestrator assessing paper complexity.

### 4. Parallel Extraction Systems: ❌ NOT RESOLVED
Separate extraction logic exists for `ai_structured` (using Gemini Vision) and `aws_answer_extractor`. These systems do not share state or results.

### 5. Direct LLM Calls Outside Pipeline: ❌ NOT RESOLVED
`universal/embeddings.py` directly instantiates `genai.Client()` and calls the SDK, bypassing any centralized `LlmChat` or `AbstractLLMService` enforcement.

### 6. Data Schema Fragmentation: ❌ NOT RESOLVED
The `Exam` model in `models/exam.py` contains fields for at least three different pipeline attempts (e.g., `question_structure`, `question_structure_v2`, `college_v1_marks`).

### 7. Duplicate Prompt Logic: ❌ NOT RESOLVED
Extraction prompts are duplicated in `ai_structured_prompts.py`, `llm_prompts.py`, and `llm_service.py` with slight variations in JSON requirements.

### 8. Alignment Logic Duplicated: ❌ NOT RESOLVED
Alignment (mapping answers to questions) is implemented separately in `ai_structured/alignment_service.py` and `college_v3/answer_mapping.py`.

### 9. Background Worker Bypasses New System: ⚠️ PARTIALLY RESOLVED
The new `run_grading_orchestrator` is used by `grading_worker.py`, but a legacy `task_worker.py` still processes `strict_visual_exam` tasks using an entirely different flow.

### 10. Fake Fallback (Safe Exits): ❌ NOT RESOLVED
The system uses "Safe Exits" that return empty results instead of failing loudly. 
*Example*: `ai_grader.py` returns `[]` if alignment fails, leading to an "empty" grading result that looks like a success with 0 marks.

### 11. Independent Pipelines Don’t Communicate: ❌ NOT RESOLVED
`ai_structured` and `college_v3` write to different fields in the database and have no shared "Common Data Model" for final grades.

### 12. Signature Mismatch Bugs: ❌ NOT RESOLVED
**Critical Finding**: Two `grading_core.py` files exist with different `run_grading_orchestrator` signatures:
- `services/grading_core.py`: `(exam_id, submission_id, ...)`
- `services/grading/grading_core.py`: `(exam_id, submission_data, ...)`
This leads to runtime `TypeError` if the wrong one is imported.

### 13. Dead Code Still Present: ❌ NOT RESOLVED
Multiple unreferenced files: `background_job.py`, `grade_paper_handler.py`, and the entire `aws_*` pipeline.

### 14. Retry Logic Not Centralized: ❌ NOT RESOLVED
While `infrastructure/concurrency/retry.py` exists, local `try/except` loops with manual counters are scattered in `ai_extraction_service.py` and `grading_worker.py`.

### 15. No Confidence-Based Decision Making: ❌ NOT RESOLVED
Confidence scores are calculated but only used for logging or **hardcoded zeroing of marks** (`GradingEngine.py` line 134: `if confidence < 0.2: return 0.0`). There is no flow to "Flag for Human Review" based on these scores.

### 16. Multiple Output Formats: ❌ NOT RESOLVED
The system produces inconsistent JSON structures depending on which pipeline is used, requiring converters in `adapters/` to normalize them for the UI.

### 17. Blueprint Generation Duplicated: ❌ NOT RESOLVED
Blueprint extraction is handled by 3+ different modules: `ai_structured/engine.py`, `college_v3/question_blueprint.py`, and `extraction/blueprint.py`.

### 18. Performance Shortcuts became Architecture: ❌ NOT RESOLVED
The use of `asyncio.gather(*tasks)` for LLM chunks in `ai_extraction_service.py` is an architectural bottleneck that ignores rate limits and provides no internal queue management.

### 19. No Central Enforcement Layer: ❌ NOT RESOLVED
Entry points (`uploads.py`, `grading.py`) directly call different service layers, bypassing the intended `grading_core.py` SSOT.

### 20. Maintenance Nightmare (Logic Scattering): ❌ NOT RESOLVED
The above 19 points culminate in a system where a single change (e.g., adding a "model_answer" field) requires updates in 10+ files across 3 pipelines.

---

## 🎯 THE "ZERO MARK" ROOT CAUSE (Evidence Found)

The mysterious "0 Marks" produced by the system are caused by **three specific code-level gates**:

1.  **Confidence Gate**: `GradingEngine.py:134`:
    ```python
    if confidence < 0.2:
        return {"marks_awarded": 0.0, "status": "needs_review"}
    ```
    *Observation*: This silently zeros the mark without actually attempting to grade it.

2.  **Empty Alignment Fallback**: `LlmEvaluator.py:74`:
    ```python
    if not student_answer or not str(student_answer).strip():
        return {"score": 0.0, "feedback": "Question not attempted."}
    ```
    *Observation*: If the alignment layer fails to find an answer segment, the evaluator defaults to 0.0 instead of flagging a "Mapping Failure".

3.  **Safe Exit Logic**: `grading/grading_core.py` (broken SSOT):
    Catches exceptions and returns empty lists, forcing the aggregation logic to see "0 questions graded" = "0 total marks".

---

## 🚦 FINAL VERDICT: NOT PRODUCTION READY
The system suffers from **Architectural Fragmentation**. The Phase 3 unification attempt was incomplete, leaving "ghost" pipelines and duplicate core files that contradict each other. 

**Critical Action Required**: Rectify the `grading_core.py` duplication and unify the orchestrator signature before any further feature development.
