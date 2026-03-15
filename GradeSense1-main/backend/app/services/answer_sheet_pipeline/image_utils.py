import base64
from typing import List

_HAS_CV2 = True
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore
    _HAS_CV2 = False


def _b64_to_cv2(image_base64: str) -> "np.ndarray":
    data = base64.b64decode(image_base64)
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode base64 image")
    return img


def _cv2_to_b64(img: "np.ndarray", quality: int = 85) -> str:
    ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("Failed to encode image")
    return base64.b64encode(enc.tobytes()).decode()


def _crop_b64(image_b64: str, bbox: List[float]) -> str:
    bgr = _b64_to_cv2(image_b64)
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, min(w - 1, x1))
    y1 = max(0, min(h - 1, y1))
    x2 = max(x1 + 1, min(w, x2))
    y2 = max(y1 + 1, min(h, y2))
    roi = bgr[y1:y2, x1:x2]
    return _cv2_to_b64(roi, quality=90)
