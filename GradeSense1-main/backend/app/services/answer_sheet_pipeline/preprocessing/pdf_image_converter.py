import base64
import gc
import io
from typing import List, Optional

from app.core.logging_config import logger
from app.services.answer_sheet_pipeline.config import PDF_IMAGE_BATCH_PAGES, PDF_IMAGE_JPEG_QUALITY, PDF_IMAGE_NORMALIZE
from app.services.answer_sheet_pipeline.preprocessing.page_normalizer import normalize_answer_pages
from app.services.answer_sheet_pipeline.image_utils import _HAS_CV2

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

try:
    from pdf2image import convert_from_bytes, pdfinfo_from_bytes
except ImportError:
    convert_from_bytes = None  # type: ignore
    pdfinfo_from_bytes = None  # type: ignore


def _get_pdf_page_count(pdf_bytes: bytes) -> Optional[int]:
    if pdfinfo_from_bytes is not None:
        try:
            info = pdfinfo_from_bytes(pdf_bytes)
            pages = int(info.get("Pages", 0) or 0)
            if pages > 0:
                return pages
        except Exception as e:
            logger.warning("pdfinfo_from_bytes failed; falling back. err=%s", e)
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages = int(doc.page_count)
            doc.close()
            return pages if pages > 0 else None
        except Exception as e:
            logger.warning("PyMuPDF page count failed; falling back. err=%s", e)
    return None


def pdf_to_clean_images(pdf_bytes: bytes, dpi: int = 300, normalize: Optional[bool] = None) -> List[str]:
    """Stage 2 from raw PDF bytes using pdf2image at target DPI, batched to reduce memory."""
    if convert_from_bytes is None:
        raise RuntimeError("pdf2image is not available")

    if normalize is None:
        normalize = PDF_IMAGE_NORMALIZE
    if normalize and not _HAS_CV2:
        logger.warning("cv2 not available; skipping normalization")
        normalize = False

    images: List[str] = []
    page_count = _get_pdf_page_count(pdf_bytes)
    batch_size = max(1, int(PDF_IMAGE_BATCH_PAGES or 1))

    def _encode_pages(pages) -> List[str]:
        encoded: List[str] = []
        for page in pages:
            buf = io.BytesIO()
            page.save(buf, format="JPEG", quality=PDF_IMAGE_JPEG_QUALITY, optimize=True)
            encoded.append(base64.b64encode(buf.getvalue()).decode())
        return encoded

    if not page_count:
        pil_pages = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="jpeg")
        images = _encode_pages(pil_pages)
        return normalize_answer_pages(images) if normalize else images

    for start in range(1, page_count + 1, batch_size):
        end = min(page_count, start + batch_size - 1)
        pil_pages = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            fmt="jpeg",
            first_page=start,
            last_page=end,
        )
        batch_images = _encode_pages(pil_pages)
        if normalize:
            batch_images = normalize_answer_pages(batch_images)
        images.extend(batch_images)
        del pil_pages
        del batch_images
        gc.collect()
    return images
