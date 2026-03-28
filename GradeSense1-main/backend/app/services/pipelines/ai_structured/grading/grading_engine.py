import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter, defaultdict
from app.services.grading.llm_evaluator import LlmEvaluator
from app.adapters.interfaces import AbstractLLMService
from app.services.grading.answer_normalizer import AnswerNormalizer
from app.services.grading.rubric_builder import RubricBuilder
from app.core.logging_config import logger
from app.utils.debug_logger import request_id
from app.services.grading.deterministic_engine import DeterministicGrader

USE_LLM_GRADING = False
from app.utils.identity_manager import normalize_question_id, is_valid_question_id
from app.core.exceptions import CustomServiceException
from app.models.submission import QuestionScore, SubQuestionScore, GradingResult
from app.repositories import ExamRepo
from app.services.pipelines.ai_structured.utils.common import _to_float
from app.services.pipelines.ai_structured.extraction.utils import _derive_total_marks, _structure_confidence
from app.services.pipelines.ai_structured.grading.alignment_service import ALIGNMENT_COVERAGE_GATE, align_answers
from app.services.pipelines.ai_structured.grading.grading_interface import GRADING_CONTRACT_VERSION, grade_answers_with_contracts
from app.layers.ai_structured.validation import validate_structure
from app.services.pipelines.ai_structured.grading.score_validator import validate_score_justification
from app.services.pipelines.ai_structured.grading.score_band import compute_score_band, enforce_score_band
from app.utils.async_utils import safe_gather

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
        self.evaluator = LlmEvaluator(llm_service)
        self.normalizer = AnswerNormalizer()
        self.rubric_builder = RubricBuilder()
        self.det_grader = DeterministicGrader()

    def _degraded_score(self, answer: str, max_marks: float) -> float:
        """
        Fallback scoring for cases where model_answer or rubric is missing.
        Uses word count and diversity as proxies for answer quality.
        """
        if not answer or not answer.strip():
            return 0.0

        words = answer.split()
        word_count = len(words)

        if word_count < 5:
            base = 0.2
        elif word_count < 15:
            base = 0.4
        elif word_count < 30:
            base = 0.6
        else:
            base = 0.75

        unique_words = len(set(answer.lower().split()))
        diversity_ratio = unique_words / max(word_count, 1)

        if diversity_ratio > 0.6:
            base += 0.1

        base = min(base, 0.85)
        return round(base * max_marks, 2)

    async def _grade_worker(self, question: Dict[str, Any], mapped_packet: Optional[Dict[str, Any]]) -> QuestionScore:
        if not question:
            raise ValueError("invalid_question_object")

        # FIX 2: SAFE DEFAULT INITIALIZATION
        coverage_final = 0.0
        concepts_detected_final = []
        missing_concepts_final = []
        grading_mode_final = "AI_EVALUATED"
        global_feedback = ""
        global_answer = ""

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
        model_answer = question.get("model_answer") or question.get("expected_answer") or ""
        if not model_answer:
            logger.warning("Missing model_answer for question %s", qid)
        
        # Identity
        clean_qid = normalize_question_id(qid)
        q_logs.append(f"Question {clean_qid}: max_marks={max_marks}")
        
        # Resolve initial raw_text and mapped_subanswers for entry evaluation
        confidence = 1.0
        raw_text = ""
        mapped_subanswers = {}
        
        if isinstance(mapped_packet, dict):
            # Task 5/8: Check both field names for confidence
            confidence = float(mapped_packet.get("confidence_score") or mapped_packet.get("mapping_confidence", 1.0))
            raw_text = mapped_packet.get("combined_text", "")
            if mapped_packet.get("subanswers"):
                for sa in mapped_packet.get("subanswers", []):
                    mapped_subanswers[sa.get("sub_id", "").lower()] = sa
            
            if "." in clean_qid and mapped_packet.get("subanswers"):
                sub_id = clean_qid.split(".")[-1].lower()
                for sa in mapped_packet.get("subanswers", []):
                    if sa.get("sub_id", "").lower() == sub_id:
                        raw_text = sa.get("combined_text", "")
                        confidence = float(sa.get("confidence_score") or sa.get("mapping_confidence", confidence))
                        q_logs.append(f"subanswer {sub_id} raw_text length={len(raw_text)}")
                        break

        elif isinstance(mapped_packet, str):
            raw_text = mapped_packet

        # Handle sub-questions
        sub_questions: List[Dict[str, Any]] = question.get("sub_questions") or question.get("subquestions") or []

        # ✅ PHASE 2.2 DEBUG LOGS
        logger.info("DEBUG_EVALUATING_QUESTION: uid=%s", q_id)
        logger.info("DEBUG_ANSWER_PRESENT: %s", mapped_packet is not None)
        logger.info("DEBUG_ANSWER_TEXT: %s", raw_text[:200] if raw_text else None)

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
                sq_model = sq.get("model_answer") or sq.get("expected_answer") or ""
                if not sq_model:
                    logger.warning("Missing model_answer for question %s", f"{clean_qid}.{sq_id}")
                
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

                # Rubric Extraction (For signal only)
                sq_rubric = self.rubric_builder.build_rubric(sq_text, sq_model, sq_max_marks)
                sq_concepts = sq_rubric.get("concepts", [])
                
                # TASK 1 & 3: FALLBACK TO DEGRADED MODE (SUBQUESTION)
                if not sq_model or not sq_concepts:
                    logger.warning(
                        "DEGRADED GRADING ACTIVATED",
                        extra={
                            "question_id": f"{clean_qid}.{sq_id}",
                            "reason": "missing_model_answer_or_concepts"
                        }
                    )
                    sq_awarded = self._degraded_score(sq_clean_answer, sq_max_marks)
                    sq_grading_mode = "DEGRADED_NO_MODEL"
                    concept_coverage = 0.0
                    feedback = "Graded in degraded mode due to missing reference material."
                    detected = []
                    missing = []
                else:
                    # Deterministic Grading Execution (Phase 1)
                    if USE_LLM_GRADING:
                        sq_eval_result = await self.evaluator.evaluate(
                            question_number=f"{clean_qid}.{sq_id}",
                            question_text=sq_text,
                            model_answer=sq_model,
                            max_marks=sq_max_marks,
                            student_answer=sq_clean_answer,
                            matched_concepts=[c["concept"] for c in sq_concepts],
                            missing_concepts=[]
                        )
                    else:
                        sq_eval_result = self.det_grader.grade(
                            student_answer=sq_clean_answer,
                            model_answer=sq_model,
                            rubric=sq.get("rubric", {})
                        )
                    
                    llm_score = float(sq_eval_result.get("score", 0.0))
                    feedback = sq_eval_result.get("feedback", "")
                    detected = sq_eval_result.get("concepts_detected", [])
                    missing = sq_eval_result.get("concepts_missing", [])
                    
                    # Concept Coverage (Step 0 - for logs/fallback)
                    total_c = len(sq_concepts)
                    detected_c = len(detected)
                    concept_coverage = detected_c / total_c if total_c > 0 else 1.0
                    logger.info(f"[CONCEPT] coverage={concept_coverage:.2f} detected={detected_c} missing={len(missing)}")

                    # Validation (Step 2)
                    validation = validate_score_justification(sq_eval_result, sq_clean_answer, sq_max_marks)
                    hallucination_detected = validation.get("hallucination_detected", False)
                    logger.info(f"[VALIDATION] hallucination_detected={hallucination_detected}")

                    sq_grading_mode = "AI_EVALUATED"
                    if hallucination_detected:
                        # Step 3: Fallback
                        logger.warning("[VALIDATION_FAILED] Triggering deterministic fallback")
                        sq_awarded = concept_coverage * sq_max_marks
                        sq_grading_mode = "DETERMINISTIC_FALLBACK"
                        logger.info(f"[FALLBACK] activated coverage={concept_coverage:.2f} score={sq_awarded:.2f}")
                    else:
                        # Step 4: Score Band Clamp
                        min_score, max_score = compute_score_band(concept_coverage, sq_max_marks)
                        sq_awarded = max(min(llm_score, max_score), min_score)
                        logger.info(f"[SCORE_BAND] allowed={min_score:.2f}-{max_score:.2f} given={llm_score:.2f} corrected={sq_awarded:.2f}")

                    # Step 5: Zero Score Protection
                    if concept_coverage > 0.4 and sq_awarded == 0:
                        logger.warning("[ZERO_SCORE_OVERRIDE] Invalid zero score detected")
                        sq_awarded = concept_coverage * sq_max_marks
                        logger.info(f"[ZERO_SCORE_FIXED] new_score={sq_awarded:.2f}")

                # TASK 6: ZERO MARKS PROTECTION (SUBQUESTION)
                if sq_clean_answer.strip() and sq_awarded == 0:
                    sq_awarded = min(1.0, sq_max_marks)

                # Finalize
                total_awarded += sq_awarded
                if feedback:
                    final_feedback.append(f"Part {sq_id}: {feedback}")

                sub_scores.append(SubQuestionScore(
                    sub_id=sq_id,
                    max_marks=sq_max_marks,
                    obtained_marks=sq_awarded,
                    ai_feedback=feedback,
                    concepts_detected=detected,
                    missing_concepts=missing,
                    concept_coverage=concept_coverage,
                    grading_mode=sq_grading_mode,
                    or_group_id=sq.get("or_group_id") # Task 5 persistence
                ))
            
            # Step 5: OR-Aware Subpart Aggregation for Parent
            or_group_scores = defaultdict(float)
            standalone_total = 0.0
            
            for score in sub_scores:
                ogid = getattr(score, "or_group_id", None) or next((s.get("or_group_id") for s in sub_questions if str(s.get("sub_id") or s.get("id")) == score.sub_id), None)
                if ogid:
                    or_group_scores[ogid] = max(or_group_scores[ogid], score.obtained_marks)
                else:
                    standalone_total += score.obtained_marks
            
            total_awarded = standalone_total + sum(or_group_scores.values())
            
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

            # 1. Build Rubric (Signal only)
            rubric = self.rubric_builder.build_rubric(q_text, model_answer, max_marks)
            concepts = rubric.get("concepts", [])

            if clean_answer.strip():
                # TASK 1 & 3: FALLBACK TO DEGRADED MODE (MONOLITHIC)
                if not model_answer or not concepts:
                    logger.warning(
                        "DEGRADED GRADING ACTIVATED",
                        extra={
                            "question_id": qid,
                            "reason": "missing_model_answer_or_concepts"
                        }
                    )
                    final_awarded = self._degraded_score(clean_answer, max_marks)
                    feedback = "Graded in degraded mode due to missing reference material."
                    grading_mode = "DEGRADED_NO_MODEL"
                    detected = []
                    missing = []
                else:
                    # 2. LLM Evaluation (Step 1)
                    if USE_LLM_GRADING:
                        eval_result = await self.evaluator.evaluate(
                            question_number=clean_qid,
                            question_text=q_text,
                            model_answer=model_answer,
                            max_marks=max_marks,
                            student_answer=clean_answer,
                            matched_concepts=[c["concept"] for c in concepts],
                            missing_concepts=[]
                        )
                    else:
                        eval_result = self.det_grader.grade(
                            student_answer=clean_answer,
                            model_answer=model_answer,
                            rubric=question.get("rubric", {})
                        )
                    
                    llm_score = float(eval_result.get("score", 0.0))
                    feedback = eval_result.get("feedback", "No feedback provided.")
                    detected = eval_result.get("concepts_detected", [])
                    missing = eval_result.get("concepts_missing", [])
                    
                    # Concept Coverage (Step 0)
                    total_c = len(concepts)
                    detected_c = len(detected)
                    concept_coverage = detected_c / total_c if total_c > 0 else 1.0
                    logger.info(f"[CONCEPT] coverage={concept_coverage:.2f} detected={detected_c} missing={len(missing)}")

                    # Validation (Step 2)
                    validation = validate_score_justification(eval_result, clean_answer, max_marks)
                    hallucination_detected = validation.get("hallucination_detected", False)
                    logger.info(f"[VALIDATION] hallucination_detected={hallucination_detected}")

                    grading_mode = "AI_EVALUATED"
                    if hallucination_detected:
                        # Step 3: Fallback
                        logger.warning("[VALIDATION_FAILED] Triggering deterministic fallback")
                        final_awarded = concept_coverage * max_marks
                        grading_mode = "DETERMINISTIC_FALLBACK"
                        logger.info(f"[FALLBACK] activated coverage={concept_coverage:.2f} score={final_awarded:.2f}")
                    else:
                        # Step 4: Score Band Clamp
                        min_score, max_score = compute_score_band(concept_coverage, max_marks)
                        final_awarded = max(min(llm_score, max_score), min_score)
                        logger.info(f"[SCORE_BAND] allowed={min_score:.2f}-{max_score:.2f} given={llm_score:.2f} corrected={final_awarded:.2f}")

                    # Step 5: Zero Score Protection
                    if concept_coverage > 0.4 and final_awarded == 0:
                        logger.warning("[ZERO_SCORE_OVERRIDE] Invalid zero score detected")
                        final_awarded = concept_coverage * max_marks
                        logger.info(f"[ZERO_SCORE_FIXED] new_score={final_awarded:.2f}")

                # Finalize result variables
                global_feedback = feedback
                concepts_detected_final = detected
                missing_concepts_final = missing
                # TASK 4: Robust coverage finalization
                coverage_final = concept_coverage if 'concept_coverage' in locals() else 0.0
                grading_mode_final = grading_mode

                # TASK 6: ZERO MARKS PROTECTION (MONOLITHIC)
                if final_awarded == 0:
                    final_awarded = min(1.0, max_marks)

            else:
                # Handle empty answer gracefully
                logger.info(f"Empty answer detected for question {qid}")
                final_awarded = 0.0
                global_feedback = "No answer provided by student."
                concepts_detected_final = []
                missing_concepts_final = [c["concept"] for c in concepts]
                coverage_final = 0.0
                grading_mode_final = "AI_EVALUATED"

            global_answer = clean_answer

        # log summary for this question
        # ✅ PHASE 2.2 DEBUG LOGS
        logger.info("DEBUG_MARKS_ASSIGNED: %s", final_awarded)

        res_obj = QuestionScore(
            question_number=qid,
            max_marks=max_marks,
            obtained_marks=final_awarded,
            status="graded",
            ai_feedback=global_feedback,
            normalized_answer=global_answer,
            sub_scores=sub_scores,
            concepts_detected=concepts_detected_final if not sub_questions else [],
            missing_concepts=missing_concepts_final if not sub_questions else [],
            concept_coverage=coverage_final if not sub_questions else 0.0,
            grading_mode=grading_mode_final if not sub_questions else "AI_EVALUATED"
        )
        
        logger.info(
            "grading_question_end",
            extra={
                "question_id": q_id,
                "request_id": request_id.get(),
                "stage": "grading",
                "status": "success",
                "score": final_awarded
            }
        )
        return res_obj

    async def run_production_grading(self, blueprint: Dict[str, Any], vision_answers: Dict[str, Any]) -> GradingResult:
        """Runs the production grading pipeline asynchronously."""
        # ADDED LOGGING START
        exam_id = blueprint.get("exam_id") or "unknown"
        logger.info(
            "grading_started",
            extra={
                "exam_id": exam_id,
                "request_id": request_id.get(),
                "stage": "grading",
                "status": "start"
            }
        )
        logger.info("[PIPELINE START] AI_GRADING | exam_id=%s | submission_id=N/A", exam_id)
        # ADDED LOGGING END
        
        # ADDED LOGGING START
        logger.info("[STEP START] INITIALIZE_GRADING")
        # ADDED LOGGING END
        # ✅ TASK 2: FIX GRADING ENGINE INPUT
        # Use keys directly without normalization to preserve canonical default_qX format
        normalized_vision = {
            str(k).strip().lower(): v 
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
            # Task 2: Use question_uid (canonical) as primary key
            uid = q.get("question_uid") or q.get("id") or q.get("question_number") or q.get("number")
            clean_qid = str(uid).strip().lower()
            root_id = clean_qid.split('.')[0]
            
            mapped = normalized_vision.get(clean_qid)
            
            # ✅ PHASE 2.3: STRICT CANONICAL KEY
            if mapped is None:
                # Log mismatch for verification guard (will be caught by grading_core as well)
                logger.debug("GradingEngine: No mapping found for canonical key '%s'", clean_qid)
            
            # Task 8: Aggregation Safety & Case-insensitivity
            # If mapping is not VALID (e.g. AMBIGUOUS, MISSING), do not award marks.
            raw_status = (mapped.get("mapping_status") or "VALID") if mapped else "MISSING"
            mapping_status = str(raw_status).upper()
            
            if mapping_status == "VALID":
                tasks.append(self._grade_worker(q, mapped))
            else:
                # Store a dummy score for non-valid mapping to keep indices aligned for raw_results
                async def mock_failed_mapping():
                    return QuestionScore(
                        question_number=clean_qid,
                        max_marks=float(q.get("marks") or q.get("max_marks") or 0.0),
                        obtained_marks=0.0,
                        status="needs_review",
                        ai_feedback=f"Aggregation safety: Mapping is {mapping_status}. Manual review required."
                    )
                tasks.append(mock_failed_mapping())
        
        # return_exceptions=True was previously used, now replaced by safe_gather
        results_list = await safe_gather(tasks)
        all_logs: List[str] = []
        
        # results_list now contains QuestionScore objects directly as exceptions are raised by safe_gather
                # Need to manually aggregate logs if needed, but QuestionScore doesn't store them.
                # However, our engine returned them in a dict before.
                # Since we want SCHEMA_ENFORCED, we strictly follow QuestionScore.

        # Rule 9: OR-Aware Dynamic Score Aggregation (Step 5)
        # 1. Group results by OR group
        or_group_awarded = defaultdict(float)
        or_group_possible = defaultdict(float)
        standalone_awarded = 0.0
        standalone_possible = 0.0
        
        main_q_awarded: Dict[str, float] = {}
        main_q_possible: Dict[str, float] = {}
        
        # We need to map questons to their or_group_id from the blueprint
        blueprint_or_map = {
             str(q.get("question_uid") or q.get("id") or q.get("question_number") or q.get("number")).strip().lower(): q.get("or_group_id")
             for q in blueprint_questions
        }

        for res in results_list:
            qid = str(res.question_number).strip().lower()
            ogid = blueprint_or_map.get(qid)
            
            if ogid:
                or_group_awarded[ogid] = max(or_group_awarded[ogid], res.obtained_marks)
                or_group_possible[ogid] = max(or_group_possible[ogid], res.max_marks)
            else:
                standalone_awarded += res.obtained_marks
                standalone_possible += res.max_marks
                
            # Legacy root-id level aggregation for display/audit
            root_id = qid.split('.')[0]
            main_q_awarded[root_id] = main_q_awarded.get(root_id, 0.0) + res.obtained_marks
            main_q_possible[root_id] = main_q_possible.get(root_id, 0.0) + res.max_marks

        total_awarded = standalone_awarded + sum(or_group_awarded.values())
        total_possible = standalone_possible + sum(or_group_possible.values())
        
        # Task 2: Accumulate totals
        all_logs.append(f"[AGGREGATION] standalone_awarded={standalone_awarded:.2f} or_groups={len(or_group_awarded)}")
        for ogid in or_group_awarded:
            all_logs.append(f"[AGGREGATION_OR] group={ogid} → awarded={or_group_awarded[ogid]:.2f} max={or_group_possible[ogid]:.2f}")

        # Final rounding for persistence safety
        total_awarded = float(f"{total_awarded:.2f}")
        total_possible = float(f"{total_possible:.2f}")

        # Task 6: Final sanity log (including normalization if target exists)
        target_total = float(blueprint.get("total_marks") or total_possible)
        normalized_score = (total_awarded / total_possible * target_total) if total_possible > 0 else 0.0
        
        check_msg = f"[FINAL SCORE CHECK] sum_of_questions={total_awarded} total_possible={total_possible}"
        if abs(target_total - total_possible) > 0.01:
            check_msg += f" normalized={normalized_score:.2f}/{target_total:.2f}"
            
        logger.info(check_msg)
        all_logs.append(check_msg)

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
