"""Image rendering logic and drawing helpers for annotations."""

# renderer.py
import io
import math
import random
import base64
from typing import List
from PIL import Image, ImageDraw, ImageFont

from .types import Annotation, AnnotationType
from .color_utils import _parse_color

def apply_annotations_to_image(image_base64: str, annotations: List[Annotation]) -> str:
    """
    Draw annotations onto a base64-encoded image and return the result as base64.
    Renders in a realistic examiner pen style.
    """
    try:
        img_bytes = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        img_w, img_h = img.size

        for ann in annotations:
            x, y = int(ann.x), int(ann.y)
            color = ann.color or "red"

            # Skip per-question score circles and their "Marks:" labels
            if ann.annotation_type == AnnotationType.SCORE_CIRCLE:
                continue
            if ann.annotation_type == AnnotationType.MARGIN_NOTE and ann.text and ann.text.startswith("Marks:"):
                continue

            if ann.annotation_type == AnnotationType.CHECKMARK:
                _draw_checkmark(draw, x, y, color, ann.size, img_w)

            elif ann.annotation_type == AnnotationType.CROSS_MARK:
                _draw_cross(draw, x, y, color, ann.size, img_w)

            elif ann.annotation_type == AnnotationType.ERROR_UNDERLINE:
                w = ann.size if ann.size > 24 else 100
                _draw_underline(draw, x, y, w, color)

            elif ann.annotation_type == AnnotationType.HIGHLIGHT_BOX:
                w = ann.width or 200
                h = ann.height or 40
                _draw_highlight_box(draw, x, y, w, h, color)

            elif ann.annotation_type in (AnnotationType.COMMENT, AnnotationType.MARGIN_NOTE):
                _draw_margin_comment(draw, x, y, ann.text, color, ann.size, img_w, img_h)

            elif ann.annotation_type == AnnotationType.POINT_NUMBER:
                _draw_text(draw, x, y, ann.text, color, ann.size)

            elif ann.annotation_type == AnnotationType.MARGIN_BRACKET:
                h = ann.height or 40
                _draw_margin_bracket(draw, x, y, h, ann.text, color, ann.size, img_w)

            elif ann.annotation_type == AnnotationType.TOTAL_SCORE:
                _draw_total_score(draw, ann.text, color, img_w)

        result = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode()

    except Exception:
        return image_base64

# --- Private drawing helpers ---

def _get_font(size: int):
    """Try to load a good font, fallback to default."""
    paths = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",       # macOS
        "/System/Library/Fonts/Helvetica.ttc",                 # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",# Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",    # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()

