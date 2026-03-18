"""
File Service for managing GridFS storage and Google Drive downloads.
"""

import pickle
import uuid
from typing import Optional, List, Tuple

from bson import ObjectId
from app.infrastructure.storage.gridfs_storage import fs
from app.infrastructure.files.converters import convert_to_images
from app.infrastructure.files.zip_handler import extract_zip_files
from app.infrastructure.files.gdrive import extract_file_id_from_url, download_from_google_drive
from app.core.logging_config import logger
from app.core.exceptions import CustomServiceException
from app.repositories import FileRepo

file_repo = FileRepo()

def upload_file_to_gridfs(file_bytes: bytes, filename: str, content_type: str, **metadata) -> str:
    """
    Upload generic file bytes to GridFS and return the GridFS ID.
    """
    try:
        gridfs_id = file_repo.put(
            file_bytes,
            filename=filename,
            content_type=content_type,
            **metadata
        )
        return gridfs_id
    except Exception as e:
        logger.error(f"Failed to upload file to GridFS: {e}")
        raise

def get_file_from_gridfs(gridfs_id: str) -> Optional[bytes]:
    """
    Retrieve file bytes from GridFS using the GridFS ID string.
    """
    return file_repo.get(gridfs_id)

def store_images(images: List, filename: str, **metadata) -> str:
    """
    Serialize images list and store in GridFS. Returns GridFS ID.
    """
    try:
        images_data = pickle.dumps(images)
        gridfs_id = file_repo.put(
            images_data,
            filename=filename,
            content_type="application/python-pickle",
            **metadata
        )
        return gridfs_id
    except Exception as e:
        logger.error(f"Failed to store images in GridFS: {e}")
        raise

def retrieve_images(gridfs_id: str) -> List:
    """
    Retrieve and deserialize images list from GridFS.
    """
    try:
        file_bytes = get_file_from_gridfs(gridfs_id)
        if file_bytes:
            return pickle.loads(file_bytes)
        return []
    except Exception as e:
        logger.error(f"Error deserializing images from GridFS ({gridfs_id}): {e}")
        return []

def download_drive_file(link: str) -> Tuple[Optional[bytes], str]:
    """
    Download file from Google Drive link.
    Returns (content_bytes, file_type).
    """
    file_id = extract_file_id_from_url(link)
    if not file_id:
        return None, ""
    
    try:
        # Note: current download_from_google_drive utility only returns bytes
        # In a real scenario, we might want to detect mime type properly.
        # For now, following existing logic pattern.
        file_bytes = download_from_google_drive(file_id)
        # Fallback to pdf if type cannot be determined easily from bytes alone here
        return file_bytes, "pdf" 
    except Exception as e:
        logger.error(f"Failed to download from Drive link: {e}")
        return None, ""

def file_exists(gridfs_id: str) -> bool:
    """Check if file exists in GridFS"""
    return file_repo.exists(gridfs_id)

async def convert_file_to_images(file_bytes: bytes, file_type: str) -> List:
    """
    Convert file bytes to images list.
    """
    from app.infrastructure.concurrency import conversion_semaphore
    import asyncio
    async with conversion_semaphore:
        return await asyncio.to_thread(convert_to_images, file_bytes, file_type)

def extract_zip(file_bytes: bytes) -> List[Tuple[str, bytes, str]]:
    """
    Extract files from ZIP.
    """
    return extract_zip_files(file_bytes)

def delete_files_by_exam_id(exam_id: str) -> int:
    """
    Delete all files associated with an exam_id from GridFS.
    Returns count of deleted files.
    """
    count = 0
    try:
        for grid_file in file_repo.find({"exam_id": exam_id}):
            file_repo.delete(str(grid_file._id))
            count += 1
        return count
    except Exception as e:
        logger.error(f"Error deleting GridFS files for exam {exam_id}: {e}")
        return count

async def pdf_to_images(pdf_bytes: bytes, zoom: float = None, quality: int = None) -> List[str]:
    """
    Exposes pdf_to_images as a service method.
    """
    from app.services.file_processing.pdf_converter import pdf_to_images as _pdf_to_images
    import asyncio
    return await asyncio.to_thread(_pdf_to_images, pdf_bytes, zoom, quality)

def pdf_to_clean_images(pdf_bytes: bytes, dpi: int = 300) -> List[str]:
    """
    Exposes pdf_to_clean_images as a service method.
    """
    from app.services.answer_sheet_pipeline.preprocessing.pdf_image_converter import pdf_to_clean_images as _pdf_to_clean_images
    return _pdf_to_clean_images(pdf_bytes, dpi=dpi)

def upload_exam_document(exam_id: str, file_bytes: bytes, content_type: str, prefix: str) -> str:
    """Helper for uploading exam documents (QP/MA)."""
    file_ref = f"{prefix}_{exam_id}"
    upload_file_to_gridfs(file_bytes, filename=file_ref, content_type=content_type)
    return file_ref

def upload_student_submission_file(exam_id: str, student_id: str, file_bytes: bytes, content_type: str) -> str:
    """Helper for uploading student submission file."""
    file_ref = f"ans_{exam_id}_{student_id}"
    upload_file_to_gridfs(file_bytes, filename=file_ref, content_type=content_type)
    return file_ref

async def _process_file_to_images(file_bytes: bytes, file_type: str) -> List:
    """Internal helper to handle ZIP or single file to images transition."""
    if file_type in ['zip', 'application/zip', 'application/x-zip-compressed']:
        all_images = []
        extracted_files = extract_zip(file_bytes)
        for filename, bts, tp in extracted_files:
            try:
                images = await convert_file_to_images(bts, tp)
                all_images.extend(images)
            except Exception: continue
        if not all_images:
            raise CustomServiceException(status_code=400, message="No valid files found in ZIP")
        return all_images
    else:
        return await convert_file_to_images(file_bytes, file_type)

async def process_and_store_model_answer(exam_id: str, file_bytes: bytes, file_type: str) -> Tuple[str, int, str]:
    """Process model answer file and store in GridFS."""
    images = await _process_file_to_images(file_bytes, file_type)
    file_id_str = str(uuid.uuid4())
    gridfs_id = store_images(
        images,
        filename=f"model_answer_{exam_id}_{file_id_str}",
        exam_id=exam_id,
        file_type="model_answer"
    )
    return file_id_str, len(images), str(gridfs_id)

async def process_and_store_question_paper(exam_id: str, file_bytes: bytes, file_type: str) -> Tuple[str, int, str]:
    """Process question paper file and store in GridFS."""
    images = await _process_file_to_images(file_bytes, file_type)
    file_id_str = str(uuid.uuid4())
    gridfs_id = store_images(
        images,
        filename=f"question_paper_{exam_id}_{file_id_str}",
        exam_id=exam_id,
        file_type="question_paper"
    )
    return file_id_str, len(images), str(gridfs_id)

def is_valid_answer_pdf(filename: str, pdf_bytes: bytes) -> bool:
    """
    Check if a file is a valid answer-sheet PDF.
    """
    # Simple check for now: must be PDF and have some content
    return filename.lower().endswith('.pdf') and len(pdf_bytes) > 0
