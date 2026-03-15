"""
Annotation service - generates annotated images with grading marks.
Migrated from server.py annotation functions (lines ~6828-7992).

These functions are very large and use Vision OCR + annotation_utils for
positioning grading marks on student answer images.
"""

from typing import List, Dict, Optional
import base64
import io
import re
import os

from PIL import Image

from app.core.logging_config import logger
from app.models.submission import QuestionScore, AnnotationData
from .utils import (
    Annotation,
    AnnotationType,
    apply_annotations_to_image,
    auto_position_annotations_for_question
)
from app.utils.ocr_provider import get_ocr_provider
from app.utils.vision_ocr_service import get_vision_service
from app.ocr import build_page_segments



from app.services.annotation_v2.config import MARGIN_X, SKIP_INTRO_PAGES, POSITIVE_LABELS, CRITICAL_LABELS
from app.services.annotation_v2.utils import (
    _normalize_text,
    _word_text,
    _word_vertices,
    _find_anchor_box,
    _build_ocr_words,
    _group_words_into_lines,
    _build_word_boxes,
    _extract_question_number_from_left_label,
    _parse_line_id,
    _expand_line_range,
    _parse_segment_id,
    _expand_segment_range
)
from app.services.annotation_v2.fallback import _generate_margin_annotations
from app.services.annotation_v2.renderers.base_renderer import BaseAnnotationRenderer
from app.services.annotation_v2.renderers.underline import UnderlineRenderer
from app.services.annotation_v2.renderers.comment import CommentRenderer
from app.services.annotation_v2.renderers.score import ScoreRenderer
from app.services.annotation_v2.renderers.tick_cross import TickCrossRenderer
from app.services.annotation_v2.renderers.box import BoxRenderer
from app.services.annotation_v2.renderers.point_number import PointNumberRenderer

# Instantiate renderers
renderers_registry = {
    AnnotationType.UNDERLINE: UnderlineRenderer(),
    AnnotationType.ERROR_UNDERLINE: UnderlineRenderer(),
    AnnotationType.FEEDBACK_UNDERLINE: UnderlineRenderer(),
    AnnotationType.EMPHASIS_UNDERLINE: UnderlineRenderer(),
    AnnotationType.COMMENT: CommentRenderer(),
    AnnotationType.BOX_COMMENT: CommentRenderer(),
    AnnotationType.SCORE_CIRCLE: ScoreRenderer(),
    AnnotationType.TICK: TickCrossRenderer(),
    AnnotationType.CHECKMARK: TickCrossRenderer(),
    AnnotationType.DOUBLE_TICK: TickCrossRenderer(),
    AnnotationType.CROSS: TickCrossRenderer(),
    AnnotationType.CROSS_MARK: TickCrossRenderer(),
    AnnotationType.BOX: BoxRenderer(),
    AnnotationType.HIGHLIGHT_BOX: BoxRenderer(),
    AnnotationType.POINT_NUMBER: PointNumberRenderer(),
}

