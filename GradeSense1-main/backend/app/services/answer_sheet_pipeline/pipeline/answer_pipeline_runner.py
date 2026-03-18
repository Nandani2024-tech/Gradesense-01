import os
from typing import Any, Dict, List, Optional
from app.adapters.interfaces import AbstractOCRService

from app.core.logging_config import logger
from app.services.extraction.blueprint import (
    build_question_blueprint_from_exam_questions,
    build_question_blueprint_from_pdf,
)

from app.services.answer_sheet_pipeline.preprocessing.page_normalizer import normalize_answer_pages
from app.services.answer_sheet_pipeline.layout.layout_detector import detect_page_layout
from app.services.answer_sheet_pipeline.ocr.region_ocr import run_region_ocr
from app.services.answer_sheet_pipeline.packets.packet_builder import build_packets
from app.services.answer_sheet_pipeline.packets.packet_aligner import align_packets_to_blueprint
from app.services.answer_sheet_pipeline.structuring.accounting_structure import structure_accounting_answer
from app.constants.layers import (
    DEFAULT_POLLING_INTERVAL_SECONDS,
    FILE_TYPE_QUESTION_PAPER,
    PDF_IMAGE_BATCH_PAGES,
    MAPPING_CONFIDENCE_THRESHOLD,
    PRECISION_ROUNDING,
)


async def run_answer_packet_pipeline(
    answer_images: List[str],
    questions: List[dict],
    ocr_service: AbstractOCRService,
    question_paper_pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Run stage 1-9 packet pipeline from in-memory images.
    Returns stage artifacts + final question-wise structured payload.
    """
    blueprint = build_question_blueprint_from_exam_questions(questions)
    allow_pdf_enrich = os.getenv("ANSWER_PACKET_ALLOW_PDF_ENRICH", "false").lower() in ("1", "true", "yes", "on")
    if question_paper_pdf_bytes and allow_pdf_enrich:
        pdf_blueprint = build_question_blueprint_from_pdf(question_paper_pdf_bytes)
        if blueprint and pdf_blueprint:
            by_q_exam = {int(q["question_id"]): q for q in blueprint if q.get("question_id") is not None}
            by_q_pdf = {int(q["question_id"]): q for q in pdf_blueprint if q.get("question_id") is not None}
            merged = []
            for qid in sorted(by_q_exam.keys()):
                q_exam = by_q_exam[qid]
                q_pdf = by_q_pdf.get(qid) or {}
                merged.append(
                    {
                        **q_exam,
                        # Enrich text/type only for existing exam question IDs.
                        "question_text": q_exam.get("question_text") or q_pdf.get("question_text", ""),
                        "rubric": q_exam.get("rubric") or q_pdf.get("rubric", ""),
                        "type": q_exam.get("type") or q_pdf.get("type", "theory"),
                        "expected_components": q_exam.get("expected_components") or q_pdf.get("expected_components", []),
                    }
                )
            dropped_qids = sorted(set(by_q_pdf.keys()) - set(by_q_exam.keys()))
            if dropped_qids:
                logger.warning(
                    "Ignoring %s PDF-only blueprint question IDs not present in exam blueprint: %s",
                    len(dropped_qids),
                    dropped_qids[:20],
                )
            blueprint = merged

    clean_pages = normalize_answer_pages(answer_images)
    page_layout = detect_page_layout(clean_pages)
    region_text = await run_region_ocr(clean_pages, page_layout, ocr_service)
    packets = build_packets(region_text, blueprint)
    aligned = align_packets_to_blueprint(blueprint, packets)

    final_rows: List[dict] = []
    for row in aligned:
        packet = row.get("packet")
        structured = structure_accounting_answer(packet)
        # Use canonical threshold and rounding
        conf = float(packet.get("mapping_confidence", 0.0) or 0.0) if packet else 0.0
        issues: List[str] = []
        if not packet:
            issues.append("missing_packet")
        elif conf < MAPPING_CONFIDENCE_THRESHOLD:
            issues.append("low_mapping_confidence")
        if structured.get("totals"):
            for t in structured["totals"]:
                if t.get("amount") is None:
                    issues.append("uncertain_total")
                    break
        final_rows.append(
            {
                "question_id": int(row["question_id"]),
                "expected": row["expected"],
                "student_answer_structured": structured,
                "confidence": round(conf, PRECISION_ROUNDING),
                "issues": sorted(set(issues)),
                "aligned_by": row.get("aligned_by"),
                "packet": packet,
            }
        )

    return {
        "question_blueprint": blueprint,
        "clean_pages_count": len(clean_pages),
        "page_layout": page_layout,
        "region_text": region_text,
        "packets": packets,
        "aligned_answers": aligned,
        "final_output": final_rows,
    }
