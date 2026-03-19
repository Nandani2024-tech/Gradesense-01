from typing import Any, Dict, List, Tuple
from app.services.pipelines.ai_extraction_service import extract_question_structure
from app.services.pipelines.ai_structured.utils.logging import with_logging, pipeline_logger
from app.repositories import ExamRepo, SubmissionRepo

logger = pipeline_logger(__name__)
exam_repo = ExamRepo()
submission_repo = SubmissionRepo()

@with_logging
async def perform_extraction(
    question_paper_images: List[str],
    expected_total_marks: float,
    expected_question_count: int,
    model_name: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, int]:
    return await extract_question_structure(
        question_paper_images=question_paper_images,
        expected_total_marks=expected_total_marks,
        expected_question_count=expected_question_count,
        max_retries=3,
        model_name=model_name,
    )

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