def generate_annotated_images(
    original_images: List[str],
    question_scores: List[QuestionScore]
) -> List[str]:
    """
    Generate annotated images by overlaying grading annotations on original student answer images.
    Basic version without Vision OCR.
    """
    try:
        logger.info(f"Generating annotated images for {len(original_images)} pages")

        # Map questions to pages
        page_questions: Dict[int, List[QuestionScore]] = {i: [] for i in range(len(original_images))}
        for q_score in question_scores:
            if q_score.page_number and q_score.page_number > 0:
                page_idx = min(q_score.page_number - 1, len(original_images) - 1)
            else:
                page_idx = min(
                    int((q_score.question_number - 1) / max(1, len(question_scores) / len(original_images))),
                    len(original_images) - 1
                )
            page_questions[page_idx].append(q_score)

        annotated_images = []
        # Number of front pages to skip annotations for (intro + following pages)
        # SKIP_INTRO_PAGES uses imported config.

        for page_idx, original_image in enumerate(original_images):
            try:
                image_data = base64.b64decode(original_image)
                with Image.open(io.BytesIO(image_data)) as img:
                    img_width, img_height = img.size
            except Exception as e:
                logger.warning(f"Could not get image dimensions: {e}, using defaults")
                img_width, img_height = 1000, 1400

            # If configured to skip the first N pages, leave them unchanged
            if page_idx < SKIP_INTRO_PAGES:
                logger.info(f"[ANN-SKIP] Skipping annotations for front page #{page_idx+1} (SKIP_INTRO_PAGES={SKIP_INTRO_PAGES})")
                annotated_images.append(original_image)
                continue

            positioned_annotations: List[Annotation] = []
            auto_annotation_y = 140
            auto_annotation_step = 60
            comment_cursor_y = int(img_height * 0.12)
            comment_x = int(img_width * 0.72)
            comment_step = max(22, int(img_height * 0.02))

            for q_score in page_questions.get(page_idx, []):
                for ann_data in q_score.annotations:
                    if ann_data.page_index != page_idx:
                        continue
                    if ann_data.box_2d and len(ann_data.box_2d) == 4:
                        ymin, xmin, ymax, xmax = ann_data.box_2d
                        x_pos = int(xmin / 1000 * img_width)
                        y_pos = int(ymin / 1000 * img_height)
                    elif ann_data.x > 0 or ann_data.y > 0:
                        x_pos = ann_data.x if ann_data.x > 0 else 30
                        y_pos = ann_data.y if ann_data.y > 0 else 120
                    else:
                        if ann_data.type in {AnnotationType.COMMENT, AnnotationType.MARGIN_NOTE}:
                            x_pos = comment_x
                            y_pos = comment_cursor_y
                            comment_cursor_y += comment_step
                        else:
                            x_pos = 40
                            y_pos = auto_annotation_y
                            auto_annotation_y += auto_annotation_step
                    positioned_annotations.append(Annotation(
                        annotation_type=ann_data.type, x=x_pos, y=y_pos,
                        text=ann_data.text, color=ann_data.color, size=ann_data.size
                    ))

                for sub_score in q_score.sub_scores:
                    for ann_data in sub_score.annotations:
                        if ann_data.page_index != page_idx:
                            continue
                        if ann_data.box_2d and len(ann_data.box_2d) == 4:
                            ymin, xmin, ymax, xmax = ann_data.box_2d
                            x_pos = int(xmin / 1000 * img_width)
                            y_pos = int(ymin / 1000 * img_height)
                        elif ann_data.x > 0 or ann_data.y > 0:
                            x_pos = ann_data.x if ann_data.x > 0 else 30
                            y_pos = ann_data.y if ann_data.y > 0 else 120
                        else:
                            if ann_data.type in {AnnotationType.COMMENT, AnnotationType.MARGIN_NOTE}:
                                x_pos = comment_x
                                y_pos = comment_cursor_y
                                comment_cursor_y += comment_step
                            else:
                                x_pos = 40
                                y_pos = auto_annotation_y
                                auto_annotation_y += auto_annotation_step
                        positioned_annotations.append(Annotation(
                            annotation_type=ann_data.type, x=x_pos, y=y_pos,
                            text=ann_data.text, color=ann_data.color, size=ann_data.size
                        ))

            if not positioned_annotations:
                annotated_images.append(original_image)
                continue

            annotated_image = apply_annotations_to_image(original_image, positioned_annotations)
            annotated_images.append(annotated_image)

        logger.info(f"Successfully generated {len(annotated_images)} annotated images")
        return annotated_images
        
    except Exception as e:
        logger.error(f"Error generating annotated images: {e}", exc_info=True)
        return original_images


