import asyncio
import json
import re
from typing import Dict, List, Any, Optional

from app.services.grading.llm_evaluator import LlmEvaluator
from app.services.grading.answer_normalizer import AnswerNormalizer
from app.services.grading.concept_matcher import ConceptMatcher
from app.services.grading.rubric_builder import RubricBuilder
from app.core.logging_config import logger

class IdentityManager:
    """Standardizes Question IDs from Vision models (e.g., '1', '22a', 'Q 34')."""
    
    @staticmethod
    def normalize_id(qid: str) -> str:
        if not qid:
            return ""
        # Remove whitespace and force upper
        clean = re.sub(r'\s+', '', str(qid)).upper()
        # Handle '1' or '22A' -> 'Q1' or 'Q22A'
        if clean[0].isdigit():
            clean = f"Q{clean}"
        # Standardize sub-question dots (e.g., Q22A -> Q22.A if preferred, 
        # but here we follow the prompt's example: Q22.a)
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
    
    def __init__(self, llm_client: Any = None):
        self.llm_client = llm_client
        self.id_manager = IdentityManager()
        self.evaluator = LlmEvaluator(llm_client)
        self.normalizer = AnswerNormalizer()
        self.matcher = ConceptMatcher()
        self.rubric_builder = RubricBuilder()

    async def _grade_worker(self, question: Dict[str, Any], mapped_packet: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        # logs for this question
        q_logs: List[str] = []
        
        # Support both 'id' (new) and 'question_number' (legacy)
        qid = str(question.get("id") or question.get("question_number") or "Unknown")
        
        # Support both 'marks' (new) and 'max_marks' (legacy)
        max_marks = float(question.get("marks") or question.get("max_marks") or 0.0)
        
        # Support both 'question' (new) and 'question_text'/'rubric' (legacy)
        q_text = question.get("question") or question.get("question_text") or question.get("rubric") or "N/A"
        
        # For semantic evaluation
        model_answer = question.get("model_answer") or question.get("expected_answer") or "Refer to standard definition."
        
        # Identity
        clean_qid = self.id_manager.normalize_id(qid)
        q_logs.append(f"Question {clean_qid}: max_marks={max_marks}")
        
        # Improvement 2: Answer Confidence Gate
        confidence = 1.0
        raw_text = ""
        
        if isinstance(mapped_packet, dict):
            confidence = float(mapped_packet.get("mapping_confidence", 1.0))
            raw_text = mapped_packet.get("combined_text", "")
            q_logs.append(f"mapped_packet raw_text length={len(raw_text)}")
            
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
        
        # previously we short‑circuited low‑confidence packets; now record but continue
        if confidence < 0.2:
            # still very low, keep same treatment as before
            q_logs.append(f"Very low confidence {confidence}, marking needs review")
            return {
                "question_number": qid,
                "question_id": qid,
                "max_marks": max_marks,
                "marks_awarded": 0.0,
                "status": "needs_review",
                "feedback": "Needs Review: Low OCR confidence for answer block.",
                "reason": "low OCR confidence",
                "normalized_answer": None,
                "sub_scores": [],
                "logs": q_logs
            }
        elif confidence < 0.4:
            # caution log but proceed to grading using whatever text was captured
            q_logs.append(f"Low confidence {confidence} (below advisory threshold)")

        # Handle sub-questions
        sub_questions: List[Dict[str, Any]] = question.get("sub_questions") or question.get("subquestions") or []
        sub_scores = []
        total_awarded = 0.0
        final_feedback = []

        if sub_questions:
            # New sub-question logic
            mapped_subanswers = {}
            if isinstance(mapped_packet, dict) and mapped_packet.get("subanswers"):
                for sa in mapped_packet.get("subanswers", []):
                    mapped_subanswers[sa.get("sub_id", "").lower()] = sa
            
            for sq in sub_questions:
                sq_id = str(sq.get("sub_id") or sq.get("id") or "Unknown")
                sq_max_marks = float(sq.get("marks") or sq.get("max_marks") or 0.0)
                sq_text = sq.get("question") or sq.get("question_text") or sq.get("rubric") or f"Part {sq_id}"
                sq_model = sq.get("model_answer") or sq.get("expected_answer") or "Refer to standard definition."
                
                # Find matching student answer
                matched_sa = mapped_subanswers.get(sq_id.lower())
                sq_raw_text = matched_sa.get("combined_text", "") if matched_sa else ""
                
                # If no raw text found, mark as not attempted
                if not sq_raw_text.strip():
                    sub_scores.append({
                        "sub_id": sq_id,
                        "max_marks": sq_max_marks,
                        "obtained_marks": 0.0,
                        "ai_feedback": "Not attempted/found",
                        "annotations": []
                    })
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
                sq_eval_result["score"] = min(sq_deterministic_score, sq_max_marks)
                sq_validated = self.evaluator.validator.validate(sq_eval_result, sq_max_marks)
                sq_awarded = sq_validated["score"]

                total_awarded += sq_awarded
                fb = sq_validated.get("feedback", "")
                if fb:
                    final_feedback.append(f"Part {sq_id}: {fb}")

                sub_scores.append({
                    "sub_id": sq_id,
                    "max_marks": sq_max_marks,
                    "obtained_marks": sq_awarded,
                    "ai_feedback": fb,
                    "annotations": []
                })
            
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

            # 3. Generate Feedback using LLM (Original Score ignored)
            eval_result = await self.evaluator.evaluate(
                question_number=clean_qid,
                question_text=q_text,
                model_answer=model_answer,
                max_marks=max_marks,
                student_answer=clean_answer,
                matched_concepts=match_result["matched_concepts"],
                missing_concepts=match_result["missing_concepts"]
            )
            
            # 4. Override with Deterministic Score & Validate
            eval_result["score"] = min(deterministic_score, max_marks)
            validated = self.evaluator.validator.validate(
                eval_result,
                max_marks
            )

            final_awarded = validated["score"]
            global_feedback = validated.get("feedback", "No feedback provided.")
            global_answer = clean_answer

        # log summary for this question
        q_logs.append(f"Final awarded for {clean_qid}: {final_awarded}/{max_marks}")
        return {
            "question_number": qid,
            "question_id": qid,
            "max_marks": max_marks,
            "obtained_marks": final_awarded,
            "marks_awarded": final_awarded,
            "status": "graded",
            "ai_feedback": global_feedback,
            "feedback": global_feedback,
            "normalized_answer": global_answer,
            "answer_type": "text",
            "sub_scores": sub_scores,
            "logs": q_logs
        }

    async def run_production_grading(self, blueprint: Dict[str, Any], vision_answers: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the production grading pipeline asynchronously."""
        
        # Rule 2: Ingestion & Normalization
        normalized_vision = {
            self.id_manager.normalize_id(k): v 
            for k, v in vision_answers.items() if k
        }
        
        blueprint_questions = blueprint.get("questions", [])
        
        # Rule 7: Parallel Execution Using Asyncio (Fixes ThreadPool sync mismatches)
        tasks = []
        for q in blueprint_questions:
            raw_qid = q.get("id") or q.get("question_number")
            clean_qid = self.id_manager.normalize_id(raw_qid)
            root_id = self.id_manager.get_root_id(clean_qid)
            
            mapped = normalized_vision.get(clean_qid)
            if mapped is None and root_id != clean_qid:
                mapped = normalized_vision.get(root_id)
                
            tasks.append(self._grade_worker(q, mapped))
        
        results = await asyncio.gather(*tasks, return_exceptions=False)
        # Fix array mutability for tuple results
        results_list = list(results)

        # Sort results to match blueprint sequence
        order_map = {str(q.get("id") or q.get("question_number")): i for i, q in enumerate(blueprint_questions)}
        results_list.sort(key=lambda x: order_map.get(str(x.get("question_id")), 999))

        # Rule 9: Dynamic Score Aggregation (Root-ID level)
        main_q_awarded: Dict[str, float] = {}
        main_q_possible: Dict[str, float] = {}
        all_logs: List[str] = []
        
        for res in results_list:
            root_id = self.id_manager.get_root_id(res["question_id"])
            main_q_awarded[root_id] = main_q_awarded.get(root_id, 0.0) + res.get("marks_awarded", 0.0)
            main_q_possible[root_id] = main_q_possible.get(root_id, 0.0) + res.get("max_marks", 0.0)
            # collect logs if present
            if isinstance(res, dict) and res.get("logs"):
                all_logs.extend(res.get("logs"))

        total_awarded = round(sum(main_q_awarded.values()), 2)
        total_possible = round(sum(main_q_possible.values()), 2)

        logger.info(f"Engine totals: awarded={total_awarded}, possible={total_possible}")

        return {
            "total_awarded": total_awarded,
            "total_possible": total_possible,
            "grades": results,
            "logs": all_logs
        }

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
