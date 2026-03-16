from app.core.database import db
from app.utils.datetime_utils import _iso_now
from app.constants.layers import (
    BLUEPRINT_MATCH_THRESHOLD,
    STATUS_SUCCESS,
    STATUS_FAILED,
    FILE_TYPE_QUESTION_PAPER,
)

async def _process_strict_visual_exam(exam: dict) -> None:
    exam_id = exam.get("exam_id")
    if not exam_id:
        return

    file_doc = await db.exam_files.find_one(
        {"exam_id": exam_id, "file_type": FILE_TYPE_QUESTION_PAPER},
        {"_id": 0, "strict_visual_blueprint_json": 1, "strict_visual_blueprint_validated": 1},
    )
    if file_doc and file_doc.get("strict_visual_blueprint_json"):
        validated = bool(file_doc.get("strict_visual_blueprint_validated"))
        await db.exams.update_one(
            {"exam_id": exam_id},
            {"$set": {
                "strict_visual_blueprint_status": STATUS_SUCCESS if validated else STATUS_FAILED,
                "strict_visual_blueprint_warning": not validated,
            }},
        )
        return
    
    # ... rest of the function ...
    from app.services.storage.gridfs_helpers import get_exam_question_paper_images
    from app.adapters.llm.blueprint_adapter import (
        STRICT_VISUAL_BLUEPRINT_PROMPT_VERSION,
        run_strict_visual_blueprint_double_pass,
    )

    question_paper_images = await get_exam_question_paper_images(exam_id)
    if not question_paper_images:
        await db.exams.update_one(
            {"exam_id": exam_id},
            {"$set": {
                "strict_visual_blueprint_status": STATUS_FAILED,
                "strict_visual_blueprint_warning": True,
            }},
        )
        return

    result = await run_strict_visual_blueprint_double_pass(question_paper_images)
    payload = result.get("selected_payload")
    valid = bool(result.get("selected_valid"))
    double_match = bool(result.get("double_pass_match"))
    diffs = list(result.get("double_pass_diffs") or [])
    warning = False
    if isinstance(payload, dict) and payload.get("global_mark_consistency_warning"):
        warning = True
    if not double_match:
        warning = True

    await db.exam_files.update_one(
        {"exam_id": exam_id, "file_type": FILE_TYPE_QUESTION_PAPER},
        {"$set": {
            "strict_visual_blueprint_json": payload,
            "strict_visual_blueprint_validated": valid,
            "strict_visual_blueprint_double_pass_match": double_match,
            "strict_visual_blueprint_double_pass_diffs": diffs,
            "strict_visual_blueprint_generated_at": _iso_now(),
            "strict_visual_blueprint_prompt_version": STRICT_VISUAL_BLUEPRINT_PROMPT_VERSION,
        }},
        upsert=True,
    )
    await db.exams.update_one(
        {"exam_id": exam_id},
        {"$set": {
            "strict_visual_blueprint_status": STATUS_SUCCESS if valid else STATUS_FAILED,
            "strict_visual_blueprint_warning": warning,
        }},
    )
