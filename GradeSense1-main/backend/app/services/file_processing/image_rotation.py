"""
Image rotation detection and correction logic.
"""

import io
import base64
from typing import List

from PIL import Image

from app.core.logging_config import logger


def detect_and_correct_rotation(image_base64: str) -> str:
    """
    Detect if an image is rotated and correct it.
    Uses PIL to analyze image orientation and rotate if needed.
    """
    try:
        # Decode base64 to image
        img_bytes = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(img_bytes))
        
        # Check EXIF orientation tag if available
        try:
            from PIL import ExifTags
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = img._getexif()
            if exif is not None:
                orientation_value = exif.get(orientation)
                if orientation_value == 3:
                    img = img.rotate(180, expand=True)
                elif orientation_value == 6:
                    img = img.rotate(270, expand=True)
                elif orientation_value == 8:
                    img = img.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            pass
        
        # Heuristic: Check if image is landscape but contains portrait text
        # Most answer sheets are portrait, so if width > height significantly, it might be rotated
        width, height = img.size
        # Use existing logic from original file_processing.py
        if width > height * 1.3:  # Landscape orientation
            # Rotate 90 degrees counter-clockwise to make it portrait
            img = img.rotate(90, expand=True)
            logger.info(f"Rotated landscape image to portrait")
        
        # Convert back to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode()
        
    except Exception as e:
        logger.error(f"Error in rotation detection: {e}")
        return image_base64  # Return original if detection fails


def correct_all_images_rotation(images: List[str]) -> List[str]:
    """Apply rotation correction to all images in a list."""
    corrected = []
    for idx, img in enumerate(images):
        corrected_img = detect_and_correct_rotation(img)
        corrected.append(corrected_img)
    return corrected
