"""
PDF-to-image conversion logic.
"""

import io
import base64
from typing import List, Optional

import fitz
from PIL import Image

from app.core.logging_config import logger
from .config import PDF_TO_IMAGES_ZOOM, PDF_TO_IMAGES_JPEG_QUALITY


def pdf_to_images(pdf_bytes: bytes, zoom: float = None, quality: int = None) -> List[str]:
    """Convert PDF pages to base64 images with compression - NO PAGE LIMIT"""
    
    # Use defaults from config if not provided
    effective_zoom = zoom if zoom is not None else PDF_TO_IMAGES_ZOOM
    effective_quality = quality if quality is not None else PDF_TO_IMAGES_JPEG_QUALITY
    
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    # Process ALL pages - no limit
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Configurable zoom for balance between quality and memory usage
        pix = page.get_pixmap(matrix=fitz.Matrix(effective_zoom, effective_zoom))
        img_bytes = pix.tobytes("jpeg")
        
        # Compress the image to save storage (40-60% reduction)
        img = Image.open(io.BytesIO(img_bytes))
        
        # Compress with configurable quality (good balance of quality vs size)
        compressed_buffer = io.BytesIO()
        img.save(compressed_buffer, format="JPEG", quality=effective_quality, optimize=True)
        compressed_bytes = compressed_buffer.getvalue()
        
        # Convert to base64
        img_base64 = base64.b64encode(compressed_bytes).decode()
        images.append(img_base64)
    
    doc.close()
    logger.info(f"Converted PDF with {len(images)} pages to compressed images")
    return images
