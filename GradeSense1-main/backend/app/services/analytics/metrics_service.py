from typing import List, Dict, Any, Optional
from app.repositories import SubmissionRepo, ExamRepo, AnalyticsRepo, StudentRepo
from app.services.llm.grading_llm_service import grading_llm_service
from app.core.logging_config import logger

class MetricsService:
    def __init__(self):
        self.student_repo = StudentRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()

    async def get_topic_drilldown(
        self,
        topic_name: str,
        teacher_id: str,
        exam_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Level 2 Drill-Down: Get detailed breakdown of a topic into sub-skills"""
        exam_query = {"teacher_id": teacher_id}
        if exam_id:
            exam_query["exam_id"] = exam_id
        if batch_id:
            exam_query["batch_id"] = batch_id

        exams = await self.exam_repo.find_exams(exam_query, limit=50)
        if not exams:
            return {"sub_skills": [], "questions": [], "students": []}

        exam_ids = [e["exam_id"] for e in exams]

        questions_in_topic = []
        for exam in exams:
            for question in exam.get("questions", []):
                topics = question.get("topic_tags", [])
                if not topics:
                    subject = None
                    if exam.get("subject_id"):
                        subject_doc = await self.analytics_repo.find_one_subject({"subject_id": exam["subject_id"]}, projection={"name": 1})
                        subject = subject_doc.get("name") if subject_doc else None
                    topics = [subject or "General"]

                if topic_name in topics:
                    questions_in_topic.append({
                        "exam_id": exam["exam_id"],
                        "exam_name": exam.get("exam_name", "Unknown"),
                        "question_number": question.get("question_number"),
                        "rubric": question.get("rubric", ""),
                        "max_marks": question.get("max_marks", 0),
                        "sub_questions": question.get("sub_questions", [])
                    })

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=500,
            projection={"student_id": 1, "student_name": 1, "exam_id": 1, "question_scores": 1}
        )

        sub_skill_performance = {}
        question_performance = {}

        for q in questions_in_topic:
            q_key = f"{q['exam_id']}_{q['question_number']}"
            question_performance[q_key] = {
                "exam_name": q["exam_name"], "question_number": q["question_number"],
                "rubric": q["rubric"], "max_marks": q["max_marks"],
                "scores": [], "avg_percentage": 0
            }

            rubric_lower = q["rubric"].lower()
            sub_skill = "Concept Understanding"
            if any(word in rubric_lower for word in ["calculate", "compute", "find the value"]):
                sub_skill = "Calculation"
            elif any(word in rubric_lower for word in ["prove", "derive", "show that"]):
                sub_skill = "Proof & Derivation"
            elif any(word in rubric_lower for word in ["apply", "solve", "use"]):
                sub_skill = "Application"
            elif any(word in rubric_lower for word in ["explain", "describe", "define"]):
                sub_skill = "Concept Understanding"

            if sub_skill not in sub_skill_performance:
                sub_skill_performance[sub_skill] = {"scores": [], "question_count": 0}
            sub_skill_performance[sub_skill]["question_count"] += 1

        for submission in submissions:
            for qs in submission.get("question_scores", []):
                q_key = f"{submission['exam_id']}_{qs.get('question_number')}"
                if q_key in question_performance:
                    percentage = (qs["obtained_marks"] / qs["max_marks"]) * 100 if qs.get("max_marks", 0) > 0 else 0
                    question_performance[q_key]["scores"].append({
                        "student_id": submission["student_id"],
                        "student_name": submission["student_name"],
                        "obtained": qs["obtained_marks"],
                        "max": qs["max_marks"],
                        "percentage": percentage,
                        "feedback": qs.get("ai_feedback", "")
                    })

        for q_key, q_data in question_performance.items():
            if q_data["scores"]:
                q_data["avg_percentage"] = round(sum(s["percentage"] for s in q_data["scores"]) / len(q_data["scores"]), 1)

        for q in questions_in_topic:
            q_key = f"{q['exam_id']}_{q['question_number']}"
            if q_key in question_performance:
                rubric_lower = q["rubric"].lower()
                sub_skill = "Concept Understanding"
                if any(word in rubric_lower for word in ["calculate", "compute", "find the value"]):
                    sub_skill = "Calculation"
                elif any(word in rubric_lower for word in ["prove", "derive", "show that"]):
                    sub_skill = "Proof & Derivation"
                elif any(word in rubric_lower for word in ["apply", "solve", "use"]):
                    sub_skill = "Application"
                elif any(word in rubric_lower for word in ["explain", "describe", "define"]):
                    sub_skill = "Concept Understanding"

                for score in question_performance[q_key]["scores"]:
                    sub_skill_performance[sub_skill]["scores"].append(score["percentage"])

        sub_skills = []
        for skill, data in sub_skill_performance.items():
            if data["scores"]:
                avg = round(sum(data["scores"]) / len(data["scores"]), 1)
                sub_skills.append({
                    "name": skill, "avg_percentage": avg,
                    "question_count": data["question_count"],
                    "color": "green" if avg >= 70 else "amber" if avg >= 50 else "red"
                })

        student_performance = {}
        for q_key, q_data in question_performance.items():
            for score in q_data["scores"]:
                sid = score["student_id"]
                if sid not in student_performance:
                    student_performance[sid] = {"student_id": sid, "student_name": score["student_name"], "scores": []}
                student_performance[sid]["scores"].append(score["percentage"])

        struggling_students = []
        for sid, data in student_performance.items():
            avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            if avg < 60:
                struggling_students.append({
                    "student_id": data["student_id"], "student_name": data["student_name"],
                    "avg_percentage": round(avg, 1), "attempts": len(data["scores"])
                })

        insight = f"Analysis shows {len(struggling_students)} students need attention in {topic_name}. "
        if sub_skills:
            weakest = min(sub_skills, key=lambda x: x["avg_percentage"])
            insight += f"Weakest sub-skill: {weakest['name']} ({weakest['avg_percentage']}%)."

        return {
            "topic": topic_name, "insight": insight,
            "sub_skills": sorted(sub_skills, key=lambda x: x["avg_percentage"]),
            "questions": [q for q in question_performance.values()],
            "struggling_students": struggling_students
        }

    async def get_question_drilldown(
        self,
        exam_id: str,
        question_number: int,
        teacher_id: str
    ) -> Dict[str, Any]:
        """Level 3 Drill-Down: Get error patterns for a specific question"""
        exam = await self.exam_repo.find_one_exam({"exam_id": exam_id, "teacher_id": teacher_id})
        if not exam:
            return None

        question = None
        for q in exam.get("questions", []):
            if q.get("question_number") == question_number:
                question = q
                break

        if not question:
            return None

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": exam_id},
            limit=1000,
            projection={"student_id": 1, "student_name": 1, "question_scores": 1, "file_images": 1}
        )

        student_answers = []
        for submission in submissions:
            for qs in submission.get("question_scores", []):
                if qs.get("question_number") == question_number:
                    student_answers.append({
                        "student_id": submission["student_id"],
                        "student_name": submission["student_name"],
                        "obtained_marks": qs["obtained_marks"],
                        "max_marks": qs["max_marks"],
                        "percentage": (qs["obtained_marks"] / qs["max_marks"]) * 100 if qs.get("max_marks", 0) > 0 else 0,
                        "feedback": qs.get("ai_feedback", ""),
                        "answer_text": qs.get("answer_text", ""),
                        "sub_scores": qs.get("sub_scores", [])
                    })

        failed_answers = [a for a in student_answers if a["percentage"] < 50]
        passed_answers = [a for a in student_answers if a["percentage"] >= 50]
        blank_answers = [a for a in student_answers if a["obtained_marks"] == 0]

        error_groups = {}
        if failed_answers:
            try:
                feedback_samples = [f"Student {a['student_name']}: {a['feedback']}" for a in failed_answers[:10]]
                error_analysis = await grading_llm_service.categorize_student_errors(
                    question_number=question_number,
                    question_rubric=question.get('rubric', ''),
                    max_marks=question.get('max_marks', 0),
                    feedback_samples=feedback_samples
                )
                
                if error_analysis:
                    for category in error_analysis.get("error_categories", []):
                        error_type = category["type"]
                        error_groups[error_type] = {"description": category["description"], "students": []}
                        for answer in failed_answers:
                            if answer["student_name"] in category.get("student_names", []):
                                error_groups[error_type]["students"].append({
                                    "student_id": answer["student_id"],
                                    "student_name": answer["student_name"],
                                    "score": answer["obtained_marks"],
                                    "feedback": answer["feedback"]
                                })
            except Exception as e:
                logger.error(f"Error in AI error grouping: {e}")
                error_groups = {
                    "Low Scorers": {
                        "description": "Students who scored below 50%",
                        "students": [{"student_id": a["student_id"], "student_name": a["student_name"], "score": a["obtained_marks"], "feedback": a["feedback"]} for a in failed_answers]
                    }
                }

        if blank_answers:
            error_groups["Not Attempted / Blank"] = {
                "description": "Students who left the question blank or scored 0",
                "students": [{"student_id": a["student_id"], "student_name": a["student_name"], "score": 0, "feedback": "No answer provided"} for a in blank_answers]
            }

        total_students = len(student_answers)
        avg_score = sum(a["percentage"] for a in student_answers) / total_students if total_students > 0 else 0
        pass_count = len([a for a in student_answers if a["percentage"] >= 50])

        return {
            "question": {"number": question_number, "rubric": question.get("rubric", ""), "max_marks": question.get("max_marks", 0)},
            "statistics": {
                "total_students": total_students, "avg_percentage": round(avg_score, 1),
                "pass_count": pass_count, "fail_count": total_students - pass_count,
                "blank_count": len(blank_answers)
            },
            "error_groups": [
                {"type": error_type, "description": data["description"], "count": len(data["students"]), "students": data["students"]}
                for error_type, data in error_groups.items()
            ],
            "top_performers": sorted(
                [{"student_name": a["student_name"], "score": a["obtained_marks"], "max_marks": a["max_marks"]} for a in passed_answers],
                key=lambda x: x["score"], reverse=True
            )[:5]
        }

    async def get_ai_comprehensive_insights(self, query: str, user_id: str) -> str:
        """Process natural language queries for academic insights using LLM"""
        # Gather context data
        submissions = await self.submission_repo.find_submissions(
            {"student_id": user_id},
            limit=10,
            sort_field="created_at",
            sort_dir=-1
        )
        
        if not submissions:
            return "No submission data available for analysis."

        data_summary = f"Student {user_id} has {len(submissions)} recent submissions. "
        for sub in submissions:
            data_summary += f"Exam {sub['exam_id']}: {sub['percentage']}%. "

        ai_response = await grading_llm_service.ask_ai_analytics(
            data_summary=data_summary,
            query=query
        )
        return ai_response

    async def get_metrics_overview(self) -> Dict[str, Any]:
        """Admin Metrics Overview"""
        # Placeholder for complex aggregation
        return {
            "business_metrics": {}, "engagement_metrics": {}, 
            "ai_trust_metrics": {}, "system_performance": {}, 
            "unit_economics": {}, "geographic_distribution": []
        }

metrics_service = MetricsService()
