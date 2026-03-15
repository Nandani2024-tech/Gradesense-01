from typing import Tuple

try:
    import cv2
except ImportError:
    cv2 = None


def _table_like(binary_inv, bbox: Tuple[int, int, int, int]) -> bool:
    x, y, w, h = bbox
    roi = binary_inv[y : y + h, x : x + w]
    if roi.size == 0:
        return False
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 12), 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 8)))
    h_lines = cv2.morphologyEx(roi, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(roi, cv2.MORPH_OPEN, v_kernel)
    line_pixels = cv2.countNonZero(h_lines) + cv2.countNonZero(v_lines)
    density = line_pixels / float(max(1, w * h))
    return density >= 0.045
