"""Student portal routes — student dashboard, topic drilldown, journey, ask-ai, study materials."""

from typing import Optional, Dict, List
from fastapi import APIRouter, Depends, HTTPException

from app.core.logging_config import logger
from app.deps import get_current_user
from app.models.user import User
from app.services.analytics import (
    extract_topic_from_rubric,
    dashboard_service,
    metrics_service,
    peer_group_service
)

from app.schemas.responses import (
    StudentDashboardResponse,
    TopicDrilldownResponse,
    QuestionDrilldownResponse,
    StudentJourneyResponse,
    ChatResponse,
    StudyMaterialsResponse
)

router = APIRouter(tags=["student_portal"])


# ============== STUDENT DASHBOARD ==============

@router.get("/analytics/student-dashboard", response_model=StudentDashboardResponse)
async def get_student_dashboard(user: User = Depends(get_current_user)) -> StudentDashboardResponse:
    """Get student's personal dashboard analytics"""
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access this")

    analytics_data = await dashboard_service.get_student_dashboard(user)
    return StudentDashboardResponse(**analytics_data)


# ============== DRILL-DOWN ANALYTICS ==============

@router.get("/analytics/drill-down/topic/{topic_name}", response_model=TopicDrilldownResponse)
async def get_topic_drilldown(
    topic_name: str,
    exam_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> TopicDrilldownResponse:
    """Level 2 Drill-Down: Get detailed breakdown of a topic into sub-skills"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    analytics_data = await metrics_service.get_topic_drilldown(topic_name, user.user_id, exam_id, batch_id)
    return TopicDrilldownResponse(**analytics_data)


# ============== QUESTION DRILLDOWN ==============

@router.get("/analytics/drill-down/question", response_model=QuestionDrilldownResponse)
async def get_question_drilldown(
    exam_id: str,
    question_number: int,
    user: User = Depends(get_current_user)
) -> QuestionDrilldownResponse:
    """Level 3 Drill-Down: Get error patterns for a specific question"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    analytics_data = await metrics_service.get_question_drilldown(exam_id, question_number, user.user_id)
    if not analytics_data:
        raise HTTPException(status_code=404, detail="Exam or question not found")
    
    return QuestionDrilldownResponse(**analytics_data)


# ============== STUDENT JOURNEY ==============

@router.get("/analytics/student-journey/{student_id}", response_model=StudentJourneyResponse)
async def get_student_journey(
    student_id: str,
    user: User = Depends(get_current_user)
) -> StudentJourneyResponse:
    """Student Journey View: Complete academic health record with comparisons"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    analytics_data = await dashboard_service.get_student_journey(student_id)
    if not analytics_data:
        raise HTTPException(status_code=404, detail="Student not found")
    
    return StudentJourneyResponse(**analytics_data)


# ============== COMPREHENSIVE AI ANALYTICS ==============

@router.post("/analytics/ask-ai", response_model=ChatResponse)
async def ask_ai_comprehensive(
    request: dict,
    user: User = Depends(get_current_user)
) -> ChatResponse:
    """Comprehensive AI Analytics Assistant"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    query = request.get("query", "").strip()
    exam_id = request.get("exam_id")
    batch_id = request.get("batch_id")

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    logger.info(f"AI Analytics Query from {user.email}: {query}")

    try:
        ai_response = await metrics_service.get_ai_comprehensive_insights(query, user.user_id)
        return ChatResponse(type="text", response=ai_response)
    except Exception as e:
        return ChatResponse(type="error", response=f"Failed to process query: {str(e)}")


# ============== STUDY MATERIALS ==============

@router.get("/study-materials", response_model=StudyMaterialsResponse)
async def get_study_materials(
    subject_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> StudyMaterialsResponse:
    """Get study material recommendations based on weak areas"""
    analytics_data = await dashboard_service.get_study_materials(user.user_id, subject_id)
    return StudyMaterialsResponse(**analytics_data)
