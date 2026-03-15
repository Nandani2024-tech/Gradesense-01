import os
import base64
from typing import List
from app.core.logging_config import logger
from app.services.file_processing.pdf_converter import pdf_to_images

def convert_to_images(file_bytes: bytes, filename: str = "") -> List[str]:
    """
    Convert an uploaded file (PDF or image) to a list of base64 image strings.
    """
    ext = os.path.splitext(filename)[1].lower() if filename else ""

    if ext == ".pdf" or (not ext and file_bytes[:5] == b"%PDF-"):
        return pdf_to_images(file_bytes)

    # Single image file
    try:
        img_base64 = base64.b64encode(file_bytes).decode()
        return [img_base64]
    except Exception as e:
        logger.error(f"Failed to convert file to image: {e}")
        return []
