from typing import List, Dict, Any, Optional
from datetime import datetime
from app.repositories import StudentRepo, SubmissionRepo, ExamRepo, AnalyticsRepo
from .peer_group_service import peer_group_service
from app.models.user import User
from app.core.database import db
from app.core.logging_config import logger

class DashboardService:
    def __init__(self):
        self.student_repo = StudentRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()

    async def get_student_dashboard(self, user: User) -> Dict[str, Any]:
        """Get student's personal dashboard analytics"""
        published_exams = await self.exam_repo.find_exams(
            {"results_published": True},
            projection={"exam_id": 1}
        )
        published_exam_ids = [e["exam_id"] for e in published_exams]

        submissions = await self.submission_repo.find_submissions(
            {"student_id": user.user_id, "exam_id": {"$in": published_exam_ids}}
        )

        if not submissions:
            return {
                "stats": {"total_exams": 0, "avg_percentage": 0, "rank": "N/A", "improvement": 0},
                "recent_results": [], "subject_performance": [],
                "recommendations": ["Complete your first exam to see analytics!"],
                "weak_areas": [], "strong_areas": [],
                "weak_topics": [], "strong_topics": []
            }

        percentages = [s.get("percentage", 0) for s in submissions]

        recent = sorted(submissions, key=lambda x: x.get("graded_at", x.get("created_at", "")), reverse=True)[:5]
        recent_results = []
        for r in recent:
            exam = await self.exam_repo.find_one_exam({"exam_id": r["exam_id"]}, projection={"exam_name": 1, "subject_id": 1})
            subject = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}) if exam else None
            recent_results.append({
                "exam_name": exam.get("exam_name", "Unknown") if exam else "Unknown",
                "subject": subject.get("name", "Unknown") if subject else "Unknown",
                "score": f"{r.get('obtained_marks', 0)}/{r.get('total_marks', 100)}",
                "percentage": r.get("percentage", 0),
                "date": r.get("graded_at", r.get("created_at", ""))
            })

        subject_perf = {}
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"subject_id": 1})
            if exam:
                subj = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")})
                subj_name = subj.get("name", "Unknown") if subj else "Unknown"
                if subj_name not in subject_perf:
                    subject_perf[subj_name] = []
                subject_perf[subj_name].append(sub["percentage"])

        subject_performance = [
            {"subject": name, "average": round(sum(scores)/len(scores), 1), "exams": len(scores)}
            for name, scores in subject_perf.items()
        ]

        # ====== TOPIC-BASED PERFORMANCE ANALYSIS FOR STUDENTS ======
        topic_performance = {}

        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]})
            if not exam:
                continue

            exam_date = sub.get("created_at", "")
            exam_questions = exam.get("questions", [])

            question_topics = {}
            for q in exam_questions:
                q_num = q.get("question_number")
                topics = q.get("topic_tags", [])
                if not topics:
                    subj = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")})
                    topics = [subj.get("name", "General")] if subj else ["General"]
                question_topics[q_num] = topics

            for qs in sub.get("question_scores", []):
                q_num = qs.get("question_number")
                pct = (qs["obtained_marks"] / qs["max_marks"]) * 100 if qs.get("max_marks", 0) > 0 else 0
                topics = question_topics.get(q_num, ["General"])

                for topic in topics:
                    if topic not in topic_performance:
                        topic_performance[topic] = []
                    topic_performance[topic].append({
                        "score": pct,
                        "exam_date": exam_date,
                        "feedback": qs.get("ai_feedback", "")[:150]
                    })

        weak_topics = []
        strong_topics = []

        for topic, performances in topic_performance.items():
            if not performances:
                continue

            sorted_perfs = sorted(performances, key=lambda x: x.get("exam_date", ""))
            avg_score = sum(p["score"] for p in sorted_perfs) / len(sorted_perfs)

            trend = 0
            trend_text = "stable"
            if len(sorted_perfs) >= 2:
                mid = len(sorted_perfs) // 2
                first_half_avg = sum(p["score"] for p in sorted_perfs[:mid]) / mid if mid > 0 else 0
                second_half_avg = sum(p["score"] for p in sorted_perfs[mid:]) / (len(sorted_perfs) - mid)
                trend = second_half_avg - first_half_avg

                if trend > 10:
                    trend_text = "improving"
                elif trend < -10:
                    trend_text = "declining"

            topic_data = {
                "topic": topic,
                "avg_score": round(avg_score, 1),
                "total_attempts": len(sorted_perfs),
                "trend": round(trend, 1),
                "trend_text": trend_text,
                "recent_score": round(sorted_perfs[-1]["score"], 1) if sorted_perfs else 0,
                "feedback": sorted_perfs[-1].get("feedback", "") if sorted_perfs else ""
            }

            if avg_score < 50:
                weak_topics.append(topic_data)
            elif avg_score >= 75:
                strong_topics.append(topic_data)

        weak_topics = sorted(weak_topics, key=lambda x: x["avg_score"])[:5]
        strong_topics = sorted(strong_topics, key=lambda x: -x["avg_score"])[:5]

        recommendations = []
        declining_topics = [t for t in weak_topics if t["trend_text"] == "declining"]
        if declining_topics:
            recommendations.append(f"⚠️ Focus on {declining_topics[0]['topic']} - your performance is declining")

        improving_weak = [t for t in weak_topics if t["trend_text"] == "improving"]
        if improving_weak:
            recommendations.append(f"📈 Great improvement in {improving_weak[0]['topic']}! Keep practicing")

        stable_weak = [t for t in weak_topics if t["trend_text"] == "stable"]
        if stable_weak:
            recommendations.append(f"💡 Review concepts in {stable_weak[0]['topic']} - needs more attention")

        if strong_topics:
            recommendations.append(f"⭐ You're excelling in {strong_topics[0]['topic']}! Consider helping classmates")

        if not recommendations:
            recommendations = [
                "Complete more exams to get personalized insights",
                "Review feedback on each question to improve",
                "Practice regularly across all topics"
            ]

        avg_percentage = sum(percentages) / len(percentages) if percentages else 0

        if len(percentages) >= 2:
            recent_avg = sum(percentages[-3:]) / min(3, len(percentages))
            older_avg = sum(percentages[:-3]) / max(1, len(percentages) - 3) if len(percentages) > 3 else recent_avg
            improvement = round(recent_avg - older_avg, 1)
        else:
            improvement = 0

        return {
            "stats": {
                "total_exams": len(submissions),
                "avg_percentage": round(avg_percentage, 1),
                "rank": "Top 10",
                "improvement": improvement
            },
            "recent_results": recent_results,
            "subject_performance": subject_performance,
            "recommendations": recommendations,
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
            "weak_areas": [{"question": t["topic"], "score": f"{t['avg_score']}%", "feedback": t.get("feedback", "")} for t in weak_topics],
            "strong_areas": [{"question": t["topic"], "score": f"{t['avg_score']}%"} for t in strong_topics]
        }

    async def get_student_journey(self, student_id: str) -> Dict[str, Any]:
        """Student Journey View: Complete academic health record with comparisons"""
        student = await self.student_repo.get_student_by_id(student_id)
        if not student:
            return None

        submissions = await self.submission_repo.find_submissions({"student_id": student_id})

        if not submissions:
            return {
                "student": student, "performance_trend": [], "vs_class_avg": [],
                "blind_spots": [], "strengths": [],
                "overall_stats": {"total_exams": 0, "avg_percentage": 0, "highest": 0, "lowest": 0}
            }

        submissions.sort(key=lambda x: x.get("created_at", ""))

        performance_trend = []
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"exam_name": 1})
            performance_trend.append({
                "exam_name": exam.get("exam_name", "Unknown") if exam else "Unknown",
                "date": sub.get("created_at", ""),
                "percentage": sub["percentage"],
                "score": sub.get("total_score", 0)
            })

        exam_ids = [s["exam_id"] for s in submissions]
        vs_class_avg = await peer_group_service.get_student_vs_class_avg(student_id, exam_ids)

        topic_performance = {}

        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"questions": 1})
            if not exam:
                continue

            question_topics = {}
            for q in exam.get("questions", []):
                topics = q.get("topic_tags", ["General"])
                question_topics[q.get("question_number")] = topics

            for qs in sub.get("question_scores", []):
                q_num = qs.get("question_number")
                topics = question_topics.get(q_num, ["General"])
                percentage = (qs["obtained_marks"] / qs["max_marks"]) * 100 if qs.get("max_marks", 0) > 0 else 0

                for topic in topics:
                    if topic not in topic_performance:
                        topic_performance[topic] = []
                    topic_performance[topic].append(percentage)

        blind_spots = []
        strengths = []

        for topic, scores in topic_performance.items():
            avg = sum(scores) / len(scores)
            data = {"topic": topic, "avg_score": round(avg, 1), "attempts": len(scores)}
            if avg < 50:
                blind_spots.append(data)
            elif avg >= 70:
                strengths.append(data)

        return {
            "student": {
                "name": student.get("name", "Unknown"),
                "email": student.get("email", ""),
                "student_id": student.get("student_id", "")
            },
            "overall_stats": {
                "total_exams": len(submissions),
                "avg_percentage": round(sum(s["percentage"] for s in submissions) / len(submissions), 1),
                "highest": max(s["percentage"] for s in submissions),
                "lowest": min(s["percentage"] for s in submissions)
            },
            "performance_trend": performance_trend,
            "vs_class_avg": vs_class_avg,
            "blind_spots": sorted(blind_spots, key=lambda x: x["avg_score"]),
            "strengths": sorted(strengths, key=lambda x: x["avg_score"], reverse=True)
        }

    async def get_study_materials(self, user_id: str, subject_id: Optional[str] = None) -> Dict[str, Any]:
        """Get study material recommendations based on weak areas"""
        submissions = await self.submission_repo.find_submissions(
            {"student_id": user_id},
            limit=5,
            sort_field="created_at",
            sort_dir=-1,
            projection={"question_scores": 1, "exam_id": 1}
        )

        weak_topics = []
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"subject_id": 1})
            subject = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1}) if exam else None
            subj_name = subject.get("name", "General") if subject else "General"

            for qs in sub.get("question_scores", []):
                pct = (qs["obtained_marks"] / qs["max_marks"]) * 100 if qs["max_marks"] > 0 else 0
                if pct < 50:
                    weak_topics.append({
                        "subject": subj_name,
                        "question": f"Q{qs['question_number']}",
                        "score": f"{pct:.0f}%"
                    })

        materials = [
            {"title": "Practice Problems", "description": "Work through similar problems to strengthen weak areas", "type": "practice"},
            {"title": "Concept Review", "description": "Review fundamental concepts related to questions you struggled with", "type": "theory"},
            {"title": "Video Tutorials", "description": "Watch explanatory videos for complex topics", "type": "video"}
        ]

        return {"weak_topics": weak_topics[:10], "recommended_materials": materials}

dashboard_service = DashboardService()
