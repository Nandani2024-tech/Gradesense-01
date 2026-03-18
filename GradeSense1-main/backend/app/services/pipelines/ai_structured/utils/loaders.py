from typing import Any, Dict, Tuple
from app.core.exceptions import CustomServiceException
from app.repositories import ExamRepo, SubmissionRepo

exam_repo = ExamRepo()
submission_repo = SubmissionRepo()


async def _load_exam_and_submission(submission_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    submission = await submission_repo.find_one_submission({"submission_id": submission_id}, projection={"_id": 0})
    if not submission:
        raise CustomServiceException("submission_not_found", 500)

    exam = await exam_repo.find_one_exam({"exam_id": submission.get("exam_id")}, projection={"_id": 0})
    if not exam:
        raise CustomServiceException("exam_not_found", 500)

    return exam, submission
