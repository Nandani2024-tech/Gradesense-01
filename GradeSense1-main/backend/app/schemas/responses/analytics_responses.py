from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

# ============== DASHBOARD ==============

class DashboardStats(BaseModel):
    total_exams: int
    total_batches: int
    total_students: int
    total_submissions: int
    pending_reviews: int
    pending_reeval: int
    avg_score: float

class RecentSubmission(BaseModel):
    submission_id: str
    student_name: str
    exam_id: str
    student_id: str
    obtained_marks: Optional[float] = None
    total_marks: Optional[float] = None
    percentage: float
    total_score: Optional[float] = None
    status: str
    created_at: Optional[str] = None
    graded_at: Optional[str] = None

class DashboardAnalyticsResponse(BaseModel):
    stats: DashboardStats
    recent_submissions: List[RecentSubmission]

# ============== CLASS REPORT ==============

class ClassReportOverview(BaseModel):
    total_students: int
    avg_score: float
    highest_score: float
    lowest_score: float
    pass_percentage: float

class ScoreDistributionItem(BaseModel):
    range: str
    count: int

class PerformanceItem(BaseModel):
    name: str
    student_id: str
    score: float
    percentage: float

class QuestionAnalysisItem(BaseModel):
    question: int
    max_marks: float
    avg_score: float
    percentage: float

class ClassReportResponse(BaseModel):
    overview: ClassReportOverview
    score_distribution: List[ScoreDistributionItem]
    top_performers: List[PerformanceItem]
    needs_attention: List[PerformanceItem]
    question_analysis: List[QuestionAnalysisItem]

# ============== INSIGHTS ==============

class ClassInsightsResponse(BaseModel):
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]

# ============== MISCONCEPTIONS ==============

class WrongAnswerItem(BaseModel):
    student_name: str
    submission_id: str
    obtained: float
    max: float
    feedback: str
    question_text: str

class QuestionInsightItem(BaseModel):
    question_number: int
    question_text: str
    avg_percentage: float
    fail_rate: float
    total_students: int
    failing_students: int
    wrong_answers: List[WrongAnswerItem]

class MisconceptionItem(BaseModel):
    question_number: int
    fail_percentage: float
    affected_students: int
    sample_feedbacks: List[str]

class MisconceptionsResponse(BaseModel):
    exam_name: str
    total_submissions: int
    misconceptions: List[MisconceptionItem]
    question_insights: List[QuestionInsightItem]
    ai_analysis: List[Any]

# ============== TOPIC MASTERY ==============

class TopicMasteryItem(BaseModel):
    topic: str
    avg_percentage: float
    level: str
    color: str
    sample_count: int
    struggling_count: int
    question_count: int

class TopicMasteryResponse(BaseModel):
    topics: List[TopicMasteryItem]
    students_by_topic: Dict[str, List[Dict[str, Any]]]
    questions_by_topic: Dict[str, List[Dict[str, Any]]]

# ============== BLUFF INDEX ==============

class SuspiciousAnswer(BaseModel):
    question_number: int
    answer_length: int
    score_percentage: float
    feedback_snippet: str

class BluffCandidate(BaseModel):
    student_id: str
    student_name: str
    bluff_score: int
    suspicious_answers: List[SuspiciousAnswer]

class BluffIndexResponse(BaseModel):
    exam_id: str
    exam_name: str
    total_students: int
    bluff_candidates: List[BluffCandidate]
    summary: str

# ============== SYLLABUS COVERAGE ==============

class TopicHeatmapItem(BaseModel):
    topic: str
    status: str
    exam_count: int
    question_count: int
    avg_score: float
    last_tested: Optional[str] = None
    color: str

class SyllabusCoverageResponse(BaseModel):
    subject: str
    total_exams: int
    tested_topics: List[TopicHeatmapItem]
    untested_topics: List[TopicHeatmapItem]
    coverage_percentage: float
    summary: str

# ============== PEER GROUPS ==============

class PeerGroupStudent(BaseModel):
    id: str
    name: str
    strengths: List[str]
    weaknesses: List[str]

class ComplementaryTopic(BaseModel):
    topic: str
    helper: str
    learner: str

class PeerGroupSuggestion(BaseModel):
    student1: PeerGroupStudent
    student2: PeerGroupStudent
    complementary_topics: List[ComplementaryTopic]
    synergy_score: int

class PeerGroupSuggestionsResponse(BaseModel):
    batch_id: str
    batch_name: str
    total_students: int
    suggestions: List[PeerGroupSuggestion]
    summary: str

# ============== SNAPSHOT ==============

class StudentSnapshot(BaseModel):
    student_id: str
    student_name: str
    average: float

class ClassSnapshotResponse(BaseModel):
    batch_name: str
    total_students: int
    class_average: float
    pass_rate: float
    total_exams: int
    recent_exam: Optional[str] = None
    recent_exam_date: Optional[str] = None
    trend: float
    top_performers: List[StudentSnapshot]
    struggling_students: List[StudentSnapshot]

# ============== ACTIONABLE STATS ==============

class ActionRequired(BaseModel):
    pending_reviews: int
    quality_concerns: int
    total: int
    papers: List[Dict[str, Any]]

class PerformanceStats(BaseModel):
    current_avg: float
    previous_avg: float
    trend: float
    trend_direction: str

class AtRiskStats(BaseModel):
    count: int
    students: List[Dict[str, Any]]
    threshold: int

class ActionableStatsResponse(BaseModel):
    action_required: ActionRequired
    performance: PerformanceStats
    at_risk: AtRiskStats
    hardest_concept: Optional[Dict[str, Any]] = None

# ============== ASK DATA ==============

class AskDataResponse(BaseModel):
    type: Optional[str] = None
    message: Optional[str] = None
    intent: Optional[str] = None
    chart_type: Optional[str] = None
    data_query: Optional[Dict[str, Any]] = None
    chart_config: Optional[Dict[str, Any]] = None
    result_data: Optional[List[Dict[str, Any]]] = None
# ============== STUDENT DEEP DIVE ==============

class DeepDiveStudent(BaseModel):
    name: str
    email: str
    student_id: str

class WorstQuestion(BaseModel):
    exam_name: str
    exam_id: str
    submission_id: str
    question_number: int
    question_text: str
    obtained_marks: float
    max_marks: float
    percentage: float
    ai_feedback: str
    has_model_answer: bool

class PerformanceTrendItem(BaseModel):
    exam_name: str
    percentage: float
    date: str

class StudentAiAnalysis(BaseModel):
    summary: str
    recommendations: Optional[List[str]] = None
    concepts_to_review: Optional[List[str]] = None

class StudentDeepDiveResponse(BaseModel):
    student: DeepDiveStudent
    overall_average: float
    total_exams: int
    worst_questions: List[WorstQuestion]
    performance_trend: List[PerformanceTrendItem]
    ai_analysis: Optional[StudentAiAnalysis] = None

# ============== REVIEW PACKET ==============

class PracticeQuestion(BaseModel):
    question_number: int
    question: str
    marks: float
    topic: str
    difficulty: str
    hint: Optional[str] = None

class ReviewPacketResponse(BaseModel):
    exam_name: Optional[str] = None
    subject: str
    weak_areas_identified: int
    practice_questions: List[PracticeQuestion]
    generated_at: str
