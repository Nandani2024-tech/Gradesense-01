from typing import List, Dict, Any, Optional
from app.core.database import db
from app.core.logging_config import logger

class ExamRepo:
    def __init__(self):
        self.collection = db.exams
        self.questions_collection = db.questions
        self.files_collection = db.exam_files

    async def find_exams(self, query: Dict[str, Any], limit: int = 100, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find exams based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find(query, projection).to_list(limit)

    async def find_one_exam(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single exam."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find_one(query, projection)

    async def insert_exam(self, doc: Dict[str, Any]) -> Any:
        """Insert a new exam."""
        logger.info("DB_WRITE_START entity=exam action=insert exam_id=%s", doc.get("exam_id"))
        result = await self.collection.insert_one(doc)
        logger.info("DB_WRITE_SUCCESS entity=exam action=insert exam_id=%s", doc.get("exam_id"))
        return result

    async def update_exam(self, exam_id: str, update_doc: Dict[str, Any], query_override: Optional[Dict[str, Any]] = None) -> Any:
        """Update exam record."""
        query = query_override or {"exam_id": exam_id}
        logger.info("DB_WRITE_START entity=exam action=update exam_id=%s", exam_id)
        result = await self.collection.update_one(query, update_doc)
        logger.info("DB_WRITE_SUCCESS entity=exam action=update exam_id=%s", exam_id)
        return result

    async def delete_exam_by_id(self, exam_id: str, teacher_id: str) -> Any:
        """Delete an exam from the collection."""
        logger.info("DB_WRITE_START entity=exam action=delete exam_id=%s", exam_id)
        result = await self.collection.delete_one({"exam_id": exam_id, "teacher_id": teacher_id})
        logger.info("DB_WRITE_SUCCESS entity=exam action=delete exam_id=%s", exam_id)
        return result

    async def delete_exam_files_by_exam_id(self, exam_id: str) -> Any:
        """Delete all file records associated with an exam."""
        return await self.files_collection.delete_many({"exam_id": exam_id})

    async def update_exam_file(self, query: Dict[str, Any], update_doc: Dict[str, Any]) -> Any:
        """Update an exam file record."""
        exam_id = query.get("exam_id")
        logger.info("DB_WRITE_START entity=exam_file action=update exam_id=%s", exam_id)
        result = await self.files_collection.update_one(query, update_doc, upsert=True)
        logger.info("DB_WRITE_SUCCESS entity=exam_file action=update exam_id=%s", exam_id)
        return result

    async def count_exams(self, query: Dict[str, Any]) -> int:
        """Count exams based on query."""
        return await self.collection.count_documents(query)

    async def find_one_question(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single question."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.questions_collection.find_one(query, projection)

    async def find_questions(self, query: Dict[str, Any], limit: int = 1000, projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find questions based on query."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.questions_collection.find(query, projection).to_list(limit)

    async def delete_questions(self, query: Dict[str, Any]) -> Any:
        """Delete questions based on query."""
        return await self.questions_collection.delete_many(query)

    async def insert_questions(self, docs: List[Dict[str, Any]]) -> Any:
        """Insert multiple questions."""
        exam_id = docs[0].get("exam_id") if docs else "N/A"
        logger.info("DB_WRITE_START entity=questions action=insert exam_id=%s count=%s", exam_id, len(docs))
        result = await self.questions_collection.insert_many(docs)
        logger.info("DB_WRITE_SUCCESS entity=questions action=insert exam_id=%s", exam_id)
        return result

    async def find_one_exam_file(self, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find a single exam file record."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.files_collection.find_one(query, projection)

    async def insert_blueprint_version(self, doc: Dict[str, Any]) -> Any:
        """Insert a new blueprint version snapshot."""
        return await db.exam_blueprint_versions.insert_one(doc)

    async def update_blueprint_version_upsert(self, exam_id: str, version: int, doc: Dict[str, Any]) -> Any:
        """Upsert a blueprint version snapshot."""
        return await db.exam_blueprint_versions.update_one(
            {"exam_id": exam_id, "blueprint_version": version},
            {"$setOnInsert": doc},
            upsert=True
        )

    async def find_one_and_update_exam(self, query: Dict[str, Any], update_doc: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Find and update an exam atomically."""
        if projection and "_id" not in projection:
            projection["_id"] = 0
        elif not projection:
            projection = {"_id": 0}
        return await self.collection.find_one_and_update(query, update_doc, projection=projection, return_document=True)
