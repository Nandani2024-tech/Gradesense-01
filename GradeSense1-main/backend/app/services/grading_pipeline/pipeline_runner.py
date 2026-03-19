"""Main orchestrator for grading pipeline."""

import asyncio
from typing import Dict, Any, Optional

from app.services.pipelines.ai_structured.grading.grading_engine import GradingEngine
from app.core.logging_config import logger

from .config import DEFAULT_TOTAL_POSSIBLE, DEFAULT_TOTAL_AWARDED
from app.services.extraction_pipeline import extract_answers_from_pdf as extract_answers
from app.services.pipelines.ai_structured.grading.grading_engine import IdentityManager
from app.adapters.interfaces import AbstractLLMService, AbstractOCRService
from app.utils.debug_logger import write_debug_json, flush_llm_responses


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

            # pipeline returns {"aligned_answers": [...], "final_output": [...], "packets": {...}}
            aligned_answers = pipeline_result.get("aligned_answers", [])
            packets = pipeline_result.get("packets", {})
            logger.info(f"GradingPipelineRunner: extracted {len(packets)} raw packets, {len(aligned_answers)} aligned")

            # ----------------------------
            # Step 3 — Normalize question IDs
            # ----------------------------
            id_manager = IdentityManager()
            vision_answers = {}

            # Map from the verified alignment array to avoid losing sequence-fallback packets
            if aligned_answers:
                for row in aligned_answers:
                    qn = row.get("question_id")
                    pkt = row.get("packet")
                    if qn is not None and pkt is not None:
                        clean_qn = id_manager.normalize_id(str(qn))
                        logger.info(f"GradingPipelineRunner: mapping aligned packet {qn} -> normalized ID {clean_qn}")
                        vision_answers[clean_qn] = pkt
            else:
                # Fallback to direct raw packets just in case
                for qn, pkt in packets.items():
                    clean_qn = id_manager.normalize_id(str(qn))
                    vision_answers[clean_qn] = pkt

            # ----------------------------
            # Step 4 — Run grading engine
            # ----------------------------
            engine = GradingEngine(llm_service=self.llm_service)
            
            # Stage 6: PRE-GRADING INPUT DEBUG
            try:
                grading_inputs = {}
                for q in blueprint.get("questions", []):
                    q_id = id_manager.normalize_id(str(q.get("id") or q.get("question_number")))
                    packet = vision_answers.get(q_id, {})
                    text = packet.get("combined_text", "") if isinstance(packet, dict) else packet
                    
                    grading_inputs[q_id] = {
                        "final_student_answer_text": text,
                        "model_answer": q.get("model_answer") or q.get("expected_answer"),
                        "marks_weight": float(q.get("marks") or q.get("max_marks") or 0.0)
                    }
                    for sq in q.get("sub_questions", q.get("subquestions", [])):
                        sq_id = id_manager.normalize_id(str(sq.get("id")))
                        full_sq_id = f"{q_id}.{sq_id}"
                        sq_text = ""
                        if isinstance(packet, dict) and packet.get("subanswers"):
                            for sa in packet["subanswers"]:
                                if sa.get("sub_id", "").lower() == str(sq.get("id")).lower():
                                    sq_text = sa.get("combined_text", "")
                        grading_inputs[full_sq_id] = {
                            "final_student_answer_text": sq_text,
                            "model_answer": sq.get("model_answer") or sq.get("expected_answer"),
                            "marks_weight": float(sq.get("marks") or sq.get("max_marks") or 0.0)
                        }
                write_debug_json("06_grading_inputs.json", grading_inputs)
            except Exception:
                pass

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

            logger.info(f"GradingPipelineRunner: final result awarded={result.get('total_awarded')} possible={result.get('total_possible')}")
            
            # Stage 8: FINAL GRADING OUTPUT DEBUG
            try:
                final_grades_debug = {
                    "per_question": [],
                    "total_marks_awarded": result.get("total_awarded", 0),
                    "max_marks": result.get("total_possible", 0)
                }
                for g in result.get("grades", []):
                    final_grades_debug["per_question"].append({
                        "question_id": g.get("question_id"),
                        "attempted": g.get("marks_awarded", 0) > 0 or g.get("normalized_answer") is not None,
                        "relevant": True,
                        "score": g.get("marks_awarded"),
                        "feedback": g.get("ai_feedback", g.get("feedback"))
                    })
                write_debug_json("08_final_grades.json", final_grades_debug)
            except Exception:
                pass

            # Stage 9: PIPELINE SUMMARY DEBUG
            try:
                llm_calls = flush_llm_responses() # Writes 07_llm_raw.json (Stage 7)
                
                summary = {
                    "total_pages_processed": pipeline_result.get("clean_pages_count", 0),
                    "total_packets_built": len(packets) if packets else 0,
                    "total_aligned_questions": len(aligned_answers) if aligned_answers else 0,
                    "missing_questions_count": len(blueprint.get("questions", [])) - len(aligned_answers),
                    "fallback_usage_count": sum(1 for a in aligned_answers if a.get("aligned_by") == "sequence_fallback"),
                    "total_llm_calls": llm_calls
                }
                write_debug_json("09_summary.json", summary)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error("Grading pipeline error: %s", str(e), exc_info=True)
            raise


__all__ = ["GradingPipelineRunner"]
