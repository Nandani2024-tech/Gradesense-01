from typing import List, Dict, Any, Optional
from app.repositories.search_repo import SearchRepo

class SearchService:
    def __init__(self):
        self.search_repo = SearchRepo()

    async def search_all(self, query: str, user: Any) -> Dict[str, Any]:
        """Unified search across multiple collections."""
        query = query.strip()
        results = {
            "exams": [],
            "students": [],
            "batches": [],
            "submissions": []
        }
        if not query or len(query) < 2:
            return results

        if user.role == "teacher":
            results["exams"] = await self.search_repo.search_exams(query, user.user_id)
            results["students"] = await self.search_repo.search_students(query, user.user_id)
            results["batches"] = await self.search_repo.search_batches(query, user.user_id)
            results["submissions"] = await self.search_repo.search_submissions(query, user.user_id)
        elif user.role == "student":
            # Students can only search their own data
            # For now, let's keep the existing logic or move it to repo
            from app.repositories import SubmissionRepo, ExamRepo
            submission_repo = SubmissionRepo()
            exam_repo = ExamRepo()
            
            subs = await submission_repo.find_submissions({"student_id": user.user_id}, limit=10, projection={"exam_id": 1, "submission_id": 1})
            if subs:
                exam_ids = [s["exam_id"] for s in subs]
                exam_details = await exam_repo.find_exams(
                    {"exam_id": {"$in": exam_ids}, "exam_name": {"$regex": query, "$options": "i"}},
                    limit=10,
                    projection={"_id": 0, "exam_id": 1, "exam_name": 1, "exam_date": 1}
                )
                results["exams"] = exam_details

        return results

search_service = SearchService()
