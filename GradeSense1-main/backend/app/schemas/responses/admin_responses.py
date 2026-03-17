from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class AdminStatusResponse(BaseModel):
    is_admin: bool
    email: str
    role: str

class AdminDashboardStats(BaseModel):
    active_now: int
    pending_feedback: int
    api_health: float
    system_status: str

class UserUsageStats(BaseModel):
    exams_this_month: int
    papers_this_month: int
    total_students: int
    total_batches: int

class UserDetailsResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    account_status: str
    feature_flags: Dict[str, bool]
    quotas: Dict[str, int]
    current_usage: UserUsageStats
    created_at: str
    picture: Optional[str] = None
    teacher_type: Optional[str] = None
    exam_category: Optional[str] = None

class FeedbackItem(BaseModel):
    feedback_id: str
    type: str
    data: str
    metadata: Dict[str, Any]
    user: Dict[str, str]
    status: str
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[Dict[str, str]] = None

class BusinessMetrics(BaseModel):
    total_users: int
    total_teachers: int
    total_students: int
    dau: int
    wau: int
    mau: int
    new_signups_30d: int
    retention_rate: float

class EngagementMetrics(BaseModel):
    total_exams: int
    total_papers: int
    avg_batch_size: float
    power_users: List[Dict[str, Any]]
    grading_mode_distribution: List[Dict[str, Any]]
    avg_grading_time_seconds: float

class AiTrustMetrics(BaseModel):
    avg_confidence: float
    avg_grade_delta: float
    human_intervention_rate: float
    zero_touch_rate: float
    total_graded: int

class SystemPerformanceMetrics(BaseModel):
    avg_response_time_ms: float
    api_success_rate: float
    error_breakdown: List[Dict[str, Any]]

class UnitEconomicsMetrics(BaseModel):
    total_cost_usd: float
    avg_cost_per_paper_usd: float
    total_tokens_input: int
    total_tokens_output: int

class MetricsOverviewResponse(BaseModel):
    business_metrics: BusinessMetrics
    engagement_metrics: EngagementMetrics
    ai_trust_metrics: AiTrustMetrics
    system_performance: SystemPerformanceMetrics
    unit_economics: UnitEconomicsMetrics
    geographic_distribution: List[Dict[str, Any]]

class FeedbackSubmitResponse(BaseModel):
    success: bool
    feedback_id: str
    message: str
