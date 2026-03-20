from typing import Any, Dict, List, Optional, Tuple
from app.adapters.interfaces import AbstractLLMService
from app.services.pipelines.ai_extraction_service import extract_question_structure
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger
from app.repositories import ExamRepo, SubmissionRepo

logger = pipeline_logger(__name__)
exam_repo = ExamRepo()
submission_repo = SubmissionRepo()

@with_logging
async def perform_extraction(
    paper_images: List[str],
    expected_total_marks: float,
    expected_question_count: int,
    model_name: str,
    llm_service: AbstractLLMService,
    answer_paper_images: Optional[List[str]] = None,
    model_answer_images: Optional[List[str]] = None,
    extract_student_info: bool = False,
    infer_topics: bool = False,
    subject_name: Optional[str] = None,
    exam_name: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, int]:
    result = await extract_question_structure(
        paper_images=paper_images,
        answer_paper_images=answer_paper_images,
        model_answer_images=model_answer_images,
        expected_total_marks=expected_total_marks,
        expected_question_count=expected_question_count,
        extract_student_info=extract_student_info,
        infer_topics=infer_topics,
        subject_name=subject_name,
        exam_name=exam_name,
        max_retries=3,
        model_name=model_name,
        llm_service=llm_service,
    )
    return result, result.get("_validation_report"), result.get("_raw_ocr_text", ""), result.get("_retry_count", 0)

@with_logging
async def persist_extracted_structure(
    exam_id: str,
    legacy_questions: List[Dict[str, Any]],
    exam_update_payload: Dict[str, Any],
    next_version: int,
) -> None:
    await exam_repo.delete_questions({"exam_id": exam_id})
    if legacy_questions:
        question_docs = []
        for q in legacy_questions:
            q_doc = {
                **q,
                "exam_id": exam_id,
                "question_id": q.get("question_uuid") or f"q_{exam_id}_{q.get('question_number')}",
            }
            question_docs.append(q_doc)
        await exam_repo.insert_questions(question_docs)

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
