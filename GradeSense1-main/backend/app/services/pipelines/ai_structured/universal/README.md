# Universal Grading Engine

## Purpose
A flexible, extraction-first pipeline designed for arbitrary exam formats. It uses a continuity resolver to handle fragmented answers and non-standard layouts across different exam types.

## Main Entry Point
- **Function**: `run_universal_pipeline_v2`
- **File**: [universal_engine.py](file:///e:/SSB%20-2/NF/Gradesense-01/GradeSense1-main/backend/app/services/pipelines/ai_structured/universal/universal_engine.py)

## Submodules
- `alignment.py`: Aligns detected answer packets with the question blueprint.
- `continuity.py`: Resolves answer continuity across pages and blocks using hybrid lexical-semantic heuristics.
- `ocr.py`: Specialized OCR block extraction for universal layouts.
- `recovery.py`: Performs post-alignment recovery for missing or low-confidence questions.
