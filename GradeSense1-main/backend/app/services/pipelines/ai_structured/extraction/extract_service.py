from typing import Any, Dict, List, Tuple, Optional
from app.adapters.interfaces import AbstractLLMService
from app.services.pipelines.ai_extraction_service import extract_question_structure
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger
from app.repositories import ExamRepo, SubmissionRepo
from app.infrastructure.serialization.safe_numeric import to_float

logger = pipeline_logger(__name__)
exam_repo = ExamRepo()
submission_repo = SubmissionRepo()

@with_logging
async def perform_extraction(
    question_paper_images: List[str],
    expected_total_marks: float,
    expected_question_count: int,
    model_name: str = "qwen2.5:latest",
    llm_service: Optional["AbstractLLMService"] = None,
    model_answer_map: Optional[Dict[str, Any]] = None,
    model_answer_images: Optional[List[str]] = None,
    raw_ocr_text: Optional[str] = None,
    max_retries: int = 3,
    paper_id: Optional[str] = None,
    mode: str = "structure",
) -> Tuple[Dict[str, Any], Dict[str, Any], str, int]:
    """Perform question structure extraction with layered pipeline."""
    result = await extract_question_structure(
        question_paper_images=question_paper_images,
        raw_ocr_text=raw_ocr_text,
        expected_total_marks=expected_total_marks,
        expected_question_count=expected_question_count,
        max_retries=max_retries,
        model_name=model_name,
        llm_service=llm_service,
        model_answer_map=model_answer_map,
        model_answer_images=model_answer_images,
        paper_id=paper_id,
        mode=mode,
    )
    return result, result.get("_validation_report") or {}, result.get("_raw_ocr_text", ""), result.get("_retry_count", 0)

@with_logging
async def persist_extracted_structure(
    exam_id: str,
    legacy_questions: List[Dict[str, Any]],
    exam_update_payload: Dict[str, Any],
    next_version: int,
) -> None:
    if legacy_questions:
        from pymongo import UpdateOne
        
        existing_docs = await exam_repo.find_questions({"exam_id": exam_id})
        existing_map = {doc.get("question_uid"): doc for doc in existing_docs if doc.get("question_uid")}
        
        operations = []
        for q in legacy_questions:
            q_uid = q.get("question_uid") or f"q_{exam_id}_{q.get('question_number')}"
            q_doc = {
                **q,
                "exam_id": exam_id,
                "question_id": q.get("question_uuid") or q_uid,
                "question_uid": q_uid
            }
            
            existing_q = existing_map.get(q_uid)
            if existing_q:
                # App-Tree Diff: Preseve Model Answers for nested subquestions
                if existing_q.get("subquestions") and q_doc.get("subquestions"):
                    ex_sq_map = {sq.get("question_uid") or sq.get("label"): sq for sq in existing_q.get("subquestions") if isinstance(sq, dict)}
                    for new_sq in q_doc.get("subquestions"):
                        sq_id = new_sq.get("question_uid") or new_sq.get("label")
                        ex_sq = ex_sq_map.get(sq_id)
                        if ex_sq:
                            if not new_sq.get("model_answer") and ex_sq.get("model_answer"):
                                new_sq["model_answer"] = ex_sq.get("model_answer")
                            if not new_sq.get("rubric") and ex_sq.get("rubric"):
                                new_sq["rubric"] = ex_sq.get("rubric")
                            
                            # Fail-Safe: Preserve marks if new payload is zero but DB is non-zero
                            if to_float(new_sq.get("marks"), 0.0) <= 0 and to_float(ex_sq.get("marks"), 0.0) > 0:
                                new_sq["marks"] = ex_sq.get("marks")
                                new_sq["mark_source"] = ex_sq.get("mark_source") or "preserved"
                
                # App-Tree Diff: Preserve root-level Model Answers, Rubrics and Marks
                if not q_doc.get("model_answer") and existing_q.get("model_answer"):
                    q_doc["model_answer"] = existing_q.get("model_answer")
                if not q_doc.get("rubric") and existing_q.get("rubric"):
                    q_doc["rubric"] = existing_q.get("rubric")
                
                # Fail-Safe: Preserve marks if new payload is zero but DB is non-zero
                if to_float(q_doc.get("marks"), 0.0) <= 0 and to_float(existing_q.get("marks"), 0.0) > 0:
                    q_doc["marks"] = existing_q.get("marks")
                    q_doc["mark_source"] = existing_q.get("mark_source") or "preserved"
                    
            operations.append(
                UpdateOne(
                    {"exam_id": exam_id, "question_uid": q_uid},
                    {"$set": q_doc},
                    upsert=True
                )
            )
            
        if operations:
            await exam_repo.questions_collection.bulk_write(operations)

    await exam_repo.update_exam(exam_id, exam_update_payload)

    realign_update = await submission_repo.update_many_submissions(
        {
            "exam_id": exam_id,
            "$or": [
                {"blueprint_version_used": {"$ne": int(next_version)}},
                {"blueprint_version_used": {"$exists": False}},
            ],
        },
        {
            "$set": {
                "realign_required": True,
            }
        },
    )
    if int(realign_update.modified_count or 0) > 0:
        logger.info(
            "REALIGN_REQUIRED exam_id=%s version=%s affected_submissions=%s",
            exam_id,
            int(next_version),
            int(realign_update.modified_count or 0),
        )
