from typing import Any, Dict, List, Optional

from app.services.pipelines.simple_pipeline.utils.meta_merger import _merge_question_meta
from app.services.pipelines.simple_pipeline.grading.mcq_grader import grade_mcq
from app.services.pipelines.simple_pipeline.grading.descriptive_grader import grade_descriptive
from app.services.pipelines.simple_pipeline.extraction.text_packet_builder import _text_only_build_packets

try:
    from app.services.answer_sheet_pipeline import (
        pdf_to_clean_images,
        detect_page_layout,
        run_region_ocr,
        build_packets,
        build_question_blueprint_from_pdf,
    )
    _HAS_FULL_ANSWER_PIPE = True
except ImportError:
    # fall back to minimal functionality
    from app.services.answer_sheet_pipeline import build_question_blueprint_from_exam_questions as build_question_blueprint_from_pdf

    _HAS_FULL_ANSWER_PIPE = False

from app.constants.layers import (
    DEFAULT_QUESTION_TYPE,
    STATUS_FAILED,
    STATUS_SUCCESS,
    QUESTION_TYPE_MCQ,
    PRECISION_ROUNDING,
)

def run_simple_pipeline(
    question_paper_pdf: bytes,
    answer_sheet_pdf: bytes,
    question_meta: Optional[Dict[Any, Any]] = None,
) -> List[Dict[str, Any]]:
    """Execute the full simple pipeline and return per-question results.

    ``question_meta`` is an optional dictionary keyed by question number; the
    values are merged into the extracted blueprint.  This allows callers to
    supply things like ``{'1': {'type': 'mcq', 'correct_option': 'B',
    'marks': 2}}`` if the paper itself lacks that information.
    """

    # 1. extract blueprint from question paper
    blueprint = build_question_blueprint_from_pdf(question_paper_pdf)
    _merge_question_meta(blueprint, question_meta or {})

    # 2. parse answer sheet into packets
    if _HAS_FULL_ANSWER_PIPE:
        clean_imgs = pdf_to_clean_images(answer_sheet_pdf)
        layout = detect_page_layout(clean_imgs)
        regions = run_region_ocr(clean_imgs, layout)
        packets = build_packets(regions, blueprint)
    else:
        # heavy dependencies missing (cv2 etc). use simple text-based
        # extraction so tests and lightweight environments still work.
        packets = _text_only_build_packets(answer_sheet_pdf, blueprint)

    # 3. grade each question independently
    results: List[Dict[str, Any]] = []
    for q in blueprint:
        qnum = int(q.get("question_id") or -1)
        pkt = packets.get(qnum, {})
        answer_text = str(pkt.get("combined_text", "") or "").strip()
        qtype = str(q.get("type", DEFAULT_QUESTION_TYPE) or "").lower()

        if qtype == QUESTION_TYPE_MCQ:
            score, feedback = grade_mcq(answer_text, q)
        else:
            score, feedback = grade_descriptive(answer_text, q)

        results.append(
            {
                "question_number": qnum,
                "answer_text": answer_text,
                "question_text": q.get("rubric") or q.get("question_text"),
                "max_marks": float(q.get("marks", 0.0) or 0.0),
                "score": round(float(score or 0.0), PRECISION_ROUNDING),
                "feedback": feedback,
            }
        )

    return results
