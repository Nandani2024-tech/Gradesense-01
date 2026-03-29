import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter, defaultdict
from app.core.logging_config import logger
from app.utils.debug_logger import request_id
from app.services.grading.deterministic_engine import evaluate_answer

USE_LLM_GRADING = False
from app.utils.identity_manager import is_valid_question_id
from app.core.exceptions import CustomServiceException
from app.models.submission import QuestionScore, SubQuestionScore, GradingResult
from app.repositories import ExamRepo
from app.services.pipelines.ai_structured.utils.common import _to_float
from app.layers.ai_structured.validation import compute_paper_effective_total
from app.services.pipelines.ai_structured.extraction.utils import _structure_confidence
from app.services.pipelines.ai_structured.grading.alignment_service import ALIGNMENT_COVERAGE_GATE, align_answers
from app.services.pipelines.ai_structured.grading.grading_interface import GRADING_CONTRACT_VERSION, grade_answers_with_contracts
from app.layers.ai_structured.validation import validate_structure
from app.utils.async_utils import safe_gather
from app.services.grading.answer_normalizer import AnswerNormalizer

STRICT_MODE = True

exam_repo = ExamRepo()

# Removed duplicate IdentityManager - use app.utils.identity_manager.normalize_id instead

class GradingEngine:
    """
    Main Orchestrator for the Production Grading Layer.
    Uses concurrency to grade questions in parallel and aggregates totals at the root ID level.

    This engine also collects lightweight logs which can be surfaced to the caller
    for debugging / UI display during grading jobs. Logs are accumulated per
    question and returned as part of the grading result.
    """
    
    def __init__(self, llm_service: Optional[Any] = None):
        self.llm_service = llm_service
        self.normalizer = AnswerNormalizer()


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
        
        # STRICT MODE: Enforce question_uid (SSOT)
        try:
            qid = str(question["question_uid"])
        except KeyError:
            logger.error("STRICT_MODE_VIOLATION: Missing question_uid: %s", question)
            raise CustomServiceException("missing_question_identifier", 500)
        
        # Phase 6: FATAL INVALID MARKS
        raw_marks = question.get("marks") or question.get("max_marks")
        if raw_marks is None or float(raw_marks) <= 0:
            logger.error("STRICT_MODE_VIOLATION: Invalid or missing marks for question %s", qid)
            raise CustomServiceException("invalid_max_marks", 500)
        max_marks = float(raw_marks)
        
        # Support both 'question' (new) and 'question_text'/'rubric' (legacy)
        q_text = question.get("question") or question.get("question_text") or question.get("rubric")
        if not q_text:
            if STRICT_MODE:
                logger.error("STRICT_MODE_VIOLATION: Missing question text for question %s", qid)
                raise CustomServiceException("missing_question_text", 500)
            q_text = "N/A"
        
        # For semantic evaluation
        model_answer = question.get("model_answer") or question.get("expected_answer") or ""
        if not model_answer and STRICT_MODE:
            logger.error("STRICT_MODE_VIOLATION: Missing model_answer for question %s", qid)
            raise CustomServiceException("missing_model_answer", 500)
        
        if not model_answer:
            logger.warning("Missing model_answer for question %s", qid)
        
        # Identity
        clean_qid = qid
        q_logs.append(f"Question {clean_qid}: max_marks={max_marks}")
        
        # Resolve initial raw_text and mapped_subanswers for entry evaluation
        confidence = 1.0
        raw_text = ""
        mapped_subanswers = {}
        
        # Capture canonical key from extraction layer
        canonical_key = question["question_uid"]
        q_logs.append(f"Processing node: {canonical_key}")
        
        if isinstance(mapped_packet, dict):
            # Task 5/8: Check both field names for confidence
            confidence = float(mapped_packet.get("confidence_score") or mapped_packet.get("mapping_confidence", 1.0))
            raw_text = mapped_packet.get("combined_text")
            if raw_text is None:
                 logger.error("STRICT_MODE_VIOLATION: Missing combined_text in mapped_packet for %s", qid)
                 raise CustomServiceException("missing_answer_text", 500)
            raw_text = raw_text or ""
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
        sub_questions: List[Dict[str, Any]] = question.get("sub_questions") or []

        # ✅ PHASE 2.2 DEBUG LOGS
        logger.info("DEBUG_EVALUATING_QUESTION: uid=%s", qid)
        logger.info("DEBUG_ANSWER_PRESENT: %s", mapped_packet is not None)
        logger.info("DEBUG_ANSWER_TEXT: %s", raw_text[:200] if raw_text else None)

        sub_scores = []
        total_awarded = 0.0
        final_feedback = []

        if sub_questions:
            # ✅ STEP 1.1 — ISOLATION TRACKER
            seen_texts = {}
            
            for sq in sub_questions:
                sq_id = str(sq["sub_id"])
                sq_max_marks = float(sq["marks"])
                sq_text = sq.get("question") or sq.get("question_text") or f"Part {sq_id}"
                sq_model = sq["model_answer"]
                
                # Find matching student answer
                matched_sa = mapped_subanswers.get(sq_id.lower())
                sq_raw_text = matched_sa.get("combined_text", "") if matched_sa else ""
                
                # 🛑 ISOLATION RULE 1: FORBID PARENT TEXT INHERITANCE
                trimmed_text = sq_raw_text.strip()
                if not trimmed_text:
                    logger.error(f"STRICT_MODE_VIOLATION: Missing text for subpart {clean_qid}.{sq_id}")
                    raise CustomServiceException("parent_text_inheritance_forbidden", 500)
                
                # 🛑 ISOLATION RULE 2: FORBID TEXT CONTAMINATION (DUPLICATE ANSWERS)
                if trimmed_text in seen_texts:
                    other_id = seen_texts[trimmed_text]
                    logger.error(f"STRICT_MODE_VIOLATION: Text contamination between {sq_id} and {other_id}")
                    raise CustomServiceException("subpart_text_contamination", 500)
                
                seen_texts[trimmed_text] = sq_id

                # Normalization
                sq_norm_result = self.normalizer.normalize(sq_raw_text)
                sq_clean_answer = sq_norm_result["normalized_answer"]

                # TASK 1 & 3 & Phase 6: FATAL ERROR ON MISSING REFERENCE
                if not sq_model:
                    logger.error(f"STRICT_MODE_VIOLATION: Subquestion {clean_qid}.{sq_id} - MISSING MODEL")
                    raise CustomServiceException("missing_model_answer", 500)
                else:
                    # Phase 3: Pure Deterministic Evaluation for Subparts
                    try:
                        sq_awarded = evaluate_answer(
                            model_answer=sq_model,
                            student_answer=sq_clean_answer,
                            max_marks=sq_max_marks
                        )
                        feedback = "Deterministic subpart overlap."
                        detected = []
                        missing = []
                        concept_coverage = 1.0 # Bypassed Phase 3
                        sq_grading_mode = "DET_EVALUATED"
                    except ValueError as ve:
                        logger.error(f"STRICT_MODE_VIOLATION: Subpart evaluation failed: {ve}")
                        raise CustomServiceException(str(ve), 500)

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
            or_group_possible = defaultdict(float) # Task 6: Aggregate possible marks too
            standalone_total = 0.0
            standalone_possible = 0.0
            
            for score in sub_scores:
                ogid = getattr(score, "or_group_id", None) or next((s.get("or_group_id") for s in sub_questions if str(s["sub_id"]) == score.sub_id), None)
                if ogid:
                    or_group_scores[ogid] = max(or_group_scores[ogid], score.obtained_marks)
                    or_group_possible[ogid] = max(or_group_possible[ogid], score.max_marks)
                else:
                    standalone_total += score.obtained_marks
                    standalone_possible += score.max_marks
            
            total_awarded = standalone_total + sum(or_group_scores.values())
            total_possible_agg = standalone_possible + sum(or_group_possible.values())
            
            # Phase 5: STICT SUMMATION VALIDATION
            if abs(total_possible_agg - max_marks) > 0.001:
                logger.error(f"STRICT_MODE_VIOLATION: Subpart max marks sum ({total_possible_agg}) mismatch with parent ({max_marks}) for {qid}")
                raise CustomServiceException("subpart_aggregation_mismatch", 500)
            
            # Phase 5: COMPLETION VALIDATION
            if len(sub_scores) != len(sub_questions):
                logger.error(f"STRICT_MODE_VIOLATION: Missing subpart scores: scored={len(sub_scores)} expected={len(sub_questions)}")
                raise CustomServiceException("missing_subpart_score", 500)
            
            # ✅ STEP 5 — SUMMARY LOG
            logger.info(
                "Question grading input resolution complete",
                extra={
                    "question_id": qid,
                    "subanswers_detected": len(mapped_subanswers) if mapped_subanswers else 0
                }
            )
            
            # Aggregate stats for parent (ENFORCE PARENT-LEVEL ROUNDING)
            final_awarded = round(min(total_awarded, max_marks), 2)
            global_feedback = "\n".join(final_feedback) if final_feedback else "Graded successfully."
            global_answer = raw_text

        else:
            # Legacy monolithic logic
            norm_result = self.normalizer.normalize(raw_text)
            clean_answer = norm_result["normalized_answer"]

            if clean_answer.strip():
                # TASK 1 & 3 & Phase 6: FATAL ERROR ON MISSING REFERENCE
                if not model_answer:
                    logger.error(f"STRICT_MODE_VIOLATION: Question {qid} - MISSING MODEL")
                    raise CustomServiceException("missing_model_answer", 500)
                else:
                    # Phase 3: Pure Deterministic Evaluation
                    try:
                        final_awarded = evaluate_answer(
                            model_answer=model_answer,
                            student_answer=clean_answer,
                            max_marks=max_marks
                        )
                        global_feedback = "Deterministic overlap evaluation."
                        concepts_detected_final = []
                        missing_concepts_final = []
                        coverage_final = 1.0 # Bypassed Phase 3
                        grading_mode_final = "DET_EVALUATED"
                    except ValueError as ve:
                        logger.error(f"STRICT_MODE_VIOLATION: Evaluation failed: {ve}")
                        raise CustomServiceException(str(ve), 500)
            else:
                # Phase 6: FATAL MISSING STUDENT ANSWER
                logger.error(f"STRICT_MODE_VIOLATION: Question {qid} - MISSING STUDENT ANSWER")
                raise CustomServiceException("missing_student_answer", 500)

            # Phase 5: PARENT-LEVEL ROUNDING (Monolithic Case)
            final_awarded = round(final_awarded, 2)

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
                "question_id": qid,
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
            # STRICT MODE: Use question_uid (canonical) only
            uid = q["question_uid"]
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
            elif mapping_status == "MISSING":
                # Valid unattempted question: Award 0.0 without failing the whole job.
                logger.info(f"Question {clean_qid}: Status MISSING. Awarding 0.0 marks (unattempted).")
                
                # Create a future that returns a QuestionScore directly to maintain parallel structure
                async def mock_missing_score(qid, max_m):
                    return QuestionScore(
                        question_number=qid,
                        obtained_marks=0.0,
                        max_marks=max_m,
                        status="not_attempted",
                        ai_feedback="Question missing in submission (unattempted)."
                    )
                tasks.append(mock_missing_score(clean_qid, float(q.get("marks") or 0.0)))
            else:
                # Phase 6: FATAL ALIGNMENT MAPPING FAILURE (AMBIGUOUS or ERROR)
                logger.error(f"STRICT_MODE_VIOLATION: Question {clean_qid} - ALIGNMENT {mapping_status}")
                raise CustomServiceException("alignment_mapping_failure", 500)
        
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
        
        # map questons to their or_group_id using canonical question_uid
        blueprint_or_map = {
             str(q["question_uid"]).strip().lower(): q.get("or_group_id")
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
        
        # Phase 4: Reconcile with SSOT to prevent divergence
        ssot_total = compute_paper_effective_total(blueprint.get("questions") or [])
        if abs(total_possible - ssot_total) > 0.01:
            logger.warning(
                "TOTAL_POSSIBLE_DIVERGENCE predicted=%s ssot=%s",
                total_possible, ssot_total
            )
            total_possible = ssot_total

        logger.info(f"Engine totals: awarded={total_awarded}, possible={total_possible} (ssot={ssot_total})")

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

    derived_total = compute_paper_effective_total(structure.get("questions") or [])
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


