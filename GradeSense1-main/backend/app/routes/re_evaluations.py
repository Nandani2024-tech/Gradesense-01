"""Re-evaluation request routes."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.deps import get_current_user
from app.models.user import User
from app.models.reevaluation import ReEvaluationCreate
from app.services.re_evaluations.re_evaluation_service import reevaluation_service
from app.schemas.responses import (
    ReEvaluationBriefResponse, ReEvaluationCreateResponse, MessageResponse
)

router = APIRouter(tags=["re-evaluations"])


@router.get("/re-evaluations", response_model=List[ReEvaluationBriefResponse])
async def get_re_evaluations(user: User = Depends(get_current_user)) -> List[ReEvaluationBriefResponse]:
    """Get re-evaluation requests"""
    requests = await reevaluation_service.get_requests(user)
    return [ReEvaluationBriefResponse(**r) for r in requests]


@router.post("/re-evaluations", response_model=ReEvaluationCreateResponse)
async def create_re_evaluation(
    request: ReEvaluationCreate,
    user: User = Depends(get_current_user)
) -> ReEvaluationCreateResponse:
    """Create re-evaluation request"""
    # The original code used request.questions, my service used question_numbers
    new_request = await reevaluation_service.submit_request(
        request.submission_id, 
        request.questions, 
        request.reason, 
        user
    )

    return ReEvaluationCreateResponse(
        request_id=new_request["request_id"], 
        status=new_request["status"]
    )


@router.put("/re-evaluations/{request_id}", response_model=MessageResponse)
async def update_re_evaluation(
    request_id: str,
    updates: dict,
    user: User = Depends(get_current_user)
) -> MessageResponse:
    """Update re-evaluation request (teacher response)"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can respond")

    await reevaluation_service.update_request_status(request_id, updates, user.user_id)
    return MessageResponse(message="Re-evaluation updated")
