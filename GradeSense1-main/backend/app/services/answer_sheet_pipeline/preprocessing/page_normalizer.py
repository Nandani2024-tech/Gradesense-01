from typing import List
from app.core.logging_config import logger
from app.services.answer_sheet_pipeline.image_utils import _b64_to_cv2, _cv2_to_b64

try:
    import cv2
except ImportError:
    cv2 = None


def normalize_answer_pages(images: List[str]) -> List[str]:
    """Stage 2 normalization over already-rendered pages."""
    cleaned: List[str] = []
    for image_b64 in images:
        try:
            bgr = _b64_to_cv2(image_b64)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

            # Shadow suppression + contrast.
            blur = cv2.GaussianBlur(gray, (3, 3), 0)
            bg = cv2.medianBlur(blur, 25)
            norm = cv2.divide(blur, bg, scale=255)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(norm)

            # Deskew by minimum-area rectangle angle from foreground pixels.
            th = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            coords = cv2.findNonZero(th)
            if coords is not None and len(coords) > 500:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = 90 + angle
                if abs(angle) > 0.1:
                    h, w = enhanced.shape[:2]
                    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                    enhanced = cv2.warpAffine(
                        enhanced,
                        m,
                        (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE,
                    )

            out = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            cleaned.append(_cv2_to_b64(out, quality=88))
        except Exception as e:
            logger.warning("Answer normalization failed for a page; using original. err=%s", e)
            cleaned.append(image_b64)
    return cleaned
