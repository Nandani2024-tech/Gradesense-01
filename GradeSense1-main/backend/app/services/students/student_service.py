import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from app.core.exceptions import CustomServiceException

from app.repositories import StudentRepo, SubmissionRepo, ExamRepo, AnalyticsRepo
from app.core.logging_config import logger

class StudentService:
    def __init__(self):
        self.student_repo = StudentRepo()
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()
        self.analytics_repo = AnalyticsRepo()

    async def create_student(
        self,
        email: str,
        name: str,
        batches: List[str],
        teacher_id: str,
        student_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new student record."""
        if student_id:
            student_id = student_id.strip()
            # Check if student ID already exists
            existing_id = await self.student_repo.get_student_by_id(student_id)
            if existing_id:
                raise CustomServiceException(
                    status_code=400,
                    message=f"Student ID {student_id} already exists"
                )
        else:
            # Auto-generate student ID
            student_id = f"STU{uuid.uuid4().hex[:6].upper()}"

        # Check if email already exists
        existing = await self.student_repo.get_student_by_email(email)
        if existing:
            raise CustomServiceException(status_code=400, message="Student with this email already exists")

        user_id = f"user_{uuid.uuid4().hex[:12]}"

        new_student = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "role": "student",
            "student_id": student_id,
            "batches": batches,
            "teacher_id": teacher_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.student_repo.insert_student(new_student)

        # Add student to batches
        for batch_id in batches:
            await self.analytics_repo.update_batch(
                {"batch_id": batch_id},
                {"$addToSet": {"students": user_id}}
            )

        return {
            "user_id": user_id,
            "student_id": student_id,
            "email": email,
            "name": name,
            "batches": batches
        }
    async def update_student(self, student_user_id: str, student_data: Dict[str, Any]) -> None:
        """Update student details."""
        result = await self.student_repo.update_student(
            student_user_id,
            {"$set": {
                "name": student_data.get("name"),
                "email": student_data.get("email"),
                "student_id": student_data.get("student_id"),
                "batches": student_data.get("batches")
            }}
        )
        if result.matched_count == 0:
            raise CustomServiceException(status_code=404, message="Student not found")

    async def delete_student(self, student_user_id: str, teacher_id: str) -> None:
        """Delete a student record."""
        result = await self.student_repo.delete_student(student_user_id)
        if result.deleted_count == 0:
            raise CustomServiceException(status_code=404, message="Student not found")

    async def get_students(self, teacher_id: str, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get students managed by a teacher."""
        query = {"role": "student", "teacher_id": teacher_id}
        if batch_id:
            query["batches"] = batch_id
        return await self.student_repo.find_students(query, limit=500)

    async def get_my_exams(self, student_user_id: str) -> List[Dict[str, Any]]:
        """Get exams assigned to a student for submission."""
        # Find exams where this student is assigned and exam is in student-upload mode
        exams = await self.exam_repo.find_exams(
            {
                "students": student_user_id,
                "is_student_upload": True
            },
            limit=100
        )

        # Enrichment logic
        for exam in exams:
            submission = await self.submission_repo.find_one_submission(
                {
                    "exam_id": exam["exam_id"],
                    "student_id": student_user_id
                },
                projection={"submission_id": 1, "status": 1, "percentage": 1, "obtained_marks": 1, "total_marks": 1}
            )

            if submission:
                exam["submitted"] = True
                exam["submission_status"] = submission.get("status", "submitted")
                exam["score"] = submission.get("percentage")
                exam["submission_id"] = submission.get("submission_id")
            else:
                exam["submitted"] = False
                exam["submission_status"] = "pending"

        return exams

    async def get_student_detail(self, student_user_id: str) -> Dict[str, Any]:
        """Get detailed student information with performance analytics."""
        student = await self.student_repo.get_student_by_id(student_user_id)
        if not student:
            raise CustomServiceException(status_code=404, message="Student not found")

        # Get all submissions for this student
        submissions = await self.submission_repo.find_submissions(
            {"student_id": student_user_id},
            limit=100
        )

        # Calculate overall stats
        if submissions:
            percentages = [s.get("percentage", 0) for s in submissions]
            avg_percentage = sum(percentages) / len(percentages)
            highest = max(percentages)
            lowest = min(percentages)

            # Trend calculation
            sorted_subs = sorted(submissions, key=lambda x: x.get("created_at", ""))
            if len(sorted_subs) >= 2:
                recent = sorted_subs[-min(5, len(sorted_subs)):]
                recent_avg = sum(s.get("percentage", 0) for s in recent) / len(recent)
                if len(sorted_subs) > 5:
                    older = sorted_subs[-min(10, len(sorted_subs)):-5]
                    older_avg = sum(s.get("percentage", 0) for s in older) / len(older) if older else recent_avg
                    trend = recent_avg - older_avg
                else:
                    trend = 0
            else:
                trend = 0
        else:
            avg_percentage = highest = lowest = trend = 0

        # Subject-wise performance
        subject_performance = {}
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"subject_id": 1})
            if exam:
                subj = await self.analytics_repo.find_one_subject({"subject_id": exam["subject_id"]}, projection={"name": 1})
                subj_name = subj.get("name", "Unknown") if subj else "Unknown"
                if subj_name not in subject_performance:
                    subject_performance[subj_name] = {"scores": [], "total_exams": 0}
                subject_performance[subj_name]["scores"].append(sub.get("percentage", 0))
                subject_performance[subj_name]["total_exams"] += 1

        for subj_name, data in subject_performance.items():
            data["average"] = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            data["highest"] = max(data["scores"]) if data["scores"] else 0
            data["lowest"] = min(data["scores"]) if data["scores"] else 0

        # Topic-based performance analysis
        topic_performance = {}
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]})
            if not exam: continue

            exam_name = exam.get("exam_name", "Unknown Exam")
            exam_date = sub.get("created_at", "")
            exam_questions = exam.get("questions", [])

            question_topics = {}
            for q in exam_questions:
                q_num = q.get("question_number")
                topics = q.get("topic_tags", [])
                if not topics:
                    subj = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1})
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
                        "exam_name": exam_name,
                        "question_number": q_num
                    })

        weak_topics = []
        strong_topics = []
        for topic, performances in topic_performance.items():
            if not performances: continue
            sorted_perfs = sorted(performances, key=lambda x: x.get("exam_date", ""))
            avg_score = sum(p["score"] for p in sorted_perfs) / len(sorted_perfs)

            topic_trend = 0
            trend_text = "stable"
            if len(sorted_perfs) >= 2:
                mid = len(sorted_perfs) // 2
                first_half_avg = sum(p["score"] for p in sorted_perfs[:mid]) / mid if mid > 0 else 0
                second_half_avg = sum(p["score"] for p in sorted_perfs[mid:]) / (len(sorted_perfs) - mid)
                topic_trend = second_half_avg - first_half_avg
                if topic_trend > 10: trend_text = "improving"
                elif topic_trend < -10: trend_text = "declining"

            topic_data = {
                "topic": topic,
                "avg_score": round(avg_score, 1),
                "total_attempts": len(sorted_perfs),
                "trend": round(topic_trend, 1),
                "trend_text": trend_text,
                "recent_score": round(sorted_perfs[-1]["score"], 1) if sorted_perfs else 0,
                "first_score": round(sorted_perfs[0]["score"], 1) if sorted_perfs else 0
            }
            if avg_score < 50: weak_topics.append(topic_data)
            elif avg_score >= 75: strong_topics.append(topic_data)

        weak_topics = sorted(weak_topics, key=lambda x: x["avg_score"])[:5]
        strong_topics = sorted(strong_topics, key=lambda x: -x["avg_score"])[:5]

        recommendations = []
        declining_topics = [t for t in weak_topics if t["trend_text"] == "declining"]
        if declining_topics:
            recommendations.append(f"⚠️ {declining_topics[0]['topic']} needs urgent attention - performance is declining")
        improving_weak = [t for t in weak_topics if t["trend_text"] == "improving"]
        if improving_weak:
            recommendations.append(f"📈 Great progress in {improving_weak[0]['topic']}! Keep practicing to master it")
        stable_weak = [t for t in weak_topics if t["trend_text"] == "stable" and t["total_attempts"] >= 2]
        if stable_weak:
            recommendations.append(f"💡 Focus more on {stable_weak[0]['topic']} - needs consistent practice")
        if strong_topics:
            recommendations.append(f"⭐ Excellent in {strong_topics[0]['topic']}! Consider helping peers")

        if not recommendations:
            recommendations = [
                "Complete more exams to get detailed topic insights",
                "Focus on understanding concepts deeply",
                "Practice regularly across all topics"
            ]

        return {
            "student": student,
            "stats": {
                "total_exams": len(submissions),
                "avg_percentage": round(avg_percentage, 1),
                "highest_score": highest,
                "lowest_score": lowest,
                "trend": round(trend, 1)
            },
            "subject_performance": subject_performance,
            "recent_submissions": submissions[-10:],
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
            "topic_performance": topic_performance,
            "recommendations": recommendations
        }

    async def get_student_analytics(self, student_id: str) -> Dict[str, Any]:
        """Get analytics for a specific student."""
        student = await self.student_repo.get_student_by_id(student_id)
        if not student:
            raise CustomServiceException(status_code=404, message="Student not found")

        submissions = await self.submission_repo.find_submissions(
            {"student_id": student_id},
            limit=100
        )

        if submissions:
            percentages = [s.get("percentage", 0) for s in submissions]
            avg = sum(percentages) / len(percentages)
            highest = max(percentages)
            lowest = min(percentages)
        else:
            avg = highest = lowest = 0

        enriched_submissions = []
        for sub in submissions:
            exam = await self.exam_repo.find_one_exam({"exam_id": sub["exam_id"]}, projection={"exam_name": 1, "subject_id": 1})
            if exam:
                sub["exam_name"] = exam.get("exam_name", "Unknown")
                subj = await self.analytics_repo.find_one_subject({"subject_id": exam.get("subject_id")}, projection={"name": 1})
                sub["subject_name"] = subj.get("name", "Unknown") if subj else "Unknown"
            enriched_submissions.append(sub)

        return {
            "student": student,
            "stats": {
                "total_exams": len(submissions),
                "avg_percentage": round(avg, 1),
                "highest_score": highest,
                "lowest_score": lowest
            },
            "submissions": enriched_submissions
        }

    async def get_or_create_student(
        self,
        student_id: str,
        name: str,
        batch_id: str,
        teacher_id: str
    ) -> Tuple[str, bool]:
        """
        Get existing student by human-readable student_id or create a new one.
        Returns: (user_id, created_flag)
        """
        # Search by student_id field (alphanumeric ID assigned by teacher/school)
        existing = await self.student_repo.find_students(
            {"student_id": student_id, "teacher_id": teacher_id},
            limit=1
        )
        if existing:
            return existing[0]["user_id"], False

        # Create new student if not found
        new_student = await self.create_student(
            email=f"{student_id.lower()}_{uuid.uuid4().hex[:4]}@gradesense.auto",
            name=name,
            batches=[batch_id],
            teacher_id=teacher_id,
            student_id=student_id
        )
        return new_student["user_id"], True

    async def identify_student(self, images: List[Any], filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Identify student from paper images and filename."""
        from app.student import extract_student_info_from_paper, parse_student_from_filename
        from app.services.llm_provider import get_llm_service
        
        # Instantiate LLM service for student info extraction
        llm_service = get_llm_service()
        
        # Call extraction utility - DISABLED FOR LEGACY, handled by Orchestrator
        # info = await extract_student_info_from_paper(images, llm_service)
        # student_id = info.get("student_id")
        # student_name = info.get("student_name")
        student_id = None
        student_name = None

        if not student_id or not student_name:
            filename_id, filename_name = parse_student_from_filename(filename)
            if not student_id and filename_id:
                student_id = filename_id
            if not student_name and filename_name:
                student_name = filename_name
                
        return student_id, student_name

    async def orchestrate_student_id(
        self,
        file_content: Optional[bytes] = None, 
        filename: Optional[str] = None, 
        batch_id: Optional[str] = None, 
        teacher_id: Optional[str] = None,
        images: Optional[List[Any]] = None
    ) -> Tuple[str, str, str]:
        """
        Orchestrates full student identification flow:
        1. Extracts images from PDF (if not provided).
        2. Identifies student via AI/filename.
        3. Resolves to a database user_id.
        4. Falls back to AUTO_ tags if identification fails.
        
        Returns: (user_id, student_id, student_name)
        """
        from app.services.answer_sheet_pipeline import pdf_to_clean_images
        
        student_id = None
        student_name = None
        
        try:
            # Get images for ID extraction if not provided
            if not images and file_content:
                images = await asyncio.to_thread(pdf_to_clean_images, file_content, normalize=True)
            
            if images and filename:
                logger.info("Phase 3 orchestrator will handle student identification for this submission")
                # student_id, student_name = await self.identify_student(images, filename)
        except Exception as e:
            logger.warning(f"Student identification failed for {filename}: {e}")

        # Fallbacks
        if not student_id:
            student_id = f"AUTO_{uuid.uuid4().hex[:6].upper()}"
        if not student_name:
            student_name = f"Student {student_id}"

        # Resolve to DB user
        if batch_id and teacher_id:
            user_id, _ = await self.get_or_create_student(student_id, student_name, batch_id, teacher_id)
        else:
            user_id = student_id # Fallback if no batch context
            
        return user_id, student_id, student_name

student_service = StudentService()
