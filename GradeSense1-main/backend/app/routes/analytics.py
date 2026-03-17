"""Analytics routes — teacher dashboard, class reports, topic mastery, insights, etc."""

from typing import Optional, List, Union
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user
from app.models.user import User
from app.models.analytics import NaturalLanguageQuery
from app.services.analytics.analytics_service import analytics_service
from app.services.analytics.insights_service import insights_service
from app.services.analytics.reporting_service import reporting_service

from app.schemas.responses import (
    DashboardAnalyticsResponse,
    ClassReportResponse,
    ClassInsightsResponse,
    MisconceptionsResponse,
    TopicMasteryResponse,
    StudentDeepDiveResponse,
    ReviewPacketResponse,
    BluffIndexResponse,
    SyllabusCoverageResponse,
    PeerGroupSuggestionsResponse,
    AskDataResponse,
    ClassSnapshotResponse,
    ActionableStatsResponse,
    MessageResponse
)

router = APIRouter(tags=["analytics"])


# ============== DASHBOARD ==============

@router.get("/analytics/dashboard", response_model=DashboardAnalyticsResponse)
async def get_dashboard_analytics(user: User = Depends(get_current_user)) -> DashboardAnalyticsResponse:
    """Get dashboard analytics for teacher"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await analytics_service.get_dashboard_analytics(user.user_id)
    return DashboardAnalyticsResponse(**data)


# ============== CLASS REPORT ==============

@router.get("/analytics/class-report", response_model=ClassReportResponse)
async def get_class_report(
    batch_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    exam_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> ClassReportResponse:
    """Get class report analytics"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await analytics_service.get_class_report(
        user.user_id, batch_id, subject_id, exam_id
    )
    return ClassReportResponse(**data)


# ============== INSIGHTS ==============

@router.get("/analytics/insights", response_model=ClassInsightsResponse)
async def get_class_insights(
    exam_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> ClassInsightsResponse:
    """Get AI-generated class insights"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_class_insights(user.user_id, exam_id)
    return ClassInsightsResponse(**data)


# ============== MISCONCEPTIONS ==============

@router.get("/analytics/misconceptions", response_model=MisconceptionsResponse)
async def get_misconceptions_analysis(
    exam_id: str,
    user: User = Depends(get_current_user)
) -> MisconceptionsResponse:
    """AI-powered analysis of common misconceptions and why students fail"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_misconceptions_analysis(user.user_id, exam_id)
    return MisconceptionsResponse(**data)


# ============== TOPIC MASTERY ==============
@router.get("/analytics/topic-mastery", response_model=TopicMasteryResponse)
async def get_topic_mastery(
    exam_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> TopicMasteryResponse:
    """Get topic-based mastery heatmap data"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_topic_mastery(user.user_id, exam_id, batch_id)
    return TopicMasteryResponse(**data)



# ============== STUDENT DEEP DIVE ==============

@router.get("/analytics/student-deep-dive/{student_id}", response_model=StudentDeepDiveResponse)
async def get_student_deep_dive(
    student_id: str,
    exam_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> StudentDeepDiveResponse:
    """Get detailed student analysis with AI-generated insights"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await reporting_service.get_student_deep_dive(user.user_id, student_id, exam_id)
    return StudentDeepDiveResponse(**data)


# ============== GENERATE REVIEW PACKET ==============

@router.post("/analytics/generate-review-packet", response_model=Union[ReviewPacketResponse, MessageResponse])
async def generate_review_packet(
    exam_id: str,
    user: User = Depends(get_current_user)
) -> Union[ReviewPacketResponse, MessageResponse]:
    """Generate AI-powered practice questions based on weak topics"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await reporting_service.generate_review_packet(user.user_id, exam_id)
    if data.get("type", "packet") == "message":
        return MessageResponse(**data)
    return ReviewPacketResponse(**data)


# ============== BLUFF INDEX ==============

@router.get("/analytics/bluff-index/{exam_id}", response_model=BluffIndexResponse)
async def get_bluff_index(
    exam_id: str,
    user: User = Depends(get_current_user)
) -> BluffIndexResponse:
    """Detect students who write long but irrelevant answers"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_bluff_index(user.user_id, exam_id)
    return BluffIndexResponse(**data)


# ============== SYLLABUS COVERAGE ==============

@router.get("/analytics/syllabus-coverage", response_model=SyllabusCoverageResponse)
async def get_syllabus_coverage(
    batch_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> SyllabusCoverageResponse:
    """Syllabus Coverage Heatmap: Shows which topics have been tested and results"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_syllabus_coverage(
        user.user_id, batch_id, subject_id
    )
    return SyllabusCoverageResponse(**data)


# ============== PEER GROUPS ==============

@router.get("/analytics/peer-groups", response_model=PeerGroupSuggestionsResponse)
async def get_peer_group_suggestions(
    batch_id: str,
    user: User = Depends(get_current_user)
) -> PeerGroupSuggestionsResponse:
    """Auto-suggest study pairs based on complementary strengths/weaknesses"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.get_peer_group_suggestions(user.user_id, batch_id)
    return PeerGroupSuggestionsResponse(**data)


@router.post("/analytics/send-peer-group-email", response_model=MessageResponse)
async def send_peer_group_email(
    student1_id: str,
    student2_id: str,
    message: str,
    user: User = Depends(get_current_user)
) -> MessageResponse:
    """Send notification to suggested peer group"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.send_peer_group_email(
        user.user_id, student1_id, student2_id, message
    )
    return MessageResponse(**data)


# ============== NATURAL LANGUAGE QUERY (Ask Your Data) ==============

@router.post("/analytics/ask", response_model=AskDataResponse)
async def ask_your_data(
    request: NaturalLanguageQuery,
    user: User = Depends(get_current_user)
) -> AskDataResponse:
    """Natural Language Query: Ask questions in plain English and get visualizations"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await insights_service.ask_your_data(user.user_id, request)
    return AskDataResponse(**data)


# ============== DASHBOARD SNAPSHOT & ACTIONABLE STATS ==============

@router.get("/dashboard/class-snapshot", response_model=ClassSnapshotResponse)
async def get_class_snapshot(
    batch_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> ClassSnapshotResponse:
    """Get overall class performance snapshot for dashboard"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await analytics_service.get_class_snapshot(user.user_id, batch_id)
    return ClassSnapshotResponse(**data)


@router.get("/dashboard/actionable-stats", response_model=ActionableStatsResponse)
async def get_actionable_stats(
    batch_id: Optional[str] = None,
    user: User = Depends(get_current_user)
) -> ActionableStatsResponse:
    """Get actionable insights for dashboard heads-up display"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher only")

    data = await analytics_service.get_actionable_stats(user.user_id, batch_id)
    return ActionableStatsResponse(**data)