async def generate_annotated_images_with_vision_ocr(
    original_images: List[str],
    question_scores: List[QuestionScore],
    use_vision_ocr: bool = False,
    dense_red_pen: bool = False
) -> List[str]:
    """
    Generate annotated images using Vision OCR for precise text positioning.
    Falls back to basic annotation if OCR is unavailable.
    
    This is a large function (~700 lines) migrated from server.py.
    It uses Google Cloud Vision OCR to find exact text positions on the page
    and places annotations (ticks, crosses, underlines, comments) precisely.
    """
    if not use_vision_ocr and not dense_red_pen:
        logger.info("Vision OCR disabled - generating margin annotations")
        return generate_annotated_images(original_images, question_scores)

    vision_service = get_vision_service()
    ocr_provider = get_ocr_provider()
    if not vision_service.is_available() and not dense_red_pen:
        logger.warning("Vision OCR unavailable; continuing with hybrid OCR provider fallback")

    # Helper functions for OCR-based annotation positioning

    # Process each page
    annotated_images: List[str] = []
    q_score_map = {qs.question_number: qs for qs in question_scores}
    question_numbers = sorted({qs.question_number for qs in question_scores})
    question_patterns = {
        q_num: re.compile(rf"^\s*(?:Q\s*)?{q_num}\s*[\).:-]?\s*", re.IGNORECASE)
        for q_num in question_numbers
    }
    q_num_set = set(question_numbers)

    def _extract_question_number_from_left_label(left_text: str, page_num: int) -> Optional[int]:
        if not left_text:
            return None
        t = re.sub(r"\s+", " ", left_text).strip()
        if not t:
            return None
        t_lower = t.lower()
        if t.isdigit() and len(t) <= 2 and int(t) == page_num:
            return None
        if "space for writing" in t_lower or "question number" in t_lower:
            return None

        explicit = re.match(r"^\s*(?:q(?:uestion)?\.?\s*)0*(\d{1,2})\b", t, re.IGNORECASE)
        if explicit:
            n = int(explicit.group(1))
            return n if n in q_num_set else None

        lead = re.match(r"^\s*[\(\[]?\s*0*([0-9]{1,3})\s*[\)\]\.:-]?\b", t)
        if lead:
            raw = lead.group(1)
            n: Optional[int] = None
            if len(raw) <= 2:
                n = int(raw)
            elif len(raw) == 3 and raw.startswith("0"):
                n = int(raw[-2:])
            elif len(raw) == 3 and raw.startswith("9"):
                n = int(raw[-2:])
            if n is not None and n in q_num_set:
                return n
        return None

    # Compute total score once for the first-page header
    _total_obtained = sum(
        qs.obtained_marks for qs in question_scores if qs.obtained_marks >= 0
    )
    _total_max = sum(
        qs.max_marks for qs in question_scores if qs.obtained_marks >= 0
    )
    def _fmt_score(v):
        return str(int(v)) if v == int(v) else f"{v:.1f}"
    _total_score_text = f"{_fmt_score(_total_obtained)} / {_fmt_score(_total_max)}"

    # --- PRE-SCAN: OCR all pages to locate the final line for each question ---
    pages_ocr = [None] * len(original_images)
    question_last_line: Dict[int, tuple] = {}  # q_num -> (page_idx, line_idx, line_box)

    carry_q_global = 0
    for p_idx, original_image_b64 in enumerate(original_images):
        try:
            image_data = base64.b64decode(original_image_b64)
            with Image.open(io.BytesIO(image_data)) as _img:
                p_w, p_h = _img.size
        except Exception:
            p_w, p_h = 1000, 1400

        try:
            ocr_result = ocr_provider.detect(original_image_b64, allow_fallback=False)
            words = ocr_result.get("words", []) or []
            tables = ocr_result.get("tables", []) or []
        except Exception:
            words = []
            tables = []

        y_threshold = max(10, int(p_h * 0.012))
        line_boxes = _group_words_into_lines(words, y_threshold, p_w)
        page_segments = build_page_segments(words=words, tables=tables, page=p_idx + 1)
        segment_id_map_local = {seg.get("segment_id"): seg for seg in page_segments if seg.get("segment_id")}

        # Build a per-page line-index map (Qn -> {L#: box}) so we can identify last lines
        line_index_map = {}
        line_counts_local: Dict[int, int] = {}
        page_num = p_idx + 1
        detected_by_line = [
            _extract_question_number_from_left_label((line.get("left_text") or ""), page_num)
            for line in line_boxes
        ]
        has_anchor = any(v is not None for v in detected_by_line)
        current_q_local = 0 if has_anchor else carry_q_global
        line_id_map_local: Dict[str, dict] = {}
        answer_start_y_local = int(p_h * 0.25)
        footer_margin = max(48, int(p_h * 0.03))
        for line, detected_q in zip(line_boxes, detected_by_line):
            text = (line.get("text") or "").strip()
            if detected_q is not None:
                current_q_local = detected_q
                carry_q_global = detected_q
            if current_q_local <= 0:
                continue
            line_counts_local[current_q_local] = line_counts_local.get(current_q_local, 0) + 1
            li = line_counts_local[current_q_local]
            line_id = f"Q{current_q_local}-L{li}"
            line_id_map_local[line_id] = line
            line_index_map.setdefault(current_q_local, {})[li] = line

            # Prefer to record the last *meaningful* line for a question — ignore headers/footers/page-numbers
            y1_l = line.get("y1", 0)
            y2_l = line.get("y2", 0)
            short_numeric = text.isdigit() and len(text) <= 3
            is_footer = (y2_l >= p_h - footer_margin) or short_numeric
            if y2_l >= answer_start_y_local and not is_footer:
                question_last_line[current_q_local] = (p_idx, li, line)

        page_text = " ".join(w.get("text", "") for w in words).lower()
        basic_intro = bool(
            re.search(r"(rubric|evaluation|parameter|marking\s+scheme|header|instruction|next\s+page|test\s+case|turn\s+to|answer\s+key)", page_text)
            or (len(line_boxes) < 3)
            or (len(words) < 10)
        )
        # If a question header (Qn) appears on the page, treat it as an answer page
        has_question_header = has_anchor
        is_intro = basic_intro and not has_question_header

        pages_ocr[p_idx] = {
            "words": words,
            "line_boxes": line_boxes,
            "line_index_map": line_index_map,
            "line_id_map": line_id_map_local,
            "segment_id_map": segment_id_map_local,
            "img_w": p_w,
            "img_h": p_h,
            "is_intro": is_intro,
        }

    # --- ASSIGN MISSING question.page_number USING OCR pre-scan ---
    # If grading didn't set page_number on QuestionScore, infer it from OCR line matches so
    # score circles can be placed deterministically beside the question end-line.
    for qs in question_scores:
        try:
            if getattr(qs, "page_number", None):
                continue
        except Exception:
            # qs may be a dict-like fallback in some call-sites
            if isinstance(qs, dict) and qs.get("page_number"):
                continue
        qn = qs.question_number
        assigned = False
        for p_idx, p in enumerate(pages_ocr):
            if not p:
                continue
            line_index_map = p.get("line_index_map", {})
            if qn in line_index_map and line_index_map[qn]:
                # assign inferred page number (1-indexed)
                try:
                    qs.page_number = p_idx + 1
                except Exception:
                    # if qs is dict-like, set key
                    if isinstance(qs, dict):
                        qs["page_number"] = p_idx + 1
                assigned = True
                logger.info(f"[PAGE-INFER] Assigned page {p_idx+1} to Q{qn} via OCR pre-scan")
                break
        if not assigned:
            logger.debug(f"[PAGE-INFER] Could not infer page for Q{qn}")

    # --- MAIN PER-PAGE RENDER PASS (uses stored OCR from pre-scan) ---
    # SKIP_INTRO_PAGES uses imported config.
    intro_zone_end = -1
    for page_idx, original_image in enumerate(original_images):

        # Use pre-scanned OCR data for this page
        page_data = pages_ocr[page_idx]
        if not page_data or not page_data.get("words"):
            # Fall back to basic annotations for this page
            annotated_images.append(original_image)
            continue

        words = page_data["words"]
        line_boxes = page_data["line_boxes"]
        img_width = page_data["img_w"]
        img_height = page_data["img_h"]
        answer_start_y = int(img_height * 0.25)
        is_intro_page = page_data.get("is_intro", False)

        # If this page falls within the intro-skip zone, do not render any annotations
        if page_idx <= intro_zone_end:
            logger.info(f"[ANN-SKIP] Page {page_idx+1}: within intro-skip zone (up to page {intro_zone_end+1}) - skipping annotations")
            annotated_images.append(original_image)
            continue

        positioned_annotations: List[Annotation] = []

        # If the OCR pre-scan explicitly marks this page as intro/header, skip it and
        # also skip the following (SKIP_INTRO_PAGES - 1) pages.
        if is_intro_page:
            intro_zone_end = page_idx + max(0, SKIP_INTRO_PAGES - 1)
            logger.info(f"[ANN-SKIP] Page {page_idx+1}: detected as intro/header - will skip through page {intro_zone_end+1}")
            annotated_images.append(original_image)
            continue


        # Reuse precomputed line ID maps from pre-scan
        line_id_map = page_data.get("line_id_map", {})
        segment_id_map = page_data.get("segment_id_map", {})
        line_index_map = page_data.get("line_index_map", {})
        current_q = question_numbers[0] if question_numbers else 0
        logger.debug(f"[ANN-LINE-MAP] Page {page_idx+1}: Reusing {len(line_id_map)} line IDs")

        # Position line-id or anchor-based annotations
        total_ann_requested = 0
        line_id_placed = 0
        line_id_skipped = 0
        anchor_placed = 0
        
        for q_score in question_scores:
            for ann_data in q_score.annotations:
                if ann_data.page_index not in (-1, page_idx):
                    continue
                
                total_ann_requested += 1
                segment_ids = []
                if getattr(ann_data, "segment_id", None):
                    segment_ids = [ann_data.segment_id]
                elif getattr(ann_data, "segment_id_start", None) or getattr(ann_data, "segment_id_end", None):
                    segment_ids = _expand_segment_range(ann_data.segment_id_start, ann_data.segment_id_end)

                if segment_ids:
                    resolved_lines = []
                    for seg_id in segment_ids:
                        seg = segment_id_map.get(seg_id)
                        if not seg:
                            continue
                        x1 = seg.get("x1", 0)
                        y1 = seg.get("y1", 0)
                        x2 = seg.get("x2", 0)
                        y2 = seg.get("y2", 0)
                        if y2 < answer_start_y:
                            continue
                        resolved_lines.append((x1, y1, x2, y2))

                    if not resolved_lines:
                        line_id_skipped += 1
                        continue

                    ann_type = str(ann_data.type or "").upper()
                    reason_text = (ann_data.text or ann_data.label or ann_data.feedback or "").strip()
                    span_x1 = min(r[0] for r in resolved_lines)
                    span_y1 = min(r[1] for r in resolved_lines)
                    span_x2 = max(r[2] for r in resolved_lines)
                    span_y2 = max(r[3] for r in resolved_lines)
                    span_cy = (span_y1 + span_y2) // 2
                    is_multi_line = len(resolved_lines) > 1

                    renderer = renderers_registry.get(ann_type)
                    if renderer:
                        context_dict = {
                            "resolved_lines": resolved_lines,
                            "span_x1": span_x1, "span_y1": span_y1, 
                            "span_x2": span_x2, "span_y2": span_y2,
                            "span_cy": span_cy, "reason_text": reason_text,
                            "is_multi_line": is_multi_line, "is_segment": True
                        }
                        positioned_annotations.extend(renderer.render(ann_data, context_dict))
                        line_id_placed += 1
                    else:
                        positioned_annotations.append(Annotation(
                            annotation_type=AnnotationType.COMMENT,
                            x=span_x2 + 10, y=span_cy - 8,
                            text=reason_text, color=ann_data.color or "red", size=26
                        ))
                        line_id_placed += 1
                    continue

                line_ids = []
                if ann_data.line_id:
                    line_ids = [ann_data.line_id]
                elif ann_data.line_id_start or ann_data.line_id_end:
                    line_ids = _expand_line_range(ann_data.line_id_start, ann_data.line_id_end)

                if line_ids:
                    # ── Collect all resolved line boxes first ──
                    resolved_lines = []
                    for line_id in line_ids:
                        line = line_id_map.get(line_id)
                        if not line:
                            if not resolved_lines:  # Only log once per annotation
                                parsed = _parse_line_id(line_id)
                                q_num_str = f"Q{parsed[0]}" if parsed else "?"
                                avail = [k for k in line_id_map if k.startswith(q_num_str + "-")]
                                logger.warning(f"[ANN-SKIP] Page {page_idx+1}: Line ID '{line_id}' not found. Q{q_score.question_number}, Type={ann_data.type}. Available {q_num_str}: {avail[:10]}")
                            continue
                        x1, y1, x2, y2 = line["x1"], line["y1"], line["x2"], line["y2"]
                        if y2 < answer_start_y:
                            continue
                        resolved_lines.append((x1, y1, x2, y2))

                    if not resolved_lines:
                        line_id_skipped += 1
                        continue

                    ann_type = str(ann_data.type or "").upper()
                    reason_text = (ann_data.text or ann_data.label or ann_data.feedback or "").strip()

                    # Bounding box of entire span
                    span_x1 = min(r[0] for r in resolved_lines)
                    span_y1 = min(r[1] for r in resolved_lines)
                    span_x2 = max(r[2] for r in resolved_lines)
                    span_y2 = max(r[3] for r in resolved_lines)
                    span_cy = (span_y1 + span_y2) // 2
                    is_multi_line = len(resolved_lines) > 1

                    renderer = renderers_registry.get(ann_type)
                    if renderer:
                        context_dict = {
                            "resolved_lines": resolved_lines,
                            "span_x1": span_x1, "span_y1": span_y1, 
                            "span_x2": span_x2, "span_y2": span_y2,
                            "span_cy": span_cy, "reason_text": reason_text,
                            "is_multi_line": is_multi_line, "is_segment": False
                        }
                        positioned_annotations.extend(renderer.render(ann_data, context_dict))
                        line_id_placed += 1
                    continue

                if ann_data.anchor_text:
                    box = _find_anchor_box(words, ann_data.anchor_text)
                    if box:
                        x1, y1, x2, y2 = box
                        if y2 < answer_start_y:
                            continue
                        line_cy = (y1 + y2) // 2
                        reason_text = (ann_data.text or ann_data.label or ann_data.feedback or "").strip()
                        renderer = renderers_registry.get(ann_data.type)
                        if renderer:
                            context_dict = {
                                "is_anchor": True,
                                "x2": x2, "y1": y1, "line_cy": line_cy,
                                "reason_text": reason_text
                            }
                            positioned_annotations.extend(renderer.render(ann_data, context_dict))
                            anchor_placed += 1
                        elif ann_data.type == AnnotationType.CROSS_MARK:
                            positioned_annotations.append(Annotation(
                                annotation_type=AnnotationType.CROSS_MARK,
                                x=30, y=line_cy - 8, text="", color="red", size=26
                            ))
                            if reason_text:
                                positioned_annotations.append(Annotation(
                                    annotation_type=AnnotationType.COMMENT,
                                    x=x2 + 10, y=y1, text=reason_text,
                                    color="red", size=24
                                ))
                            anchor_placed += 1

        logger.info(f"[ANN-SUMMARY] Page {page_idx+1}: Requested={total_ann_requested}, LineID placed={line_id_placed}, LineID skipped={line_id_skipped}, Anchor placed={anchor_placed}")

        # Ensure every page with substantial handwriting gets AT LEAST 7 annotations
        # Skip intro/next pages (pages with very few lines)
        # Only use GREEN boxes - red is reserved for actual error/correction feedback
        non_total = [a for a in positioned_annotations if a.annotation_type != AnnotationType.TOTAL_SCORE]
        
        # Only add fallback if: (1) insufficient marks AND (2) page has substantial content (4+ lines)
        if len(non_total) < 7 and line_boxes and len(line_boxes) >= 4:
            # Page is a real answer page with insufficient marks; auto-add GREEN boxes only
            candidates = [l for l in line_boxes if l.get("y2", 0) >= answer_start_y]
            candidates = sorted(candidates, key=lambda l: l.get("y1", 0))
            needed = 7 - len(non_total)  # How many more marks to reach 7
            
            # Pick diverse lines: first, middle sections, and near end
            picks = []
            if candidates:
                picks.append(candidates[0])  # First line
                if len(candidates) > 1:
                    picks.append(candidates[len(candidates) // 3])  # Lower third
                if len(candidates) > 2:
                    picks.append(candidates[len(candidates) // 2])  # Middle
                if len(candidates) > 3:
                    picks.append(candidates[2 * len(candidates) // 3])  # Upper third
                if len(candidates) > 4:
                    picks.append(candidates[-1])  # Last line
            
            # Remove duplicates while preserving order
            seen = set()
            unique_picks = []
            for l in picks:
                key = (l.get('y1', 0), l.get('x1', 0))
                if key not in seen:
                    unique_picks.append(l)
                    seen.add(key)
            picks = unique_picks[:needed]
            
            # Add MIXED FEEDBACK - both positive (GREEN) and constructive (RED)
            # Balance: roughly 50-60% positive, 40-50% critical/improvement feedback
            positive_labels = POSITIVE_LABELS
            critical_labels = CRITICAL_LABELS
            
            # Alternate between positive and critical feedback
            for idx, line in enumerate(picks):
                x1, y1, x2, y2 = line["x1"], line["y1"], line["x2"], line["y2"]
                
                # Alternate: even index = positive (green), odd index = critical (red)
                is_positive = (idx % 2 == 0)
                
                if is_positive:
                    label = positive_labels[idx % len(positive_labels)]
                    color = "green"
                else:
                    label = critical_labels[idx % len(critical_labels)]
                    color = "red"
                
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.HIGHLIGHT_BOX,
                    x=x1 - 4, y=y1 - 4, text="", color=color,
                    width=max(30, x2 - x1 + 8), height=max(16, y2 - y1 + 8)
                ))
                positioned_annotations.append(Annotation(
                    annotation_type=AnnotationType.MARGIN_NOTE,
                    x=x2 + 10, y=y1,
                    text=label, color=color, size=24
                ))

        # --- Add per-question total marks at the question's final line (right-margin score) ---
        for qs in question_scores:
            qn = qs.question_number
            placed_score = False

            # 1) Prefer page_number on QuestionScore (explicit mapping from grading)
            page_for_q = (qs.page_number - 1) if getattr(qs, "page_number", None) else None
            if page_for_q == page_idx:
                # Try to find the question START line first (where 'Qn' appears)
                lines_map = page_data.get("line_index_map", {}).get(qn, {})
                if lines_map:
                    # Prefer the smallest line index (question header/start)
                    start_li = min(lines_map.keys())
                    start_line = lines_map[start_li]
                    start_text = (start_line.get("text") or "").strip()
                    is_header = False
                    try:
                        pat = question_patterns.get(qn)
                        if pat and pat.match(start_text):
                            is_header = True
                    except Exception:
                        pass

                    if is_header:
                        # Place score next to question START line (user requested)
                        raw_mid = (start_line.get("y1", 0) + start_line.get("y2", 0)) // 2
                        answer_top = int(img_height * 0.12)
                        clamp_top = max(answer_top, start_line.get("y1", 0) + 4)
                        clamp_bottom = min(img_height - 48, start_line.get("y2", 0) - 2)
                        mid_y = max(clamp_top, min(raw_mid, clamp_bottom))
                        place_x = min(start_line.get("x2", img_width // 2) + 60, img_width - 48)

                        score_text = _fmt_score(qs.obtained_marks)
                        max_text = _fmt_score(qs.max_marks)
                        pct = (qs.obtained_marks / max(1, qs.max_marks)) if qs.max_marks > 0 else 0
                        color = "green" if pct >= 0.5 else "red"
                        renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                        context_dict = {
                            "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                            "max_text": max_text, "color": color, "is_start": True,
                            "img_width": img_width
                        }
                        positioned_annotations.extend(renderer.render(None, context_dict))
                        placed_score = True
                        logger.debug(f"[SCORE-PLACE-START] Q{qn} -> page {page_idx+1} at y={mid_y} (by question start)")
                    else:
                        # Fallback to last-line placement if header not found on this page
                        last_li = max(lines_map.keys())
                        last_line = lines_map[last_li]
                        raw_mid = (last_line.get("y1", 0) + last_line.get("y2", 0)) // 2
                        answer_top = int(img_height * 0.12)
                        clamp_top = max(answer_top, last_line.get("y1", 0) + 4)
                        clamp_bottom = min(img_height - 48, last_line.get("y2", 0) - 2)
                        mid_y = max(clamp_top, min(raw_mid, clamp_bottom))
                        place_x = min(last_line.get("x2", img_width // 2) + 60, img_width - 48)

                        score_text = _fmt_score(qs.obtained_marks)
                        max_text = _fmt_score(qs.max_marks)
                        pct = (qs.obtained_marks / max(1, qs.max_marks)) if qs.max_marks > 0 else 0
                        color = "green" if pct >= 0.5 else "red"
                        # More visible score circle + textual label
                        renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                        context_dict = {
                            "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                            "max_text": max_text, "color": color, "is_start": False,
                            "img_width": img_width, "size": 22
                        }
                        positioned_annotations.extend(renderer.render(None, context_dict))
                        placed_score = True
                        logger.debug(f"[SCORE-PLACE] Q{qn} -> page {page_idx+1} at y={mid_y} (by page_number fallback)")

            # 2) Fall back to the pre-scanned question_last_line if it lies on this page
            if not placed_score:
                last = question_last_line.get(qn)
                if last and last[0] == page_idx and qs.obtained_marks is not None and qs.obtained_marks >= 0:
                    _, _, last_line = last
                    raw_mid = (last_line.get("y1", 0) + last_line.get("y2", 0)) // 2
                    answer_top = int(img_height * 0.12)
                    clamp_top = max(answer_top, last_line.get("y1", 0) + 4)
                    clamp_bottom = min(img_height - 48, last_line.get("y2", 0) - 2)
                    mid_y = max(clamp_top, min(raw_mid, clamp_bottom))

                    place_x = min(last_line.get("x2", img_width // 2) + 60, img_width - 48)
                    score_text = _fmt_score(qs.obtained_marks)
                    max_text = _fmt_score(qs.max_marks)
                    pct = (qs.obtained_marks / max(1, qs.max_marks)) if qs.max_marks > 0 else 0
                    color = "green" if pct >= 0.5 else "red"
                    # More visible score circle + textual label
                    renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                    context_dict = {
                        "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                        "max_text": max_text, "color": color, "is_start": False,
                        "img_width": img_width, "size": 22
                    }
                    positioned_annotations.extend(renderer.render(None, context_dict))
                    placed_score = True
                    logger.debug(f"[SCORE-PLACE] Q{qn} -> page {page_idx+1} at y={mid_y} (by last-line)")

            # 3) If no line found for this question on this page but the question is expected on this page,
            #    place a fallback score circle near the lower section of the question's area.
            if not placed_score and page_for_q == page_idx:
                # Estimate a reasonable Y by dividing page into N question slots for this page
                page_qs = [q for q in question_scores if (getattr(q, 'page_number', None) and q.page_number - 1 == page_idx)]
                if page_qs:
                    # Determine index among page questions
                    try:
                        idx_in_page = next(i for i, q in enumerate(page_qs) if q.question_number == qn)
                    except StopIteration:
                        idx_in_page = 0
                    slot_h = max(80, img_height // max(1, len(page_qs)))
                    est_y = int((idx_in_page + 0.85) * slot_h)
                    est_y = max(64, min(img_height - 80, est_y))
                    place_x = min(int(img_width * 0.72), img_width - 48)
                    score_text = _fmt_score(qs.obtained_marks)
                    max_text = _fmt_score(qs.max_marks)
                    pct = (qs.obtained_marks / max(1, qs.max_marks)) if qs.max_marks > 0 else 0
                    color = "green" if pct >= 0.5 else "red"
                    # More visible score circle + textual label for estimated placement
                    renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                    context_dict = {
                        "place_x": place_x, "y_pos": est_y, "score_text": score_text,
                        "max_text": max_text, "color": color, "is_start": False,
                        "img_width": img_width, "size": 22
                    }
                    positioned_annotations.extend(renderer.render(None, context_dict))
                    placed_score = True
                    logger.debug(f"[SCORE-PLACE] Q{qn} -> page {page_idx+1} at y={est_y} (estimated slot)")

            # otherwise do not place a score for questions that do not belong to this page


        annotated_image = apply_annotations_to_image(original_image, positioned_annotations)
        annotated_images.append(annotated_image)

    logger.info(f"OCR annotations applied to {len(annotated_images)} pages")
    return annotated_images
