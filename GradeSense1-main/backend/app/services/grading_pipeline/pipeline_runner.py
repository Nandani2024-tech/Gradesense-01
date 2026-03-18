"""Main orchestrator for grading pipeline."""

import asyncio
from typing import Dict, Any, Optional

from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine
from app.core.logging_config import logger

from .config import DEFAULT_TOTAL_POSSIBLE, DEFAULT_TOTAL_AWARDED
from app.services.extraction_pipeline import extract_answers_from_pdf as extract_answers
from app.services.pipelines.ai_structured.grading.grading_engine import IdentityManager
from app.adapters.interfaces import AbstractLLMService, AbstractOCRService


class GradingPipelineRunner:
    """Orchestrator for the full grading pipeline."""

    def __init__(self, llm_service: AbstractLLMService, ocr_service: AbstractOCRService):
        self.llm_service = llm_service
        self.ocr_service = ocr_service

    async def grade_pdf(
        self,
        blueprint: Dict[str, Any],
        pdf_bytes: bytes,
        question_paper_pdf_bytes: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Full grading pipeline for one answer sheet.

        Steps
        -----
        1. PDF → images
        2. images → answer packets
        3. packets → normalized vision_answers
        4. vision_answers → grading_engine
        """
        try:
            # ----------------------------
            # Step 1 & 2 — Extraction Pipeline
            # ----------------------------
            logger.info("GradingPipelineRunner: starting extraction for pdf")
            pipeline_result = await extract_answers(
                pdf_bytes,
                blueprint.get("questions", []),
                self.ocr_service
            )

            # pipeline may return {"packets": {...}}
            packets = pipeline_result.get("packets", pipeline_result)
            logger.info(f"GradingPipelineRunner: extracted {len(packets)} packets")

            # ----------------------------
            # Step 3 — Normalize question IDs
            # ----------------------------
            id_manager = IdentityManager()
            vision_answers = {}

            for qn, pkt in packets.items():
                clean_qn = id_manager.normalize_id(str(qn))
                vision_answers[clean_qn] = pkt

            # ----------------------------
            # Step 4 — Run grading engine
            # ----------------------------
            engine = GradingEngine(llm_service=self.llm_service)

            result = await engine.run_production_grading(
                blueprint=blueprint,
                vision_answers=vision_answers
            )

            # ensure totals exist
            if result.get("total_possible", DEFAULT_TOTAL_POSSIBLE) == DEFAULT_TOTAL_POSSIBLE and result.get("grades"):
                logger.warning("GradingPipelineRunner: total_possible was zero, recomputing from grades")
                total = DEFAULT_TOTAL_POSSIBLE
                for g in result.get("grades", []):
                    total += float(g.get("max_marks", 0))
                result["total_possible"] = total
                
            if result.get("total_awarded", DEFAULT_TOTAL_AWARDED) == DEFAULT_TOTAL_AWARDED and result.get("grades"):
                awarded = DEFAULT_TOTAL_AWARDED
                for g in result.get("grades", []):
                    awarded += float(g.get("marks_awarded", 0))
                result["total_awarded"] = awarded

            logger.info(f"GradingPipelineRunner: result awarded={result.get('total_awarded')} possible={result.get('total_possible')}")
            return result

        except Exception as e:
            logger.error("Grading pipeline error: %s", str(e), exc_info=True)
            raise


__all__ = ["GradingPipelineRunner"]
