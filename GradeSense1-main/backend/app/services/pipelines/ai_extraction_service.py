"""AI-first question structure extraction (image-first, OCR-supported)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import logger
from app.infrastructure.serialization.safe_numeric import safe_float, safe_int
from app.infrastructure.concurrency.retry import RetryExhaustedError, run_with_retry
from app.layers.ai_structured.validation import normalize_structure_payload
from app.adapters.visual_extractor import extract_visual_entities
from app.services.pipelines.steps import ocr_step, parse_step, evaluate_step
from app.infrastructure.serialization.safe_numeric import safe_float as _to_float, safe_int as _to_int
from app.adapters.interfaces import AbstractLLMService, AbstractOCRService


class AIExtractionOrchestrator:
    """Orchestrator for AI-first question structure extraction."""

    def __init__(self, llm_service: AbstractLLMService, ocr_service: AbstractOCRService):
        self.llm_service = llm_service
        self.ocr_service = ocr_service

    async def extract_question_structure(
        self,
        *,
        question_paper_images: List[str],
        raw_ocr_text: Optional[str] = None,
        expected_total_marks: Optional[float] = None,
        expected_question_count: Optional[int] = None,
        max_retries: int = 3,
        model_name: str = "qwen2.5:latest",
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str, int]:
        """Extract question structure with layered visual+semantic pipeline."""
        logger.info("[PIPELINE START] AIExtractionOrchestrator | exam_id=N/A | submission_id=N/A")

        if not question_paper_images:
            raise ValueError("question_paper_images_required")

        logger.info("[STEP START] OCR_EXTRACTION")
        if raw_ocr_text is None:
            raw_ocr_text = await ocr_step.build_raw_ocr_text(question_paper_images, self.ocr_service)
        logger.info("[STEP SUCCESS] OCR_EXTRACTION")

        logger.info("[PIPELINE] PARSE START")
        # 1. Visual Extraction
        logger.info("[STEP START] VISUAL_PARSING")
        visual_entities: Dict[str, Any]
        try:
            visual_entities = await parse_step.extract_visual_entities_pipeline(
                question_paper_images, model_name, self.llm_service
            )
            if not any(visual_entities.get(k) for k in ("questions", "section_math", "margin_marks", "or_connectors")):
                raise RuntimeError("empty_visual_payload")
        except Exception as exc:
            logger.warning("VISUAL_ENTITIES_FAILED error=%s", exc)
            try:
                # This calling extract_visual_entities might need refactoring too if it uses infra directly
                visual_entities = extract_visual_entities(question_paper_images, force_ocr_fallback=True)
            except Exception as exc2:
                logger.info("[FALLBACK TRIGGERED] VISUAL_OCR_FALLBACK")
                logger.warning("VISUAL_OCR_FALLBACK_FAILED error=%s", exc2)
                visual_entities = {
                    "questions": [],
                    "subparts": [],
                    "margin_marks": [],
                    "section_math": [],
                    "or_connectors": [],
                    "headers": [],
                    "header_total": None,
                }

        logger.info(
            "VISUAL_EVIDENCE_CONF questions=%s subparts=%s margin_marks=%s section_math=%s or_connectors=%s headers=%s avg_q=%.3f avg_sp=%.3f avg_mm=%.3f avg_sm=%.3f avg_or=%.3f avg_hd=%.3f",
            len((visual_entities or {}).get("questions") or []),
            len((visual_entities or {}).get("subparts") or []),
            len((visual_entities or {}).get("margin_marks") or []),
            len((visual_entities or {}).get("section_math") or []),
            len((visual_entities or {}).get("or_connectors") or []),
            len((visual_entities or {}).get("headers") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("questions") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("subparts") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("margin_marks") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("section_math") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("or_connectors") or []),
            evaluate_step.calculate_average_confidence((visual_entities or {}).get("headers") or []),
        )

        # 2. Semantic Extraction
        logger.info("[STEP START] SEMANTIC_EXTRACTION")
        prompt_extra_rules: List[str] = []
        expected_count = _to_int(expected_question_count, 0)
        if expected_count > 0:
            prompt_extra_rules.append(
                f"Expected question count = {expected_count}. Do not output question numbers outside 1..{expected_count}."
            )
        prompt_total_marks = None
        if expected_total_marks is not None and _to_float(expected_total_marks, 0.0) > 0:
            val_total = float(_to_float(expected_total_marks, 0.0))
            prompt_total_marks = float(round(val_total, 4))
        else:
            visual_header = (visual_entities or {}).get("header_total")
            if isinstance(visual_header, dict) and visual_header.get("reliable") and _to_float(visual_header.get("marks"), 0.0) > 0:
                val_header = float(_to_float(visual_header.get("marks"), 0.0))
                prompt_total_marks = float(round(val_header, 4))
        if prompt_total_marks is not None:
            prompt_extra_rules.append(
                f"Expected total marks = {prompt_total_marks}. Use only as consistency reference; do not assign marks."
            )

        retry_count = 0
        stage2_structure: Dict[str, Any]
        try:
            retry_result = await run_with_retry(
                name="STRUCTURE_EXTRACTION",
                max_attempts=max_retries,
                operation=lambda _attempt: parse_step.extract_semantic_structure_pipeline(
                    question_paper_images, raw_ocr_text, prompt_extra_rules, self.llm_service
                ),
            )
            stage2_structure = retry_result.value
            retry_count = retry_result.attempts - 1
        except RetryExhaustedError as exc:
            logger.error("[STEP FAILED] SEMANTIC_EXTRACTION | error=%s", exc)
            logger.error("STRUCTURE_EXTRACTION_FAILED reason=%s", exc)
            stage2_structure = {"questions": [], "section_math_blocks": [], "total_questions": 0, "total_marks": 0.0}
            retry_count = max_retries

        if not (stage2_structure.get("questions") or []):
            stage2_structure = parse_step.semantic_structure_from_visual_entities(visual_entities)

        visual_entities = parse_step.merge_semantic_with_visual_entities(stage2_structure, visual_entities)
        stage2_structure, visual_entities = parse_step.clip_to_expected_question_count(
            stage2_structure,
            visual_entities,
            expected_question_count,
        )
        logger.info("[STEP SUCCESS] SEMANTIC_EXTRACTION")
        logger.info("[STEP SUCCESS] VISUAL_PARSING")

        # 3. Anchor Merging
        logger.info("[STEP START] PIPELINE_EVALUATION")
        try:
            ocr_anchors = ocr_step.extract_ocr_question_anchors(question_paper_images, self.ocr_service)
        except Exception as exc:
            logger.warning("OCR_ANCHOR_EXTRACTION_FAILED error=%s", exc)
            ocr_anchors = []
        try:
            structured_anchors = evaluate_step.extract_structured_question_anchors(stage2_structure)
        except Exception as exc:
            logger.warning("STRUCTURED_ANCHOR_EXTRACTION_FAILED error=%s", exc)
            structured_anchors = []
        merged_anchors = evaluate_step.merge_question_anchors(
            list((visual_entities or {}).get("questions") or []),
            ocr_anchors,
            structured_anchors,
        )
        if expected_count > 0:
            merged_anchors = [row for row in merged_anchors if 1 <= _to_int(row.get("number"), 0) <= expected_count]
        visual_entities = dict(visual_entities or {})
        visual_entities["questions"] = merged_anchors

        # 4. Header Marks
        visual_header = (visual_entities or {}).get("header_total") if isinstance(visual_entities, dict) else None
        if isinstance(visual_header, dict) and safe_float(visual_header.get("marks"), 0.0) > 0:
            val_m: float = float(safe_float(visual_header.get("marks"), 0.0))
            header_total_marks = float(round(val_m, 4))
            header_total_reliable = bool(visual_header.get("reliable"))
            header_total_conf = safe_float(visual_header.get("confidence"), 0.0)
            header_total_source = str(visual_header.get("source") or "visual_header")
        else:
            header_total_marks, header_total_reliable, header_total_conf, header_total_source = ocr_step.extract_header_total_from_images(
                question_paper_images, self.ocr_service
            )
            if not header_total_marks:
                header_total_marks, header_total_reliable, header_total_conf, header_total_source = ocr_step.extract_header_total_hint(
                    raw_ocr_text
                )

        # 5. Evaluation Pipeline
        structure, validation_report, retry_count = await evaluate_step.run_evaluation_pipeline(
            structure=stage2_structure,
            visual_entities=visual_entities,
            header_total_marks=header_total_marks,
            header_total_reliable=header_total_reliable,
            header_total_conf=header_total_conf,
            header_total_source=header_total_source,
            expected_question_count=expected_question_count,
            raw_ocr_text=raw_ocr_text,
            question_paper_images=question_paper_images,
            retry_count=retry_count,
            llm_service=self.llm_service,
        )
        logger.info("[STEP SUCCESS] PIPELINE_EVALUATION")

        final_ocr_text: str = str(raw_ocr_text) if raw_ocr_text is not None else ""
        logger.info("[PIPELINE END] AIExtractionOrchestrator")
        return structure, validation_report, final_ocr_text, int(retry_count)


__all__ = ["AIExtractionOrchestrator"]
