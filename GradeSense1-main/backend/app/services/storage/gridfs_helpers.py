"""
GridFS helpers for retrieving exam files (model answers, question papers).
"""

import pickle
from typing import List

from bson import ObjectId

from app.repositories import ExamRepo
from app.services.files import retrieve_images, get_file_from_gridfs
from app.core.logging_config import logger


exam_repo = ExamRepo()

async def get_exam_model_answer_images(exam_id: str) -> List[str]:
    """Get model answer images from GridFS or fallback to old storage"""
    # First try GridFS storage (new method)
    file_doc = await exam_repo.find_one_exam_file(
        {"exam_id": exam_id, "file_type": "model_answer"},
        projection={"_id": 0, "gridfs_id": 1, "images": 1}
    )
    
    if file_doc:
        logger.info(f"FETCH_FILE_DOC exam_id={exam_id} type=model_answer status=found")
        # Try GridFS first (new storage)
        if file_doc.get("gridfs_id"):
            try:
                imgs = retrieve_images(file_doc["gridfs_id"])
                if imgs:
                    logger.info(f"FETCH_IMAGES exam_id={exam_id} type=model_answer source=gridfs count={len(imgs)}")
                    return imgs
            except Exception as e:
                logger.error(f"Error retrieving from GridFS for {exam_id}: {e}")
        
        # Fallback to direct images storage (old method, still supported)
        if file_doc.get("images"):
            logger.info(f"FETCH_IMAGES exam_id={exam_id} type=model_answer source=file_doc_images count={len(file_doc['images'])}")
            return file_doc["images"]
    else:
        logger.warning(f"FETCH_FILE_DOC exam_id={exam_id} type=model_answer status=not_found")
    
    # Fallback to very old storage in exam document
    exam = await exam_repo.find_one_exam({"exam_id": exam_id}, projection={"_id": 0, "model_answer_images": 1})
    if exam and exam.get("model_answer_images"):
        logger.info(f"FETCH_IMAGES exam_id={exam_id} type=model_answer source=exam_doc count={len(exam['model_answer_images'])}")
        return exam["model_answer_images"]
    
    logger.warning(f"FETCH_IMAGES exam_id={exam_id} type=model_answer status=failed reason=no_images_found")
    return []

async def get_exam_question_paper_images(exam_id: str) -> List[str]:
    """Get question paper images from GridFS or fallback to old storage"""
    # First try GridFS storage (new method)
    file_doc = await exam_repo.find_one_exam_file(
        {"exam_id": exam_id, "file_type": "question_paper"},
        projection={"_id": 0, "gridfs_id": 1, "images": 1}
    )
    
    if file_doc:
        logger.info(f"FETCH_FILE_DOC exam_id={exam_id} type=question_paper status=found")
        # Try GridFS first (new storage)
        if file_doc.get("gridfs_id"):
            try:
                imgs = retrieve_images(file_doc["gridfs_id"])
                if imgs:
                    logger.info(f"FETCH_IMAGES exam_id={exam_id} type=question_paper source=gridfs count={len(imgs)}")
                    return imgs
            except Exception as e:
                logger.error(f"Error retrieving from GridFS for {exam_id}: {e}")
        
        # Fallback to direct images storage (old method, still supported)
        if file_doc.get("images"):
            logger.info(f"FETCH_IMAGES exam_id={exam_id} type=question_paper source=file_doc_images count={len(file_doc['images'])}")
            return file_doc["images"]
    else:
        logger.warning(f"FETCH_FILE_DOC exam_id={exam_id} type=question_paper status=not_found")
    
    # Fallback to very old storage in exam document
    exam = await exam_repo.find_one_exam({"exam_id": exam_id}, projection={"_id": 0, "question_paper_images": 1})
    if exam and exam.get("question_paper_images"):
        logger.info(f"FETCH_IMAGES exam_id={exam_id} type=question_paper source=exam_doc count={len(exam['question_paper_images'])}")
        return exam["question_paper_images"]
    
    logger.warning(f"FETCH_IMAGES exam_id={exam_id} type=question_paper status=failed reason=no_images_found")
    return []


async def get_exam_question_paper_pdf_bytes(exam_id: str) -> bytes:
    """Get original question paper PDF bytes from GridFS when available."""
    file_doc = await exam_repo.find_one_exam_file(
        {"exam_id": exam_id, "file_type": "question_paper_pdf"},
        projection={"_id": 0, "gridfs_id": 1},
    )
    if not file_doc or not file_doc.get("gridfs_id"):
        return b""
    try:
        return get_file_from_gridfs(file_doc["gridfs_id"]) or b""
    except Exception as e:
        logger.error(f"Error retrieving question paper PDF from GridFS: {e}")
        return b""

async def exam_has_model_answer(exam_id: str) -> bool:
    """Check if exam has model answer uploaded"""
    # Check new collection first
    file_doc = await exam_repo.find_one_exam_file(
        {"exam_id": exam_id, "file_type": "model_answer"},
        projection={"_id": 0}
    )
    if file_doc:
        return True
    
    # Fallback check
    exam = await exam_repo.find_one_exam({"exam_id": exam_id}, projection={"_id": 0, "model_answer_images": 1, "has_model_answer": 1})
    return bool(exam and (exam.get("has_model_answer") or exam.get("model_answer_images")))
