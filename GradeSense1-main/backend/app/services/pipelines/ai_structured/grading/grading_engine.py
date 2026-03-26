import asyncio
import json
import re
from typing import Dict, List, Any, Optional

from app.services.grading.llm_evaluator import LlmEvaluator
from app.adapters.interfaces import AbstractLLMService
from app.services.grading.answer_normalizer import AnswerNormalizer
from app.services.grading.concept_matcher import ConceptMatcher
from app.services.grading.rubric_builder import RubricBuilder
from app.core.logging_config import logger

from typing import Tuple
from app.core.exceptions import CustomServiceException
from app.models.submission import QuestionScore, SubQuestionScore, GradingResult
from app.repositories import ExamRepo
from app.services.pipelines.ai_structured.utils.common import _to_float
from app.services.pipelines.ai_structured.extraction.utils import _derive_total_marks, _structure_confidence
from app.services.pipelines.ai_structured.grading.alignment_service import ALIGNMENT_COVERAGE_GATE, align_answers
from app.services.pipelines.ai_structured.grading.grading_interface import GRADING_CONTRACT_VERSION, grade_answers_with_contracts
from app.layers.ai_structured.validation import validate_structure

exam_repo = ExamRepo()

class IdentityManager:
    """Standardizes Question IDs from Vision models (e.g., '1', '22a', 'Q 34')."""
    
    @staticmethod
    def normalize_id(qid: str) -> str:
        if not qid:
            return ""
        # Remove whitespace and force upper for legacy keys, but preserve UIDs if they look special
        s_qid = str(qid).strip()
        if "__q" in s_qid:
            # It's a UID, keep as is (or lower/upper consistently)
            # We'll stick to lowercase for UIDs as that's what build_question_uid uses
            return s_qid.lower()
            
        clean = re.sub(r'\s+', '', s_qid).upper()
        # Handle '1' or '22A' -> 'Q1' or 'Q22A'
        if clean and clean[0].isdigit():
            clean = f"Q{clean}"
        # Regex to insert dot before first letter following numbers
        clean = re.sub(r'(Q\d+)([A-Z])', r'\1.\2', clean)
        return clean

    @staticmethod
    def get_root_id(qid: str) -> str:
        """Extracts parent ID for mark aggregation."""
        return qid.split('.')[0]

