# College Grading Engine

## Purpose
A specialized pipeline (V2) for college-level exams. It focuses on strict reconstruction of answer structures, layout-aware OCR, and robust packet building for answer alignment.

## Main Entry Point
- **Function**: `run_college_pipeline_v2`
- **File**: [college_engine.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/pipelines/ai_structured/college/college_engine.py)

## Submodules
- `blueprint.py`: Assembles the college-specific question blueprint.
- `alignment.py`: Performs packet-to-blueprint alignment using anchor-first logic.
- `packet_builder.py`: Groups OCR blocks into logical answer packets.
- `college_recovery.py`: Implements confidence gates and alignment recovery strategies.
