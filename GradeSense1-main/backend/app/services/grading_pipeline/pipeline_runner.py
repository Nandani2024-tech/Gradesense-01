"""Main orchestrator for grading pipeline."""

import os
from typing import Dict, Any, Optional

from app.core.logging_config import logger
from .config import DEFAULT_TOTAL_POSSIBLE, DEFAULT_TOTAL_AWARDED

from app.services.pipelines.ai_structured.grading.grading_engine import IdentityManager
from app.adapters.interfaces import AbstractLLMService, AbstractOCRService
from app.utils.debug_logger import write_debug_json, flush_llm_responses

# ❗ Feature flag
USE_LEGACY_PIPELINE = False


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
        """
        try:
            logger.info("GradingPipelineRunner: starting extraction for pdf")

            # ----------------------------
            # 🚨 LEGACY PIPELINE BLOCK
            # ----------------------------
            if not USE_LEGACY_PIPELINE:
                logger.critical(
                    "PIPELINE_RUNNER: Legacy extraction triggered",
                    extra={"blueprint_version": blueprint.get("blueprint_version")}
                )

                environment = os.getenv("ENVIRONMENT", "development")  # ✅ runtime read

                if environment == "development":
                    raise Exception("LEGACY_PIPELINE_BLOCKED")
                else:
                    return {
                        "total_possible": 0,
                        "total_awarded": 0,
                        "grades": [],
                        "status": "failed",
                        "error": "LEGACY_PIPELINE_BLOCKED",
                        "should_store": False 
                    }

            # ----------------------------
            # LEGACY EXTRACTION (only if enabled)
            # ----------------------------
            from app.services.extraction_pipeline import extract_answers_from_pdf as extract_answers

            logger.warning(
                "PIPELINE_RUNNER: Triggering legacy extract_answers for blueprint version %s",
                blueprint.get("blueprint_version")
            )

            pipeline_result = await extract_answers(
                pdf_bytes,
                blueprint.get("questions", []),
                self.ocr_service
            )

            aligned_answers = pipeline_result.get("aligned_answers", [])
            packets = pipeline_result.get("packets", {})

            logger.info(
                f"GradingPipelineRunner: extracted {len(packets)} raw packets, {len(aligned_answers)} aligned"
            )

            # ----------------------------
            # NORMALIZE IDS
            # ----------------------------
            id_manager = IdentityManager()
            vision_answers = {}

            if aligned_answers:
                for row in aligned_answers:
                    qn = row.get("question_id")
                    pkt = row.get("packet")
                    if qn and pkt:
                        clean_qn = id_manager.normalize_id(str(qn))
                        vision_answers[clean_qn] = pkt
            else:
                for qn, pkt in packets.items():
                    clean_qn = id_manager.normalize_id(str(qn))
                    vision_answers[clean_qn] = pkt

            # ----------------------------
            # GRADING ENGINE (LAZY IMPORT)
            # ----------------------------
            from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine

            engine = GradingEngine(llm_service=self.llm_service)

            # ----------------------------
            # DEBUG INPUTS
            # ----------------------------
            try:
                grading_inputs = {}

                for q in blueprint.get("questions", []):
                    q_id = id_manager.normalize_id(
                        str(q.get("id") or q.get("question_number"))
                    )
                    packet = vision_answers.get(q_id, {})

                    text = packet.get("combined_text", "") if isinstance(packet, dict) else packet

                    grading_inputs[q_id] = {
                        "final_student_answer_text": text,
                        "model_answer": q.get("model_answer") or q.get("expected_answer"),
                        "marks_weight": float(q.get("marks") or q.get("max_marks") or 0.0)
                    }

                write_debug_json("06_grading_inputs.json", grading_inputs)

            except Exception:
                pass

            # ----------------------------
            # RUN GRADING
            # ----------------------------
            result = await engine.run_production_grading(
                blueprint=blueprint,
                vision_answers=vision_answers
            )

            # ----------------------------
            # FIX TOTALS
            # ----------------------------
            if result.get("total_possible", DEFAULT_TOTAL_POSSIBLE) == DEFAULT_TOTAL_POSSIBLE:
                total = sum(float(g.get("max_marks", 0)) for g in result.get("grades", []))
                result["total_possible"] = total

            if result.get("total_awarded", DEFAULT_TOTAL_AWARDED) == DEFAULT_TOTAL_AWARDED:
                awarded = sum(float(g.get("marks_awarded", 0)) for g in result.get("grades", []))
                result["total_awarded"] = awarded

            logger.info(
                f"GradingPipelineRunner: final result awarded={result.get('total_awarded')} possible={result.get('total_possible')}"
            )

            # ----------------------------
            # DEBUG OUTPUT
            # ----------------------------
            try:
                final_debug = {
                    "total_awarded": result.get("total_awarded"),
                    "total_possible": result.get("total_possible"),
                }
                write_debug_json("08_final_grades.json", final_debug)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error("Grading pipeline error: %s", str(e), exc_info=True)
            raise


__all__ = ["GradingPipelineRunner"]