class GradingEngine:
    """
    Main Orchestrator for the Production Grading Layer.
    Uses concurrency to grade questions in parallel and aggregates totals at the root ID level.

    This engine also collects lightweight logs which can be surfaced to the caller
    for debugging / UI display during grading jobs. Logs are accumulated per
    question and returned as part of the grading result.
    """
    
    def __init__(self, llm_service: AbstractLLMService = None):
        self.llm_service = llm_service
        self.id_manager = IdentityManager()
        self.evaluator = LlmEvaluator(llm_service)
        self.normalizer = AnswerNormalizer()
        self.matcher = ConceptMatcher()
        self.rubric_builder = RubricBuilder()

    async def _grade_worker(self, question: Dict[str, Any], mapped_packet: Optional[Dict[str, Any]]) -> QuestionScore:
        if not question:
            raise ValueError("invalid_question_object")
        # logs for this question
        q_logs: List[str] = []
        
        # Support both 'question_uid' (SSOT), 'id' (new), 'question_number' (legacy), AND 'number' (AI structured)
        qid = str(question.get("question_uid") or question.get("id") or question.get("question_number") or question.get("number") or "Unknown")
        q_id = qid # For user snippet compatibility
        
        # Support both 'marks' (new) and 'max_marks' (legacy)
        max_marks = float(question.get("marks") or question.get("max_marks") or 0.0)
        
        # Support both 'question' (new) and 'question_text'/'rubric' (legacy)
        q_text = question.get("question") or question.get("question_text") or question.get("rubric") or "N/A"
        
        # For semantic evaluation
        model_answer = question.get("model_answer") or question.get("expected_answer") or "Refer to standard definition."
        
        # Identity
        clean_qid = self.id_manager.normalize_id(qid)
        q_logs.append(f"Question {clean_qid}: max_marks={max_marks}")
        
        # Resolve initial raw_text and mapped_subanswers for entry evaluation
        confidence = 1.0
        raw_text = ""
        mapped_subanswers = {}
        
        if isinstance(mapped_packet, dict):
            confidence = float(mapped_packet.get("mapping_confidence", 1.0))
            raw_text = mapped_packet.get("combined_text", "")
            if mapped_packet.get("subanswers"):
                for sa in mapped_packet.get("subanswers", []):
                    mapped_subanswers[sa.get("sub_id", "").lower()] = sa
            
            if "." in clean_qid and mapped_packet.get("subanswers"):
                sub_id = clean_qid.split(".")[-1].lower()
                for sa in mapped_packet.get("subanswers", []):
                    if sa.get("sub_id", "").lower() == sub_id:
                        raw_text = sa.get("combined_text", "")
                        confidence = float(sa.get("mapping_confidence", confidence))
                        q_logs.append(f"subanswer {sub_id} raw_text length={len(raw_text)}")
                        break

        elif isinstance(mapped_packet, str):
            raw_text = mapped_packet

        # Handle sub-questions
        sub_questions: List[Dict[str, Any]] = question.get("sub_questions") or question.get("subquestions") or []

        # ✅ STEP 0 — ENTRY LOG (PER QUESTION)
        logger.info(
            "Grading question started",
            extra={
                "question_id": q_id,
                "has_subquestions": bool(sub_questions),
                "subquestion_count": len(sub_questions) if sub_questions else 0,
                "has_raw_text": bool(raw_text.strip()),
                "raw_text_length": len(raw_text) if raw_text else 0,
                "subanswers_detected": len(mapped_subanswers) if mapped_subanswers else 0
            }
        )

        # ✅ STEP 1 — INITIALIZE COUNTERS (PER QUESTION)
        fallback_used_count = 0
        empty_subanswers_count = 0
        
        # previously we short‑circuited low‑confidence packets; now record but continue
        if confidence < 0.2:
            # SSOT ENFORCEMENT: Inner layers must raise exceptions on failure
            logger.error(f"Very low confidence {confidence} for question {qid}, raising exception")
            raise ValueError(f"low_ocr_confidence: {confidence}")
        elif confidence < 0.4:
            # caution log but proceed to grading using whatever text was captured
            q_logs.append(f"Low confidence {confidence} (below advisory threshold)")

        sub_scores = []
        total_awarded = 0.0
        final_feedback = []

        if sub_questions:
            # Logic here uses pre-initialized mapped_subanswers
            
            for sq in sub_questions:
                sq_id = str(sq.get("sub_id") or sq.get("id") or "Unknown")
                sq_max_marks = float(sq.get("marks") or sq.get("max_marks") or 0.0)
                sq_text = sq.get("question") or sq.get("question_text") or sq.get("rubric") or f"Part {sq_id}"
                sq_model = sq.get("model_answer") or sq.get("expected_answer") or "Refer to standard definition."
                
                # Find matching student answer
                matched_sa = mapped_subanswers.get(sq_id.lower())
                sq_raw_text = matched_sa.get("combined_text", "") if matched_sa else ""
                
                if matched_sa:
                    logger.info(f"GRADING_INPUT_TEXT sub_id={matched_sa.get('sub_id')} len={len(sq_raw_text)}")

                fallback_used = False

                # ✅ STEP 2 — FIX SUB-QUESTION FALLBACK LOGIC
                # CRITICAL RULE: Only fallback if NO subanswers exist at all
                if not sq_raw_text.strip():
                    if not mapped_subanswers and raw_text.strip():
                        sq_raw_text = raw_text
                        fallback_used = True

                # ✅ STEP 3 — CONTROLLED LOGGING (NO SPAM)
                if fallback_used:
                    fallback_used_count += 1
                    logger.warning(
                        "Fallback used for subquestion",
                        extra={
                            "question_id": q_id,
                            "sub_id": sq_id,
                            "reason": "no_subanswers_detected",
                            "raw_text_length": len(raw_text)
                        }
                    )

                elif not sq_raw_text.strip():
                    empty_subanswers_count += 1
                    logger.info(
                        "Subquestion marked as not attempted",
                        extra={
                            "question_id": q_id,
                            "sub_id": sq_id,
                            "reason": "no_text_found"
                        }
                    )
                
                # If no raw text found, mark as not attempted and continue
                if not sq_raw_text.strip():
                    sub_scores.append(SubQuestionScore(
                        sub_id=sq_id,
                        max_marks=sq_max_marks,
                        obtained_marks=0.0,
                        ai_feedback="No answer provided by student."
                    ))
                    continue

                # Normalization
                sq_norm_result = self.normalizer.normalize(sq_raw_text)
                sq_clean_answer = sq_norm_result["normalized_answer"]

                # Rubric & Concept Match (Deterministic base)
                sq_rubric = self.rubric_builder.build_rubric(sq_text, sq_model, sq_max_marks)
                sq_match = self.matcher.match_concepts(sq_rubric, sq_clean_answer)
                sq_deterministic_score = float(sq_match["score"])

                # LLM Evaluation
                sq_eval_result = await self.evaluator.evaluate(
                    question_number=f"{clean_qid}.{sq_id}",
                    question_text=sq_text,
                    model_answer=sq_model,
                    max_marks=sq_max_marks,
                    student_answer=sq_clean_answer,
                    matched_concepts=sq_match["matched_concepts"],
                    missing_concepts=sq_match["missing_concepts"]
                )
                
                # Apply deterministic score and validate
                # Check for evaluation failure
                if sq_eval_result.get("score") is None:
                    error_msg = sq_eval_result.get("error") or "evaluation_failed"
                    raise ValueError(f"evaluation_failure: question={qid} sub={sq_id} reason={error_msg}")

                # Use the evaluated LLM score capped at max_marks.
                sq_awarded = min(float(sq_eval_result.get("score", 0.0)), sq_max_marks)

                total_awarded += sq_awarded
                fb = sq_eval_result.get("feedback", "")
                if fb:
                    final_feedback.append(f"Part {sq_id}: {fb}")

                sub_scores.append(SubQuestionScore(
                    sub_id=sq_id,
                    max_marks=sq_max_marks,
                    obtained_marks=sq_awarded,
                    ai_feedback=fb
                ))
            
            # ✅ STEP 5 — SUMMARY LOG (PER QUESTION, NOT FUNCTION)
            logger.info(
                "Question grading input resolution complete",
                extra={
                    "question_id": q_id,
                    "total_subquestions": len(sub_questions) if sub_questions else 0,
                    "fallback_used_count": fallback_used_count,
                    "empty_subanswers_count": empty_subanswers_count,
                    "subanswers_detected": len(mapped_subanswers) if mapped_subanswers else 0
                }
            )
            
            # Aggregate stats for parent
            final_awarded = min(total_awarded, max_marks)
            global_feedback = "\n".join(final_feedback) if final_feedback else "Graded successfully."
            global_answer = raw_text

        else:
            # Legacy monolithic logic
            norm_result = self.normalizer.normalize(raw_text)
            clean_answer = norm_result["normalized_answer"]

            # 1. Build Rubric Deterministically
            rubric = self.rubric_builder.build_rubric(
                q_text,
                model_answer,
                max_marks
            )

            # 2. Match Concepts Deterministically
            match_result = self.matcher.match_concepts(
                rubric,
                clean_answer
            )
            deterministic_score = float(match_result["score"])

            # 3. Generate Feedback using LLM
            if clean_answer.strip():
                eval_result = await self.evaluator.evaluate(
                    question_number=clean_qid,
                    question_text=q_text,
                    model_answer=model_answer,
                    max_marks=max_marks,
                    student_answer=clean_answer,
                    matched_concepts=match_result["matched_concepts"],
                    missing_concepts=match_result["missing_concepts"]
                )
                
                # Check for evaluation failure
                if eval_result.get("score") is None:
                    error_msg = eval_result.get("error") or "evaluation_failed"
                    raise ValueError(f"evaluation_failure: question={qid} reason={error_msg}")

                # Use the evaluated LLM score capped at max_marks.
                final_awarded = min(float(eval_result.get("score", 0.0)), max_marks)
                global_feedback = eval_result.get("feedback", "No feedback provided.")
            else:
                # Handle empty answer gracefully
                logger.info(f"Empty answer detected for question {qid}")
                final_awarded = 0.0
                global_feedback = "No answer provided by student."

            global_answer = clean_answer

        # log summary for this question
        q_logs.append(f"Final awarded for {clean_qid}: {final_awarded}/{max_marks}")
        
        return QuestionScore(
            question_number=qid,
            max_marks=max_marks,
            obtained_marks=final_awarded,
            status="graded",
            ai_feedback=global_feedback,
            normalized_answer=global_answer,
            sub_scores=sub_scores
        )

    async def run_production_grading(self, blueprint: Dict[str, Any], vision_answers: Dict[str, Any]) -> GradingResult:
        """Runs the production grading pipeline asynchronously."""
        # ADDED LOGGING START
        exam_id = blueprint.get("exam_id") or "unknown"
        logger.info("[PIPELINE START] AI_GRADING | exam_id=%s | submission_id=N/A", exam_id)
        # ADDED LOGGING END
        
        # ADDED LOGGING START
        logger.info("[STEP START] INITIALIZE_GRADING")
        # ADDED LOGGING END
        # Rule 2: Ingestion & Normalization
        normalized_vision = {
            self.id_manager.normalize_id(k): v 
            for k, v in vision_answers.items() if k
        }
        
        blueprint_questions = blueprint.get("questions", [])
        # ADDED LOGGING START
        logger.info("[STEP SUCCESS] INITIALIZE_GRADING")
        # ADDED LOGGING END
        
        # ADDED LOGGING START
        logger.info("[STEP START] RUN_GRADING")
        # ADDED LOGGING END
        
        # Rule 7: Parallel Execution Using Asyncio (Fixes ThreadPool sync mismatches)
        tasks = []
        for q in blueprint_questions:
            raw_qid = q.get("question_uid") or q.get("id") or q.get("question_number") or q.get("number")
            clean_qid = self.id_manager.normalize_id(raw_qid) if not q.get("question_uid") else str(raw_qid)
            root_id = self.id_manager.get_root_id(clean_qid)
            
            mapped = normalized_vision.get(clean_qid)
            if mapped is None and root_id != clean_qid:
                mapped = normalized_vision.get(root_id)
                
            tasks.append(self._grade_worker(q, mapped))
        
        # return_exceptions=True ensures one failure doesn't crash the whole run
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        results_list: List[QuestionScore] = []
        all_logs: List[str] = []
        
        for i, res in enumerate(raw_results):
            if isinstance(res, Exception):
                q = blueprint_questions[i]
                qid = str(q.get("id") or q.get("question_number") or q.get("number") or "Unknown")
                logger.error(f"Grading failed for question {qid}: {res}", exc_info=True)
                results_list.append(QuestionScore(
                    question_number=qid,
                    max_marks=float(q.get("marks") or q.get("max_marks") or 0),
                    obtained_marks=0.0,
                    status="failed",
                    ai_feedback=f"Grading error: {str(res)}"
                ))
                all_logs.append(f"Execution error for {qid}: {str(res)}")
            else:
                results_list.append(res)
                # Need to manually aggregate logs if needed, but QuestionScore doesn't store them.
                # However, our engine returned them in a dict before.
                # Since we want SCHEMA_ENFORCED, we strictly follow QuestionScore.

        # Rule 9: Dynamic Score Aggregation (Root-ID level)
        main_q_awarded: Dict[str, float] = {}
        main_q_possible: Dict[str, float] = {}
        
        for res in results_list:
            root_id = self.id_manager.get_root_id(res.question_number)
            main_q_awarded[root_id] = main_q_awarded.get(root_id, 0.0) + res.obtained_marks
            main_q_possible[root_id] = main_q_possible.get(root_id, 0.0) + res.max_marks

        total_awarded = round(sum(main_q_awarded.values()), 2)
        total_possible = round(sum(main_q_possible.values()), 2)

        logger.info(f"Engine totals: awarded={total_awarded}, possible={total_possible}")

        # ADDED LOGGING START
        logger.info("[STEP SUCCESS] RUN_GRADING")
        # ADDED LOGGING END
        # ADDED LOGGING START
        logger.info("[PIPELINE END] AI_GRADING")
        # ADDED LOGGING END

        return GradingResult(
            total_awarded=total_awarded,
            total_possible=total_possible,
            grades=results_list,
            logs=all_logs
        )

