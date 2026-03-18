# 🔍 Hidden Pipeline Detection Report

## 1. Summary

* **Total files scanned**: 45+ (focused on services, adapters, layers, and workers)
* **Files flagged**: 11
* **High-risk files (≥4 signals)**: 5
* **Medium-risk files (2–3 signals)**: 6

---

## 2. 🚨 High-Risk Files (4+ Signals)

### 📂 File: `app/services/pipelines/ai_structured_engine.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Orchestrates a multi-step flow consisting of extraction, alignment, and deterministic grading. Integrates multiple layers (repositories, services, and adapters).
* **Signal B (Responsibility Violations)**: Mixes business logic (grading formulas, score derivations) with direct database state management (`exam_repo.update_exam`).
* **Signal C (Data Mutation Risk)**: Extensively normalizes, reshapes, and validates the `question_structure_v2` object.
* **Signal D (Size & Complexity)**: Even after recent extraction of helpers, the file remains a primary orchestrator with complex async logic.
* **Signal E (Hidden Execution Flow)**: Serves as a gateway for background processing triggered by workers.

**What it appears to be doing:**
Functions as the primary monolithic orchestrator for the AI structured grading pipeline. It coordinates the lifecycle of an AI grading job from initial lock acquisition to final score computation and persistence.

**Potential Risk:** Hidden pipeline orchestration, tight coupling of logic and persistence, and silent schema enforcement.

---

### 📂 File: `app/services/pipelines/aws_blueprint_builder.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Implements a sequential process to build content spans and then structure them into a blueprint.
* **Signal B (Responsibility Violations)**: Contains low-level OCR text parsing heuristics (regex for marks/questions) alongside LLM orchestration.
* **Signal C (Data Mutation Risk)**: Derives question numbers and marks from "best partial structure" fallbacks when AI fails, reshaping OCR output significantly.
* **Signal D (Size & Complexity)**: ~600 lines with numerous internal private helper functions for pattern detection and data cleaning.

**What it appears to be doing:**
Acts as a fallback or specialized blueprint builder for AWS Textract outputs. It performs heavy lifting in cleaning OCR noise and "guessing" question structures to create a valid domain model.

**Potential Risk:** Silent data mutation based on heuristics, mixed responsibility of text processing and domain modeling.

---

### 📂 File: `app/services/pipelines/ai_extraction_service.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Explicitly defines a "layered visual + semantic pipeline" with multiple distinct steps (OCR, Visual Parsing, Semantic, Evaluation).
* **Signal B (Responsibility Violations)**: Orchestrates adapters (`ocr_service`, `llm_service`) and infrastructure steps.
* **Signal C (Data Mutation Risk)**: Modifies and merges semantic structures with visual entities; clips question counts based on expectations.
* **Signal E (Hidden Execution Flow)**: Triggered indirectly by other service engines during the extraction phase.

**What it appears to be doing:**
A service-layer orchestrator specifically for the "AI-first" extraction flow. It manages retries and fallbacks between OCR-based and LLM-based extraction.

**Potential Risk:** Complex execution flow with multiple silent fallbacks that change how data is extracted.

---

### 📂 File: `app/layers/ai_structured/mark_merger.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Manages a multi-pass process (Initial Pass -> Reconciliation -> Redistribution) to merge mark data from disparate sources.
* **Signal C (Data Mutation Risk)**: Specifically designed to reconcile and "trim" or "fill" marks to match header totals. It reshapes the actual score data.
* **Signal D (Size & Complexity)**: ~420 lines with complex set-based logic and graph algorithms (`_build_or_groups`).
* **Signal E (Hidden Execution Flow)**: Operates deep within the "Evaluation Step" of the pipeline, making its effects silent to the top-level route.

**What it appears to be doing:**
A specialized logic layer for reconciling marks. It uses graph-based Union-Find to group questions and applies heuristics to distribute "header marks" across individual questions.

**Potential Risk:** Silent mark redistribution and logic-heavy mutations that are hard to trace from the outside.

---

