import asyncio
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from app.core.logging_config import logger
from app.layers.ai_structured.validation import normalize_structure_payload
from app.services.llm.prompts.ai_structured_prompts import build_reconstruction_prompt
from app.infrastructure.serialization.safe_numeric import safe_float as _to_float, safe_int as _to_int
from app.services.pipelines.steps import llm_step, parse_step
from app.services.pipelines.steps import scoring_step, validation_step, repair_step
from app.adapters.interfaces import AbstractLLMService

def extract_structured_question_anchors(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    anchors: List[Dict[str, Any]] = []
    for q in (structure or {}).get("questions") or []:
        qn = _to_int(q.get("number"), 0)
        if qn <= 0:
            continue
        best: Dict[str, Any] = {}
        for ev in (q.get("image_evidence") or []):
            if not isinstance(ev, dict):
                continue
            page = _to_int(ev.get("page_index"), -1)
            bbox = list(ev.get("bbox") or [])
            if page < 0 or len(bbox) != 4:
                continue
            conf = _to_float(ev.get("visual_confidence"), 0.0)
            if not best or conf > best.get("confidence", 0.0):
                best = {
                    "number": qn,
                    "bbox": bbox,
                    "page": page,
                    "confidence": conf,
                    "source": "structured",
                }
        if best:
            anchors.append(best)
    return anchors


def merge_question_anchors(
    visual_questions: List[Dict[str, Any]],
    ocr_anchors: List[Dict[str, Any]],
    structured_anchors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for row in visual_questions:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("number"), 0)
        if qn <= 0:
            continue
        candidates.append(
            {
                "number": qn,
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _to_int(row.get("page"), -1),
                "confidence": _to_float(row.get("confidence"), 0.0),
                "source": str(row.get("source") or "visual"),
            }
        )

    candidates.extend([dict(a) for a in (ocr_anchors or [])])
    candidates.extend([dict(a) for a in (structured_anchors or [])])

    by_number: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for cand in candidates:
        qn = _to_int(cand.get("number"), 0)
        if qn <= 0:
            continue
        by_number[qn].append(cand)

    merged: List[Dict[str, Any]] = []
    for qn, items in by_number.items():
        if not items:
            continue
        visuals = [it for it in items if str(it.get("source") or "").lower() == "visual"]
        ocrs = [it for it in items if str(it.get("source") or "").lower() == "ocr"]
        if visuals:
            batch = visuals
            final_source = "visual"
        elif ocrs:
            batch = ocrs
            final_source = "ocr"
        else:
            batch = items
            final_source = "merged"

        centers: List[Tuple[float, float, int]] = []
        for idx, item in enumerate(batch):
            bbox = item.get("bbox") or [0, 0, 0, 0]
            if len(bbox) != 4:
                bbox = [0, 0, 0, 0]
            cx = (float(bbox[0]) + float(bbox[2])) / 2.0
            cy = (float(bbox[1]) + float(bbox[3])) / 2.0
            centers.append((cx, cy, idx))

        supports: List[int] = []
        for idx in range(len(batch)):
            cx: float = float(centers[idx][0])
            cy: float = float(centers[idx][1])
            page: int = _to_int(batch[idx].get("page"), -1)
            c_val = 0
            for ox, oy, _ in centers:
                dist: float = abs(cx - float(ox)) + abs(cy - float(oy))
                if dist <= 30.0:
                    c_val = c_val + 1
            supports.append(int(c_val))

        best_idx = max(
            range(len(batch)),
            key=lambda i: (
                int(supports[i]),
                float(_to_float(batch[i].get("confidence"), 0.0)),
            ),
        )
        best = batch[best_idx]
        best["source"] = final_source
        merged.append(best)

    merged.sort(key=lambda r: _to_int(r.get("number"), 0))
    return merged


def calculate_average_confidence(items: List[Dict[str, Any]]) -> float:
    vals = [float(row.get("confidence") or 0.0) for row in items if isinstance(row, dict)]
    if not vals:
        return 0.0
    val_sum: float = float(sum(vals))
    val_count: float = float(len(vals))
    avg: float = float(val_sum) / val_count
    # Explicitly cast to float to satisfy picky linters on round()
    result_val = round(float(avg), 4)
    return float(result_val)


async def run_evaluation_pipeline(
    structure: Dict[str, Any],
    visual_entities: Dict[str, Any],
    header_total_marks: Optional[float],
    header_total_reliable: bool,
    header_total_conf: float,
    header_total_source: str,
    expected_question_count: Optional[int],
    raw_ocr_text: str,
    question_paper_images: List[str],
    retry_count: int,
    llm_service: AbstractLLMService,
) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
    # 1. Scoring Step
    reasoned = scoring_step.run_scoring(
        structure,
        visual_entities=visual_entities,
        header_total_marks=header_total_marks,
        header_total_reliable=header_total_reliable,
    )
    structure = reasoned.get("resolved_structure") or structure
    question_audit_tree = list(reasoned.get("question_audit_tree") or [])

    # 2. Validation Step
    validation_report = validation_step.run_validation(
        structure,
        header_total_marks=header_total_marks,
        header_total_reliable=header_total_reliable,
        expected_question_count=expected_question_count,
        visual_entities=visual_entities,
        question_audit_tree=question_audit_tree,
    )
    validation_report["header_total_marks"] = header_total_marks
    validation_report["header_total_reliable"] = header_total_reliable
    validation_report["header_total_confidence"] = header_total_conf
    validation_report["header_total_source"] = header_total_source
    validation_report["mark_override_coverage"] = reasoned.get("mark_override_coverage", 0.0)
    validation_report["effective_marks_map"] = reasoned.get("effective_marks_map") or []
    validation_report["mark_sources"] = {
        "header": 1 if header_total_marks is not None else 0,
        "section_math": len((structure.get("section_math_blocks") or [])),
        "effective_marks_map": len(reasoned.get("effective_marks_map") or []),
    }
    validation_report["visual_entities"] = visual_entities
    validation_report["question_audit_tree"] = question_audit_tree
    validation_report["unresolved_flags"] = []

    ai_reason_mismatches = list(reasoned.get("ai_visual_mismatches") or [])
    if ai_reason_mismatches:
        validation_report.setdefault("warnings", []).append(f"ai_visual_marks_mismatch:{len(ai_reason_mismatches)}")
        validation_report["ai_visual_mismatches"] = ai_reason_mismatches

    # Optional one-time semantic correction retry on validation failure.
    if not validation_report.get("is_valid"):
        errors_now = list(validation_report.get("errors") or [])
        only_subpart_mismatch = bool(errors_now) and all(
            str(err).startswith("subpart_sum_mismatch") for err in errors_now
        )
        if not only_subpart_mismatch:
            logger.warning("RECONSTRUCT_STRUCTURE errors=%s", errors_now)
            try:
                reconstruction_prompt = build_reconstruction_prompt(
                    previous_structure=structure,
                    validation_errors=errors_now or ["unknown_validation_failure"],
                    raw_ocr_text=raw_ocr_text,
                )
                reconstructed_raw = await llm_step.call_extraction_llm(
                    llm_service,
                    reconstruction_prompt,
                    question_paper_images,
                )
                reconstructed_semantic = parse_step.normalize_batch_payload(reconstructed_raw, page_offset=0)
                reconstructed_semantic = parse_step.merge_semantic_with_visual_entities(reconstructed_semantic, visual_entities)
                
                # Re-run scoring for reconstructed structure
                reconstructed_reasoned = scoring_step.run_scoring(
                    reconstructed_semantic,
                    visual_entities=visual_entities,
                    header_total_marks=header_total_marks,
                    header_total_reliable=header_total_reliable,
                )
                reconstructed_structure = reconstructed_reasoned.get("resolved_structure") or reconstructed_semantic
                reconstructed_audit = list(reconstructed_reasoned.get("question_audit_tree") or [])
                
                # Re-run validation for reconstructed structure
                reconstructed_validation = validation_step.run_validation(
                    reconstructed_structure,
                    header_total_marks=header_total_marks,
                    header_total_reliable=header_total_reliable,
                    expected_question_count=expected_question_count,
                    visual_entities=visual_entities,
                    question_audit_tree=reconstructed_audit,
                )
                if len(reconstructed_validation.get("errors") or []) < len(errors_now):
                    structure = reconstructed_structure
                    question_audit_tree = reconstructed_audit
                    validation_report = reconstructed_validation
                    retry_count += 1
            except Exception as exc:
                logger.warning("RECONSTRUCTION_SKIPPED error=%s", exc)

    # 3. Repair Step
    if not validation_report.get("is_valid"):
        repair_result = repair_step.run_repair(
            structure=structure,
            validation_report=validation_report,
            visual_entities=visual_entities,
        )
        repaired_structure = repair_result.get("repaired_structure") or structure
        repaired_audit = list(repair_result.get("question_audit_tree") or question_audit_tree)
        repairs_applied = list(repair_result.get("repairs_applied") or [])
        
        # Final validation after repair
        repaired_validation = validation_step.run_validation(
            repaired_structure,
            header_total_marks=header_total_marks,
            header_total_reliable=header_total_reliable,
            expected_question_count=expected_question_count,
            visual_entities=visual_entities,
            question_audit_tree=repaired_audit,
        )
        repaired_validation["repairs_applied"] = repairs_applied
        repaired_validation["question_audit_tree"] = repaired_audit
        repaired_validation["visual_entities"] = visual_entities
        repaired_validation["unresolved_flags"] = list(repaired_validation.get("errors") or [])
        structure = repaired_structure
        question_audit_tree = repaired_audit
        validation_report = repaired_validation

    # Final payload normalization + freeze-friendly metadata.
    structure = validation_report.get("normalized") or normalize_structure_payload(structure)
    structure["total_questions"] = len(structure.get("questions") or [])
    structure["total_marks"] = float(validation_report.get("effective_total_marks") or 0.0)
    structure["effective_total_marks"] = float(validation_report.get("effective_total_marks") or 0.0)
    structure["numbering_contiguous"] = bool(validation_report.get("numbering_contiguous", False))
    structure["question_audit_tree"] = question_audit_tree
    structure["visual_entities"] = visual_entities
    structure["unresolved_flags"] = list(validation_report.get("errors") or [])
    structure["section_math_rules"] = list(structure.get("section_math_rules") or [])

    confidence_vals = [float(_to_float(q.get("ai_confidence"), 0.0)) for q in (structure.get("questions") or [])]
    if not confidence_vals:
        structure["structure_confidence"] = 0.0
    else:
        conf_avg: float = float(sum(confidence_vals)) / float(len(confidence_vals))
        final_conf = round(float(conf_avg), 4)
        structure["structure_confidence"] = float(final_conf)

    validation_report["question_audit_tree"] = question_audit_tree
    validation_report["visual_entities"] = visual_entities
    validation_report["unresolved_flags"] = list(validation_report.get("errors") or [])
    validation_report["section_math_rules"] = list(structure.get("section_math_rules") or [])

    return structure, validation_report, retry_count
