from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
import math

from app.repositories import StudentRepo, SubmissionRepo, ExamRepo, AnalyticsRepo

class AnalyticsService:
    """Service for high-level dashboard and class analytics."""

    def __init__(self):
        self.student_repo = StudentRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()

    async def get_dashboard_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard analytics for teacher"""
        total_exams = await self.exam_repo.count_exams({"teacher_id": user_id})
        total_batches = await self.analytics_repo.count_batches({"teacher_id": user_id})
        total_students = await self.student_repo.count_students({"teacher_id": user_id})

        exams = await self.exam_repo.find_exams({"teacher_id": user_id}, limit=100, projection={"exam_id": 1})
        exam_ids = [e["exam_id"] for e in exams]

        total_submissions = await self.submission_repo.count_submissions({"exam_id": {"$in": exam_ids}})
        pending_reviews = await self.submission_repo.count_submissions({
            "exam_id": {"$in": exam_ids},
            "status": "ai_graded"
        })
        pending_reeval = await self.analytics_repo.count_re_evaluations({
            "exam_id": {"$in": exam_ids},
            "status": "pending"
        })

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=500
        )
        
        avg_score = sum(s.get("percentage", 0) for s in submissions) / len(submissions) if submissions else 0

        recent_submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=10,
            sort_field="graded_at",
            sort_dir=-1
        )

        return {
            "stats": {
                "total_exams": total_exams,
                "total_batches": total_batches,
                "total_students": total_students,
                "total_submissions": total_submissions,
                "pending_reviews": pending_reviews,
                "pending_reeval": pending_reeval,
                "avg_score": round(avg_score, 1)
            },
            "recent_submissions": recent_submissions
        }

    async def get_class_report(
        self, 
        user_id: str,
        batch_id: Optional[str] = None,
        subject_id: Optional[str] = None,
        exam_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get class report analytics"""
        exam_query = {"teacher_id": user_id}
        if batch_id:
            exam_query["batch_id"] = batch_id
        if subject_id:
            exam_query["subject_id"] = subject_id
        if exam_id:
            exam_query["exam_id"] = exam_id

        exams = await self.exam_repo.find_exams(exam_query, limit=100)
        exam_ids = [e["exam_id"] for e in exams]

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=500
        )

        if not submissions:
            return {
                "overview": {
                    "total_students": 0, "avg_score": 0, "highest_score": 0,
                    "lowest_score": 0, "pass_percentage": 0
                },
                "score_distribution": [],
                "top_performers": [],
                "needs_attention": [],
                "question_analysis": []
            }

        percentages = [s["percentage"] for s in submissions]

        distribution = {
            "0-20": len([p for p in percentages if 0 <= p < 20]),
            "21-40": len([p for p in percentages if 20 <= p < 40]),
            "41-60": len([p for p in percentages if 40 <= p < 60]),
            "61-80": len([p for p in percentages if 60 <= p < 80]),
            "81-100": len([p for p in percentages if 80 <= p <= 100])
        }

        sorted_subs = sorted(submissions, key=lambda x: x["percentage"], reverse=True)
        top_performers = [
            {
                "name": s["student_name"],
                "student_id": s["student_id"],
                "score": s.get("obtained_marks") or s.get("total_score", 0),
                "percentage": s["percentage"]
            }
            for s in sorted_subs[:5]
        ]

        needs_attention = [
            {
                "name": s["student_name"],
                "student_id": s["student_id"],
                "score": s.get("obtained_marks") or s.get("total_score", 0),
                "percentage": s["percentage"]
            }
            for s in submissions if s["percentage"] < 40
        ][:10]

        question_analysis = []
        if submissions and submissions[0].get("question_scores"):
            num_questions = len(submissions[0]["question_scores"])
            for q_idx in range(num_questions):
                q_scores = []
                max_marks = 0
                for sub in submissions:
                    if len(sub.get("question_scores", [])) > q_idx:
                        qs = sub["question_scores"][q_idx]
                        q_scores.append(qs["obtained_marks"])
                        max_marks = qs["max_marks"]
                if q_scores:
                    avg = sum(q_scores) / len(q_scores)
                    question_analysis.append({
                        "question": q_idx + 1,
                        "max_marks": max_marks,
                        "avg_score": round(avg, 2),
                        "percentage": round((avg / max_marks) * 100, 1) if max_marks > 0 else 0
                    })

        return {
            "overview": {
                "total_students": len(submissions),
                "avg_score": round(sum(percentages) / len(percentages), 1),
                "highest_score": max(percentages),
                "lowest_score": min(percentages),
                "pass_percentage": round(len([p for p in percentages if p >= 40]) / len(percentages) * 100, 1)
            },
            "score_distribution": [{"range": k, "count": v} for k, v in distribution.items()],
            "top_performers": top_performers,
            "needs_attention": needs_attention,
            "question_analysis": question_analysis
        }

    async def get_class_snapshot(self, user_id: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        """Get overall class performance snapshot for dashboard"""
        exam_query = {"teacher_id": user_id}
        if batch_id:
            exam_query["batch_id"] = batch_id

        exams = await self.exam_repo.find_exams(
            exam_query, 
            limit=100, 
            projection={"exam_id": 1, "exam_name": 1, "created_at": 1, "batch_id": 1}
        )

        if not exams:
            return {
                "batch_name": "No Batch Selected", "total_students": 0, "class_average": 0,
                "pass_rate": 0, "total_exams": 0, "recent_exam": None, "trend": 0,
                "top_performers": [], "struggling_students": []
            }

        exam_ids = [e["exam_id"] for e in exams]

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=10000
        )

        if not submissions:
            return {
                "batch_name": "No Data", "total_students": 0, "class_average": 0,
                "pass_rate": 0, "total_exams": len(exams),
                "recent_exam": exams[0].get("exam_name") if exams else None,
                "trend": 0, "top_performers": [], "struggling_students": []
            }

        total_students = len(set(s.get("student_id") for s in submissions if s.get("student_id")))
        class_average = sum(s.get("percentage", 0) for s in submissions) / len(submissions) if submissions else 0
        pass_count = len([s for s in submissions if s.get("percentage", 0) >= 50])
        pass_rate = (pass_count / len(submissions)) * 100 if submissions else 0

        batch_name = "All Batches"
        if batch_id:
            batch = await self.analytics_repo.find_one_batch({"batch_id": batch_id})
            batch_name = batch.get("name") if batch else "Unknown Batch"

        recent_exam = max(exams, key=lambda x: x.get("created_at", ""))

        sorted_exams = sorted(exams, key=lambda x: x.get("created_at", ""), reverse=True)
        trend = 0

        if len(sorted_exams) >= 6:
            recent_exam_ids = [e["exam_id"] for e in sorted_exams[:3]]
            older_exam_ids = [e["exam_id"] for e in sorted_exams[3:6]]
            recent_subs = [s for s in submissions if s["exam_id"] in recent_exam_ids]
            older_subs = [s for s in submissions if s["exam_id"] in older_exam_ids]
            if recent_subs and older_subs:
                recent_avg = sum(s["percentage"] for s in recent_subs) / len(recent_subs)
                older_avg = sum(s["percentage"] for s in older_subs) / len(older_subs)
                trend = round(recent_avg - older_avg, 1)

        student_averages = {}
        for sub in submissions:
            sid = sub.get("student_id")
            if not sid:
                continue
            if sid not in student_averages:
                student_averages[sid] = {"name": sub.get("student_name", "Unknown"), "scores": []}
            student_averages[sid]["scores"].append(sub.get("percentage", 0))

        student_stats = []
        for sid, data in student_averages.items():
            avg = sum(data["scores"]) / len(data["scores"])
            student_stats.append({"student_id": sid, "student_name": data["name"], "average": round(avg, 1)})

        student_stats.sort(key=lambda x: x["average"], reverse=True)

        top_performers = student_stats[:3]
        struggling_students = [s for s in student_stats if s["average"] < 50][:3]

        return {
            "batch_name": batch_name, "total_students": total_students,
            "class_average": round(class_average, 1), "pass_rate": round(pass_rate, 1),
            "total_exams": len(exams), "recent_exam": recent_exam.get("exam_name", "Unknown"),
            "recent_exam_date": recent_exam.get("created_at", ""), "trend": trend,
            "top_performers": top_performers, "struggling_students": struggling_students
        }

    async def get_actionable_stats(self, user_id: str, batch_id: Optional[str] = None) -> Dict[str, Any]:
        """Get actionable insights for dashboard heads-up display"""
        exam_query = {"teacher_id": user_id}
        if batch_id:
            exam_query["batch_id"] = batch_id

        exams = await self.exam_repo.find_exams(exam_query, limit=100)

        if not exams:
            return {
                "action_required": {"pending_reviews": 0, "quality_concerns": 0, "total": 0, "papers": []},
                "performance": {"current_avg": 0, "previous_avg": 0, "trend": 0, "trend_direction": "stable"},
                "at_risk": {"count": 0, "students": [], "threshold": 40},
                "hardest_concept": None
            }

        exam_ids = [e["exam_id"] for e in exams]

        submissions = await self.submission_repo.find_submissions(
            {"exam_id": {"$in": exam_ids}},
            limit=10000
        )

        pending_reviews = len([s for s in submissions if s.get("status") == "pending"])

        quality_concerns = []
        for sub in submissions:
            if sub.get("percentage", 0) < 50:
                for qs in sub.get("question_scores", []):
                    answer_text = qs.get("answer_text", "")
                    obtained = qs.get("obtained_marks", 0)
                    max_marks = qs.get("max_marks", 1)
                    percentage = (obtained / max_marks) * 100 if max_marks > 0 else 0
                    if len(answer_text) > 100 and percentage < 30:
                        quality_concerns.append({
                            "submission_id": sub.get("submission_id"),
                            "student_name": sub.get("student_name", "Unknown"),
                            "exam_id": sub.get("exam_id")
                        })
                        break
        quality_concerns = quality_concerns[:10]

        sorted_exams = sorted(exams, key=lambda x: x.get("created_at", ""), reverse=True)
        current_avg = 0
        previous_avg = 0
        trend = 0

        if len(sorted_exams) >= 2:
            recent_exam_ids = [e["exam_id"] for e in sorted_exams[:2]]
            recent_subs = [s for s in submissions if s["exam_id"] in recent_exam_ids]
            if len(sorted_exams) >= 4:
                prev_exam_ids = [e["exam_id"] for e in sorted_exams[2:4]]
                prev_subs = [s for s in submissions if s["exam_id"] in prev_exam_ids]
                if recent_subs and prev_subs:
                    current_avg = sum(s.get("percentage", 0) for s in recent_subs) / len(recent_subs)
                    previous_avg = sum(s.get("percentage", 0) for s in prev_subs) / len(prev_subs)
                    trend = current_avg - previous_avg
        elif submissions:
            current_avg = sum(s.get("percentage", 0) for s in submissions) / len(submissions)

        trend_direction = "up" if trend > 2 else "down" if trend < -2 else "stable"

        at_risk_students = {}
        if len(sorted_exams) >= 2:
            recent_exam_ids = [e["exam_id"] for e in sorted_exams[:2]]
            recent_subs = [s for s in submissions if s["exam_id"] in recent_exam_ids]
            for sub in recent_subs:
                percentage = sub.get("percentage", 0)
                if percentage < 40:
                    sid = sub.get("student_id")
                    if not sid:
                        continue
                    if sid not in at_risk_students:
                        at_risk_students[sid] = {"student_id": sid, "student_name": sub.get("student_name", "Unknown"), "avg_score": percentage, "exams_failed": 1}
                    else:
                        at_risk_students[sid]["exams_failed"] += 1

        at_risk_list = list(at_risk_students.values())
        at_risk_list.sort(key=lambda x: x["avg_score"])

        question_performance = {}
        for sub in submissions:
            for qs in sub.get("question_scores", []):
                q_key = f"{sub['exam_id']}_{qs.get('question_number')}"
                if q_key not in question_performance:
                    question_performance[q_key] = {"exam_id": sub["exam_id"], "question_number": qs.get("question_number"), "total_attempts": 0, "total_score": 0, "max_marks": qs.get("max_marks", 0)}
                question_performance[q_key]["total_attempts"] += 1
                question_performance[q_key]["total_score"] += qs.get("obtained_marks", 0)

        question_stats = []
        for q_key, data in question_performance.items():
            if data["total_attempts"] > 0:
                avg_obtained = data["total_score"] / data["total_attempts"]
                success_rate = (avg_obtained / data["max_marks"]) * 100 if data["max_marks"] > 0 else 0
                exam = await self.exam_repo.find_one_exam({"exam_id": data["exam_id"]}, projection={"exam_name": 1, "questions": 1})
                if exam:
                    for q in exam.get("questions", []):
                        if q.get("question_number") == data["question_number"]:
                            question_stats.append({
                                "exam_id": data["exam_id"], "exam_name": exam.get("exam_name", "Unknown"),
                                "question_number": data["question_number"],
                                "topic": q.get("rubric", "")[:50] + "..." if len(q.get("rubric", "")) > 50 else q.get("rubric", "Unknown"),
                                "success_rate": round(success_rate, 1), "attempts": data["total_attempts"]
                            })
                            break

        valid_questions = [q for q in question_stats if q["attempts"] >= 5]
        hardest = min(valid_questions, key=lambda x: x["success_rate"]) if valid_questions else None

        return {
            "action_required": {"pending_reviews": pending_reviews, "quality_concerns": len(quality_concerns), "total": pending_reviews + len(quality_concerns), "papers": quality_concerns[:5]},
            "performance": {"current_avg": round(current_avg, 1), "previous_avg": round(previous_avg, 1), "trend": round(trend, 1), "trend_direction": trend_direction},
            "at_risk": {"count": len(at_risk_list), "students": at_risk_list[:5], "threshold": 40},
            "hardest_concept": hardest
        }

analytics_service = AnalyticsService()
