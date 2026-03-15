import os
import re

source_path = r"d:\SSB\GradeSense1-main\backend\app\services\annotation.py"
dest_path = r"d:\SSB\GradeSense1-main\backend\app\services\annotation_v2\annotator.py"

with open(source_path, "r", encoding="utf-8") as f:
    content = f.read()

content = re.sub(
    r"\s*def _normalize_text\(.*?def _build_word_boxes\(words\):.*?return boxes\n",
    "\n",
    content,
    flags=re.DOTALL
)

helpers2_start = r"\s*def _parse_line_id.+?def _expand_segment_range.+?return \[f\"P\{p_num\}-S\{i\}\" for i in range\(start_idx, end_idx \+ 1\)\]\n"
content = re.sub(helpers2_start, "\n", content, flags=re.DOTALL)

new_imports = """
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
"""

content = re.sub(r"def _generate_margin_annotations.*?def generate_annotated_images\(", 
                 new_imports + "\ndef generate_annotated_images(", 
                 content, flags=re.DOTALL)

content = content.replace('SKIP_INTRO_PAGES = int(os.environ.get("SKIP_ANNOTATION_INTRO_PAGES", "3"))',
                          '# SKIP_INTRO_PAGES uses imported config.')

content = content.replace('positive_labels = [\n                "Well explained point", "Strong constitutional basis", "Relevant case law cited", \n                "Accurate data with source", "Good substantiation", "Proper legal framework",\n                "Contextual understanding shown", "Evidence-based claim", "Strong argumentation"\n            ]', "positive_labels = POSITIVE_LABELS")

content = content.replace('critical_labels = [\n                "Needs more examples", "Lacks substantiation", "Missing key statute", \n                "Vague explanation needed", "Should cite relevant case", "Incomplete coverage",\n                "Needs schedule/article reference", "Lacks constitutional basis", "More clarity needed"\n            ]', "critical_labels = CRITICAL_LABELS")

def replace_chunk(text, start_marker, end_marker, replacement):
    start_idx = text.find(start_marker)
    if start_idx == -1: return text
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1: return text
    return text[:start_idx] + replacement + text[end_idx+len(end_marker):]

# SEGMENT
seg_start = '                    if ann_type in {"UNDERLINE", "ERROR_UNDERLINE", "FEEDBACK_UNDERLINE", "EMPHASIS_UNDERLINE"}:'
seg_start_idx = content.find(seg_start)
if seg_start_idx != -1:
    seg_end_marker = '                        line_id_placed += 1\n                    continue\n'
    seg_repl = '''                    renderer = renderers_registry.get(ann_type)
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
'''
    content = replace_chunk(content, seg_start, seg_end_marker, seg_repl)

# LINE ID
line_start_idx = content.find(seg_start) # find next
if line_start_idx != -1:
    line_end_marker = '                        line_id_placed += 1\n                    continue\n'
    line_repl = '''                    renderer = renderers_registry.get(ann_type)
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
'''
    content = replace_chunk(content, seg_start, line_end_marker, line_repl)

# ANCHOR
anchor_start = '                        if ann_data.type == AnnotationType.CHECKMARK:'
anchor_end = '                            anchor_placed += 1\n'
anchor_repl = '''                        renderer = renderers_registry.get(ann_data.type)
                        if renderer:
                            context_dict = {
                                "is_anchor": True,
                                "x2": x2, "y1": y1, "line_cy": line_cy,
                                "reason_text": reason_text
                            }
                            positioned_annotations.extend(renderer.render(ann_data, context_dict))
                            anchor_placed += 1
'''
content = replace_chunk(content, anchor_start, anchor_end, anchor_repl)

# SCORE PLACEMENT 1 (start)
s1_start = '                        positioned_annotations.append(Annotation(\n                            annotation_type=AnnotationType.SCORE_CIRCLE,'
s1_end = '                        placed_score = True\n'
s1_repl = '''                        renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                        context_dict = {
                            "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                            "max_text": max_text, "color": color, "is_start": True,
                            "img_width": img_width
                        }
                        positioned_annotations.extend(renderer.render(None, context_dict))
                        placed_score = True
'''
content = replace_chunk(content, s1_start, s1_end, s1_repl)

# SCORE PLACEMENT 2 (fallback)
s2_start = '                        # More visible score circle + textual label\n                        positioned_annotations.append(Annotation(\n                            annotation_type=AnnotationType.SCORE_CIRCLE,'
s2_end = '                        placed_score = True\n'
s2_repl = '''                        # More visible score circle + textual label
                        renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                        context_dict = {
                            "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                            "max_text": max_text, "color": color, "is_start": False,
                            "img_width": img_width, "size": 22
                        }
                        positioned_annotations.extend(renderer.render(None, context_dict))
                        placed_score = True
'''
content = replace_chunk(content, s2_start, s2_end, s2_repl)

# SCORE PLACEMENT 3 (last-line)
s3_start = '                    # More visible score circle + textual label\n                    positioned_annotations.append(Annotation(\n                        annotation_type=AnnotationType.SCORE_CIRCLE,'
s3_end = '                    placed_score = True\n'
s3_repl = '''                    # More visible score circle + textual label
                    renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                    context_dict = {
                        "place_x": place_x, "y_pos": mid_y, "score_text": score_text,
                        "max_text": max_text, "color": color, "is_start": False,
                        "img_width": img_width, "size": 22
                    }
                    positioned_annotations.extend(renderer.render(None, context_dict))
                    placed_score = True
'''
content = replace_chunk(content, s3_start, s3_end, s3_repl)

# SCORE PLACEMENT 4 (estimated slot)
s4_start = '                    # More visible score circle + textual label for estimated placement\n                    positioned_annotations.append(Annotation(\n                        annotation_type=AnnotationType.SCORE_CIRCLE,'
s4_end = '                    placed_score = True\n'
s4_repl = '''                    # More visible score circle + textual label for estimated placement
                    renderer = renderers_registry.get(AnnotationType.SCORE_CIRCLE)
                    context_dict = {
                        "place_x": place_x, "y_pos": est_y, "score_text": score_text,
                        "max_text": max_text, "color": color, "is_start": False,
                        "img_width": img_width, "size": 22
                    }
                    positioned_annotations.extend(renderer.render(None, context_dict))
                    placed_score = True
'''
content = replace_chunk(content, s4_start, s4_end, s4_repl)

with open(dest_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Annotator properly refactored and written!")