def _draw_checkmark(draw: ImageDraw.Draw, x: int, y: int, color: str, size: int, img_w: int = 0):
    rgba = _parse_color(color if "green" in str(color).lower() or str(color).startswith("#0") else "green")
    margin_x = min(x, 35)
    s = max(size, 28)
    p1 = (margin_x, y + s // 3)
    p2 = (margin_x + s // 3, y + s * 2 // 3)
    p3 = (margin_x + s, y - s // 6)
    pen_w = max(3, s // 8)
    for offset in range(-1, 2):
        draw.line([(p1[0], p1[1] + offset), (p2[0], p2[1] + offset)], fill=rgba, width=pen_w)
        draw.line([(p2[0], p2[1] + offset), (p3[0], p3[1] + offset)], fill=rgba, width=pen_w + 1)

def _draw_cross(draw: ImageDraw.Draw, x: int, y: int, color: str, size: int, img_w: int = 0):
    rgba = _parse_color("red")
    margin_x = min(x, 35)
    s = max(size, 24)
    half = s // 2
    pen_w = max(3, s // 7)
    for offset in range(-1, 2):
        draw.line([(margin_x - half // 2, y - half + offset), (margin_x + half, y + half + offset)], fill=rgba, width=pen_w)
        draw.line([(margin_x - half // 2, y + half + offset), (margin_x + half, y - half + offset)], fill=rgba, width=pen_w)

def _draw_underline(draw: ImageDraw.Draw, x: int, y: int, width: int, color: str):
    rgba = _parse_color(color)
    pen_w = 3
    segments = max(4, width // 20)
    points = []
    for i in range(segments + 1):
        px = x + (width * i) // segments
        wave = random.randint(-1, 1)
        py = y + wave
        points.append((px, py))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=rgba, width=pen_w)
    for i in range(len(points) - 1):
        draw.line([(points[i][0], points[i][1] + 1), (points[i + 1][0], points[i + 1][1] + 1)], fill=rgba, width=pen_w - 1)

def _draw_highlight_box(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int, color: str):
    rgba = _parse_color(color)
    is_green = rgba[1] > rgba[0] and rgba[1] > rgba[2]
    if is_green:
        fill_rgba = (0, 200, 0, 40)
        border_rgba = (0, 150, 0, 200)
    else:
        fill_rgba = (220, 30, 30, 35)
        border_rgba = (220, 30, 30, 200)
    pad = 4
    draw.rectangle([(x - pad, y - pad), (x + w + pad, y + h + pad)], fill=fill_rgba, outline=border_rgba, width=2)
    bracket_len = max(4, min(14, w // 3, h // 3))
    bw = 3
    # TL
    draw.line([(x - pad, y - pad), (x - pad + bracket_len, y - pad)], fill=border_rgba, width=bw)
    draw.line([(x - pad, y - pad), (x - pad, y - pad + bracket_len)], fill=border_rgba, width=bw)
    # TR
    draw.line([(x + w + pad, y - pad), (x + w + pad - bracket_len, y - pad)], fill=border_rgba, width=bw)
    draw.line([(x + w + pad, y - pad), (x + w + pad, y - pad + bracket_len)], fill=border_rgba, width=bw)
    # BL
    draw.line([(x - pad, y + h + pad), (x - pad + bracket_len, y + h + pad)], fill=border_rgba, width=bw)
    draw.line([(x - pad, y + h + pad), (x - pad, y + h + pad - bracket_len)], fill=border_rgba, width=bw)
    # BR
    draw.line([(x + w + pad, y + h + pad), (x + w + pad - bracket_len, y + h + pad)], fill=border_rgba, width=bw)
    draw.line([(x + w + pad, y + h + pad), (x + w + pad, y + h + pad - bracket_len)], fill=border_rgba, width=bw)

def _draw_margin_comment(draw: ImageDraw.Draw, x: int, y: int, text: str, color: str, size: int, img_w: int, img_h: int):
    if not text or not text.strip(): return
    rgba = _parse_color(color)
    font_size = min(max(13, size // 2), 16)
    font = _get_font(font_size)
    margin_x = x if (x and x > 0) else (int(img_w * 0.78) if img_w > 0 else x)
    display_text = text.strip()[:40] if len(text.strip()) <= 40 else text.strip()[:38] + ".."
    words = display_text.split()
    lines, current_line, word_count = [], [], 0
    for word in words:
        if word_count < 4:
            current_line.append(word); word_count += 1
        else:
            if current_line: lines.append(" ".join(current_line))
            current_line = [word]; word_count = 1
    if current_line: lines.append(" ".join(current_line))
    lines = lines[:3]
    line_sizes = []
    for line in lines:
        try:
            bbox = font.getbbox(line)
            line_sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
        except Exception:
            line_sizes.append((len(line) * 7, 14))
    max_tw = max(tw for tw, _ in line_sizes) if line_sizes else 0
    line_h = max(th for _, th in line_sizes) if line_sizes else 14
    total_h = line_h * len(lines) + (len(lines) - 1) * 2
    if img_w > 0 and margin_x + max_tw > img_w - 5: margin_x = max(5, img_w - max_tw - 8)
    if img_h > 0 and y + total_h + 2 > img_h - 5: y = max(5, img_h - total_h - 6)
    draw.rectangle([(margin_x - 2, y - 1), (margin_x + max_tw + 3, y + total_h + 2)], fill=(255, 255, 240, 140))
    for idx, line in enumerate(lines):
        draw.text((margin_x, y + idx * (line_h + 2)), line, fill=rgba, font=font)

def _draw_text(draw: ImageDraw.Draw, x: int, y: int, text: str, color: str, size: int):
    font = _get_font(min(size, 18))
    rgba = _parse_color(color)
    draw.text((x, y), text, fill=rgba, font=font)

def _draw_score_circle(draw: ImageDraw.Draw, x: int, y: int, text: str, color: str, size: int):
    rgba = _parse_color(color)
    r = max(size, 20)
    draw.ellipse([(x - r, y - r), (x + r, y + r)], outline=rgba, width=3)
    font = _get_font(max(14, r - 4))
    try:
        bbox = font.getbbox(text)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * 8, 14
    draw.text((x - tw // 2, y - th // 2), text, fill=rgba, font=font)

def _draw_margin_bracket(draw: ImageDraw.Draw, x: int, y_top: int, height: int, text: str, color: str, size: int, img_w: int):
    rgba = _parse_color(color)
    pen_w = 2
    bx = max(x, int(img_w * 0.76)) if img_w > 0 else x
    y_bot, y_mid, indent = y_top + height, y_top + height // 2, 8
    draw.line([(bx, y_top), (bx, y_mid - 4)], fill=rgba, width=pen_w)
    draw.line([(bx, y_mid - 4), (bx - indent, y_mid)], fill=rgba, width=pen_w)
    draw.line([(bx - indent, y_mid), (bx, y_mid + 4)], fill=rgba, width=pen_w)
    draw.line([(bx, y_mid + 4), (bx, y_bot)], fill=rgba, width=pen_w)
    draw.line([(bx, y_top), (bx + 5, y_top)], fill=rgba, width=pen_w)
    draw.line([(bx, y_bot), (bx + 5, y_bot)], fill=rgba, width=pen_w)
    if text and text.strip():
        font_size = min(max(12, size // 2), 15); font = _get_font(font_size)
        display_text = text.strip()[:25] if len(text.strip()) <= 25 else text.strip()[:23] + ".."
        label_x, label_y = bx + 6, y_mid - 7
        try:
            bbox = font.getbbox(display_text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = len(display_text) * 7, 13
        if img_w > 0 and label_x + tw > img_w - 3: label_x = max(3, img_w - tw - 5)
        draw.rectangle([(label_x - 2, label_y - 1), (label_x + tw + 2, label_y + th + 1)], fill=(255, 255, 240, 140))
        draw.text((label_x, label_y), display_text, fill=rgba, font=font)

def _draw_total_score(draw: ImageDraw.Draw, text: str, color: str, img_w: int):
    rgba = _parse_color(color)
    score_font, label_font = _get_font(28), _get_font(13)
    label, score_text = "Total", text or "0"
    try:
        s_bbox = score_font.getbbox(score_text)
        s_tw, s_th = s_bbox[2] - s_bbox[0], s_bbox[3] - s_bbox[1]
    except Exception:
        s_tw, s_th = len(score_text) * 16, 28
    try:
        l_bbox = label_font.getbbox(label)
        l_tw, l_th = l_bbox[2] - l_bbox[0], l_bbox[3] - l_bbox[1]
    except Exception:
        l_tw, l_th = 30, 13
    box_w, box_h = max(s_tw, l_tw) + 28, s_th + l_th + 22
    bx, by = img_w - box_w - 18, 12
    draw.rectangle([(bx, by), (bx + box_w, by + box_h)], fill=(255, 255, 255, 230))
    border = (rgba[0], rgba[1], rgba[2], 220)
    draw.rectangle([(bx, by), (bx + box_w, by + box_h)], outline=border, width=3)
    draw.rectangle([(bx + 3, by + 3), (bx + box_w - 3, by + box_h - 3)], outline=border, width=1)
    draw.text((bx + (box_w - l_tw) // 2, by + 5), label, fill=(0, 0, 0, 200), font=label_font)
    draw.text((bx + (box_w - s_tw) // 2, by + l_th + 12), score_text, fill=rgba, font=score_font)
