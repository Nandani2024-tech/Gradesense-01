import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.schemas.exam.student_exam_create import StudentExamCreate
from app.domain.exam_nodes import ExamQuestion

class ExamFactory:
    """Factory for processing and generating Exam models for the database."""
    
    @staticmethod
    def exam_questions_to_db_questions(questions: List[ExamQuestion]) -> List[Dict[str, Any]]:
        """Converts domain ExamQuestion objects into DB-ready dictionary representations."""
        return [q.model_dump() for q in questions]

    @staticmethod
    def student_exam_create_to_exam_doc(student_exam: StudentExamCreate, teacher_id: str) -> Dict[str, Any]:
        """
        Converts StudentExamCreate schema to a DB-ready exam document dict.
        """
        exam_id = f"exam_{uuid.uuid4().hex[:12]}"
        questions = student_exam.questions or []
        db_questions = ExamFactory.exam_questions_to_db_questions(questions)
        
        has_questions = len(db_questions) > 0
        now = datetime.now(timezone.utc).isoformat()
        
        # Blueprint health requires complex derivation via logic not permitted here, 
        # but returning empty object is sufficient for initialization in factories
        blueprint_health: Dict[str, Any] = {}
        
        return {
            "exam_id": exam_id,
            "batch_id": student_exam.batch_id,
            "subject_id": "unknown", # default fallback
            "exam_name": student_exam.exam_name,
            "total_marks": student_exam.total_marks,
            "grading_mode": student_exam.grading_mode,
            "exam_mode": "student_upload",
            "exam_type": "standard", # default fallback
            "show_question_paper": student_exam.show_question_paper,
            "questions": db_questions,
            "question_extraction_status": "completed" if has_questions else "pending",
            "question_paper_processing": False,
            "blueprint_status": "ready_locked" if has_questions else "pending",
            "blueprint_locked_at": now if has_questions else None,
            "blueprint_version": 1 if has_questions else 0,
            "blueprint_health": blueprint_health,
            "teacher_id": teacher_id,
            "selected_students": student_exam.student_ids,
            "created_at": now,
            "status": "awaiting_submissions",
            "total_students": len(student_exam.student_ids),
            "submitted_count": 0
        }
