# Grading Engine

## Purpose
This module is responsible for the final grading logic of the AI-structured pipeline. It takes an exam blueprint and a set of aligned student answers, performs normalization, deterministic concept matching, and LLM-based evaluation to produce final scores and feedback.

## Main Entry Point
- **Function/Class**: `GradingEngine.run_production_grading`
- **File**: [grading_engine.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/pipelines/ai_structured/grading/grading_engine.py)

## Submodules
- `alignment_service.py`: Handles visual alignment of answers against the blueprint if not already provided.
- `grading_interface.py`: Defines the contract and helper functions for question-level grading.
- `grading_resolver.py`: Determines the appropriate grading layer/params based on exam metadata.
- `mark_resolver.py`: Resolves visual marks from question paper images to override or validate AI marks.
