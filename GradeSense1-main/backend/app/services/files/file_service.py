"""
File Service for managing GridFS storage and Google Drive downloads.
"""

import pickle
import uuid
from typing import Optional, List, Tuple

from bson import ObjectId
from app.infrastructure.storage.gridfs_storage import fs
from app.utils.file_utils import (
    download_from_google_drive, 
    extract_file_id_from_url,
    convert_to_images,
    extract_zip_files
)
from app.core.logging_config import logger

def upload_file_to_gridfs(file_bytes: bytes, filename: str, content_type: str, **metadata) -> str:
    """
    Upload generic file bytes to GridFS and return the GridFS ID.
    """
    try:
        gridfs_id = fs.put(
            file_bytes,
            filename=filename,
            content_type=content_type,
            **metadata
        )
        return str(gridfs_id)
    except Exception as e:
        logger.error(f"Failed to upload file to GridFS: {e}")
        raise

def get_file_from_gridfs(gridfs_id: str) -> Optional[bytes]:
    """
    Retrieve file bytes from GridFS using the GridFS ID string.
    """
    try:
        oid = ObjectId(gridfs_id)
        if fs.exists(oid):
            grid_out = fs.get(oid)
            return grid_out.read()
        return None
    except Exception as e:
        logger.error(f"Error retrieving file from GridFS ({gridfs_id}): {e}")
        return None

def store_images(images: List, filename: str, **metadata) -> str:
    """
    Serialize images list and store in GridFS. Returns GridFS ID.
    """
    try:
        images_data = pickle.dumps(images)
        gridfs_id = fs.put(
            images_data,
            filename=filename,
            content_type="application/python-pickle",
            **metadata
        )
        return str(gridfs_id)
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
    try:
        return fs.exists(ObjectId(gridfs_id))
    except Exception:
        return False

async def convert_file_to_images(file_bytes: bytes, file_type: str) -> List:
    """
    Convert file bytes to images list.
    """
    from app.utils.concurrency import conversion_semaphore
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
        for grid_file in fs.find({"exam_id": exam_id}):
            fs.delete(grid_file._id)
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
