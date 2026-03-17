from pydantic import BaseModel
from typing import List, Any, Optional, Dict

class StudentDashboardStats(BaseModel):
    total_exams: int
    avg_percentage: float
    rank: str
    improvement: float

class RecentResultItem(BaseModel):
    exam_name: str
    subject: str
    score: str
    percentage: float
    date: str

class SubjectPerformanceItem(BaseModel):
    subject: str
    average: float
    exams: int

class TopicPerformanceItem(BaseModel):
    topic: str
    avg_score: float
    total_attempts: int
    trend: float
    trend_text: str
    recent_score: float
    feedback: str

class WeakAreaItem(BaseModel):
    question: str
    score: str
    feedback: str

class StrongAreaItem(BaseModel):
    question: str
    score: str

class StudentDashboardResponse(BaseModel):
    stats: StudentDashboardStats
    recent_results: List[RecentResultItem]
    subject_performance: List[SubjectPerformanceItem]
    recommendations: List[str]
    weak_topics: List[TopicPerformanceItem]
    strong_topics: List[TopicPerformanceItem]
    weak_areas: List[WeakAreaItem]
    strong_areas: List[StrongAreaItem]

class ChatResponse(BaseModel):
    type: str
    response: str

class StudyMaterialsResponse(BaseModel):
    weak_topics: List[Dict[str, Any]]
    recommended_materials: List[Dict[str, Any]]

class StudentPerformanceDeepDive(BaseModel):
    student: Any
    performance_trend: List[Any]
    vs_class_avg: List[Any]
    blind_spots: List[Any]
    strengths: List[Any]

class TopicDrilldownResponse(BaseModel):
    topic: str
    insight: str
    sub_skills: List[Dict[str, Any]]
    questions: List[Dict[str, Any]]
    struggling_students: List[Dict[str, Any]]

class QuestionDrilldownResponse(BaseModel):
    question: Dict[str, Any]
    statistics: Dict[str, Any]
    error_groups: List[Dict[str, Any]]
    top_performers: List[Dict[str, Any]]

class StudentJourneyResponse(BaseModel):
    student: Dict[str, Any]
    overall_stats: Dict[str, Any]
    performance_trend: List[Dict[str, Any]]
    vs_class_avg: List[Dict[str, Any]]
    blind_spots: List[Dict[str, Any]]
    strengths: List[Dict[str, Any]]