async def perform_grading(
    exam: Dict[str, Any],
    images: List[str],
    model_answer_text: str,
    structure: Dict[str, Any],
    model_answer_map: Dict[str, Any],
    model_answer_images: List[str],
    question_paper_images: List[str],
    grading_mode: str,
    exam_id: str,
    model_name: str,
    job_id: str,
    PIPELINE_VERSION: str,
    PROMPT_VERSION: str,
) -> Tuple[List[QuestionScore], Dict[str, Any]]:

    derived_total = _derive_total_marks(structure)
    declared_total = _to_float(structure.get("total_marks"), 0.0)
    validation_meta = exam.get("question_structure_validation") or {}
    header_total_marks = _to_float(validation_meta.get("header_total_marks"), 0.0)
    header_total_reliable = bool(validation_meta.get("header_total_reliable"))

    if header_total_reliable and header_total_marks > 0:
        if abs(declared_total - header_total_marks) > 0.5:
            logger.warning(
                "TOTAL_MARKS_HEADER_OVERRIDE exam_id=%s declared=%.2f header=%.2f",
                exam_id, declared_total, header_total_marks,
            )
        structure["total_marks"] = header_total_marks
        structure["effective_total_marks"] = header_total_marks
        if exam_id:
            try:
                await exam_repo.update_exam(
                    exam_id, {"$set": {"total_marks": header_total_marks, "effective_total_marks": header_total_marks}},
                )
            except Exception as exc:
                logger.warning("TOTAL_MARKS_UPDATE_FAILED exam_id=%s error=%s", exam_id, exc)
    elif derived_total > 0 and (declared_total <= 0 or abs(derived_total - declared_total) > 0.5):
        logger.warning(
            "TOTAL_MARKS_MISMATCH exam_id=%s declared=%.2f derived=%.2f",
            exam_id, declared_total, derived_total,
        )
        structure["total_marks"] = derived_total
        structure["effective_total_marks"] = derived_total
        if exam_id:
            try:
                await exam_repo.update_exam(
                    exam_id, {"$set": {"total_marks": derived_total, "effective_total_marks": derived_total}},
                )
            except Exception as exc:
                logger.warning("TOTAL_MARKS_UPDATE_FAILED exam_id=%s error=%s", exam_id, exc)

    validation = validate_structure(structure)
    if not validation.get("is_valid"):
        logger.warning(
            "BLUEPRINT_VALIDATION_WARNING exam_id=%s errors=%s",
            exam_id, validation.get("errors") or [],
        )

    alignment_result = await align_answers(
        submission_id=f"adhoc_{exam_id}",
        question_structure=structure,
        answer_images=images,
        blueprint_signature=str(exam.get("active_structure_hash") or ""),
        model_name=model_name,
        use_cache=False,
    )

    mapping_coverage = _to_float(alignment_result.get("alignment_coverage"), 0.0)
    mapped_ratio = _to_float(alignment_result.get("coverage_ratio"), 0.0)
    unresolved_questions = [
        int(qn) for qn, ok in (alignment_result.get("question_coverage_map") or {}).items()
        if not ok and str(qn).isdigit()
    ]
    if unresolved_questions or (alignment_result.get("unmapped_answers") or []) or (alignment_result.get("duplicate_answers") or []):
        logger.warning(
            "ALIGNMENT_GAP_DETECTED exam_id=%s unresolved=%s unmapped=%s duplicates=%s",
            exam_id, unresolved_questions, len(alignment_result.get("unmapped_answers") or []), len(alignment_result.get("duplicate_answers") or []),
        )
    if mapping_coverage < ALIGNMENT_COVERAGE_GATE:
        logger.warning(
            "PIPELINE_BLOCKED_ALIGNMENT exam_id=%s coverage=%.3f threshold=%.3f",
            exam_id, mapping_coverage, ALIGNMENT_COVERAGE_GATE,
        )
        raise CustomServiceException("alignment_coverage_low", 500)

    grading_result = await grade_answers_with_contracts(
        question_structure=structure,
        alignment_result=alignment_result,
        model_answer_text=model_answer_text,
        model_answer_map=model_answer_map or {},
        answer_images=images,
        model_answer_images=model_answer_images or [],
        question_paper_images=question_paper_images or [],
        grading_mode=grading_mode,
        exam_id=exam_id,
        model_name=model_name,
        job_id=job_id,
    )

    structure_conf = _to_float(exam.get("structure_confidence"), _structure_confidence(structure))
    alignment_conf = _to_float(alignment_result.get("alignment_confidence_score"), 0.0)
    grading_conf = _to_float(grading_result.get("grading_confidence"), 0.0)
    overall_conf = round(min(structure_conf, alignment_conf, grading_conf), 2)

    packet_meta = {
        "pipeline": "ai_structured",
        "mapping_status": "pass",
        "mapped_question_ratio": round(mapped_ratio, 2),
        "mapping_coverage": round(mapping_coverage, 2),
        "unresolved_questions": [int(qn) for qn in unresolved_questions],
        "mapping_fail_reasons": [],
        "packets_generated": int(alignment_result.get("mapped_questions", 0) or 0),
        "subpacket_count": 0,
        "low_confidence_questions": [],
        "consistency_flags": [],
        "grading_reference_mode": "rubric_only",
        "structure_confidence": structure_conf,
        "alignment_confidence": alignment_conf,
        "grading_confidence": grading_conf,
        "overall_confidence": overall_conf,
        "question_coverage_map": alignment_result.get("question_coverage_map", {}),
        "unmapped_answers": alignment_result.get("unmapped_answers", []),
        "duplicate_answers": alignment_result.get("duplicate_answers", []),
        "orphan_pages": alignment_result.get("orphan_pages", []),
        "objective_key_flags": grading_result.get("objective_key_flags", {}),
        "grading_report": grading_result.get("grading_report", {}),
        "blueprint_version_used": int(exam.get("blueprint_version", 0) or 0),
        "grading_contract_version": grading_result.get("grading_contract_version", GRADING_CONTRACT_VERSION),
        "prompt_version": PROMPT_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "model_name": model_name,
    }

    return grading_result.get("question_scores", []), packet_meta


if __name__ == "__main__":
    # Production Test Scenario (Standalone Execution)
    blueprint_data = {
        "questions": [
            {"id": "Q1", "question": "Capital of France?", "marks": 1, "model_answer": "Paris"},
            {"id": "Q2.a", "question": "Define Osmosis", "marks": 2, "model_answer": "Movement of water through semi-permeable membrane"},
            {"id": "Q2.b", "question": "Define Diffusion", "marks": 3, "model_answer": "Movement of particles from high to low concentration"}
        ]
    }
    
    # Simulating a mix of dirty OCR strings and complex mapped packets
    vision_data = {
        "Q1": "Ans: (A) Paris.",
        "Q2A": {
            "mapping_confidence": 0.5, # Should trigger confidence gate bypass
            "combined_text": "Movement of water through... scattered noise"
        },
        "Q2.b": "Movement of particles from high to low concentration"
    }
    
    async def run_test():
        engine = GradingEngine()
        final_report = await engine.run_production_grading(blueprint_data, vision_data)
        print(json.dumps(final_report, indent=2))
        
    asyncio.run(run_test())