### 📂 File: `app/layers/ai_structured/structure_repair.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Acts as a "Layer-6 auto-repair engine" in the evaluation pipeline.
* **Signal C (Data Mutation Risk)**: Mutates the structure to fix "numbering explosions", deduplicate subparts, and propagate section pattern marks.
* **Signal D (Size & Complexity)**: ~340 lines with multiple specialized repair strategies.
* **Signal E (Hidden Execution Flow)**: Automatically executes during evaluation to "fix" upstream errors silently.

**What it appears to be doing:**
A self-healing module that tries to correct structural inconsistencies in the extracted blueprint before it reaches the database.

**Potential Risk:** Silent structural modifications that may hide underlying extraction bugs or introduce new ones.

---

### 📂 File: `app/services/pipelines/ai_structured/grading/alignment_service.py`

**Why flagged:**
* **Signal A (Pipeline Behavior)**: Implements a complex multi-stage alignment flow: Batch processing -> LLM Alignment -> OCR Fallback -> Objective Fallback -> Metrics Computation.
* **Signal B (Responsibility Violations)**: Contains low-level OCR regex matching for MCQ answers alongside high-level batching logic.
* **Signal C (Data Mutation Risk)**: Normalizes and reshapes alignment payloads; dynamically adjusts page indices and confidence scores.
* **Signal D (Size & Complexity)**: ~460 lines of dense orchestration and heuristic-based reconciliation.

**What it appears to be doing:**
The primary service for aligning visual answers from a submission to the structured question paper blueprint. It manages batching for LLM efficiency and provides multiple layers of redundancy for MCQ vs written answers.

**Potential Risk:** Hidden pipeline complexity and silent data "filling" from multiple fallback sources.

---

## 3. ⚠️ Medium-Risk Files (2–3 Signals)

### 📂 File: `app/adapters/visual_extractor.py`
* **Signal B (Responsibility Violations)**: Performs heavy entity extraction (questions, subparts, math) from OCR lines, which is highly logic-intensive for an adapter.
* **Signal C (Data Mutation Risk)**: Normalizes labels and parses mark values from raw strings.
* **Signal D (Size & Complexity)**: ~590 lines with custom regex-heavy state machine logic.

### 📂 File: `app/workers/grading_worker.py`
* **Signal A (Pipeline Behavior)**: Triggers a 3-step orchestrator (Grading -> Student ID -> Submission Create).
* **Signal E (Hidden Execution Flow)**: Runs background async processing via semaphores.

### 📂 File: `app/services/maintenance_service.py`
* **Signal B (Responsibility Violations)**: Directly manipulates Job/Task statuses in the DB and triggers re-evaluations.
* **Signal E (Hidden Execution Flow)**: Direct entry point for complex "Repair" and "Cleanup" logic.

### 📂 File: `app/layers/ai_structured/mark_reasoner.py`
* **Signal C (Data Mutation Risk)**: Reshapes raw AI grading outputs into structured `QuestionScore` items.
* **Signal D (Size & Complexity)**: Contains dense mapping and validation logic for marks.

---

## 4. 🧩 Suspicious Patterns Observed

* **Duplicate Normalization**: `_to_float` and `normalize_structure_payload` are imported and called in almost every pipeline and layer file, often with slight Variations in fallback behavior.
* **Scattered Persistence**: Both "Engines" and "Workers" directly call repository update methods, leading to "split persistence" where the state of a job is updated in three different files during one flow.
* **Heuristic Reliance**: Significant "guessing" logic (using Regex and Frequency counts) is embedded deep in the code to handle OCR inaccuracies, especially in `aws_blueprint_builder.py` and `visual_extractor.py`.

---

## 5. 🧭 Entry Points & Flow Clues

* **Entry Point**: `grading_worker.py` -> Triggers `GradingPipelineRunner`.
* **Entry Point**: `ai_structured_engine.py` -> Direct entry point for manual extraction triggers.
* **Indirect Trigger**: Any file calling `auto_extract_questions` (like `maintenance_service.py`) kicks off a hidden multi-step process.

---

## 6. ❗ Edge-Case Flags (Even Weak Doubts)

* `app/infrastructure/serialization/safe_numeric.py`: While technically a utility, it contains complex parsing for "section math" that drives downstream logic.
* `app/layers/ai_structured/mark_sources.py`: Contains centralized confidence scoring that determines whether a mark is accepted or rejected, acting as a silent filter.
