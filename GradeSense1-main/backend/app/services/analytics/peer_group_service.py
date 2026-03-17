from typing import List, Dict, Any, Optional
from app.repositories import SubmissionRepo, ExamRepo

class PeerGroupService:
    def __init__(self):
        self.submission_repo = SubmissionRepo()
        self.exam_repo = ExamRepo()

    async def get_student_vs_class_avg(self, student_id: str, exam_ids: List[str]) -> List[Dict[str, Any]]:
        """Compare student performance against class average for a set of exams"""
        vs_class_avg = []
        for eid in exam_ids:
            # Student score
            student_sub = await self.submission_repo.find_one_submission({"student_id": student_id, "exam_id": eid}, projection={"percentage": 1})
            if not student_sub:
                continue

            # Class average
            all_submissions = await self.submission_repo.find_submissions({"exam_id": eid}, projection={"percentage": 1})
            class_avg = 0
            if all_submissions:
                class_avg = sum(s["percentage"] for s in all_submissions) / len(all_submissions)
            
            exam = await self.exam_repo.find_one_exam({"exam_id": eid}, projection={"exam_name": 1})
            
            vs_class_avg.append({
                "exam_id": eid,
                "exam_name": exam.get("exam_name", "Unknown") if exam else "Unknown",
                "student_score": student_sub["percentage"],
                "class_avg": round(class_avg, 1),
                "difference": round(student_sub["percentage"] - class_avg, 1)
            })
        return vs_class_avg

peer_group_service = PeerGroupService()
