import os
from typing import List, Dict, Any, Optional, Set, Tuple
from app.core.logging_config import logger

from .config import (
    _env_bool,
    _dedupe_preserve_order,
    ANCHOR_LEFT_RATIO,
    MAPPING_COVERAGE_MIN,
    SPARSE_WORD_THRESHOLD,
    SEMANTIC_REPAIR_SIM_MIN,
    SEMANTIC_OVERRIDE_ANCHOR,
    SPARSE_ALLOW_ANCHOR,
)
from .margin_detection import detect_margin_labels, normalize_question_number, _segment_has_label, _token_count
from app.utils.identity_manager import normalize_question_id
from .subquestion_detection import _build_subanswer_packets
from .segment_analysis import (
    _bbox,
    _bbox_center,
    _merge_bbox,
    _vertical_overlaps,
    _is_table_segment,
    _is_working_note_segment,
    _jaccard_similarity,
)


def _new_packet(question_id: str) -> Dict[str, Any]:
    return {
        "question_number": str(question_id),
        "segments": [],
        "subquestions": {},
        "subanswers": [],
        "page_refs": set(),
        "tables": [],
        "table_segments": [],
        "working_note_segments": [],
        "segment_ids": [],
        "mapping_trace": [],
        "mapping_confidence": 0.0,
        "start_anchor": None,
        "end_anchor": None,
        "_stats": {
            "anchors": 0,
            "sparse_assignments": 0,
            "semantic_repairs": 0,
            "sticky_table_assignments": 0,
            "working_note_assignments": 0,
        },
    }


def _append_trace(entry: Dict[str, Any], trace: str) -> None:
    traces = entry.setdefault("mapping_trace", [])
    if trace not in traces:
        traces.append(trace)


def _compute_mapping_confidence(entry: Dict[str, Any]) -> float:
    stats = entry.get("_stats", {})
    score = 0.45
    if stats.get("anchors", 0) > 0:
        score += 0.24
    if len(entry.get("page_refs") or []) > 1:
        score += 0.08
    if entry.get("table_segments"):
        score += 0.05
    if entry.get("working_note_segments"):
        score += 0.04
    score -= min(0.18, 0.04 * int(stats.get("sparse_assignments", 0)))
    score -= min(0.22, 0.06 * int(stats.get("semantic_repairs", 0)))
    return max(0.0, min(0.99, score))


def _nearest_previous_question(
    seg: Dict[str, Any],
    page_num: int,
    question_history: List[Dict[str, Any]],
) -> Optional[int]:
    if not question_history:
        return None
    sbox = _bbox(seg)
    scx, scy = _bbox_center(sbox)
    best_q: Optional[str] = None
    best_score = None
    for item in question_history:
        if int(item.get("page", 0)) > page_num:
            continue
        qbox = item.get("bbox")
        if not qbox:
            continue
        qcx, qcy = _bbox_center(qbox)
        page_gap = max(0, page_num - int(item.get("page", 0)))
        score = (page_gap * 2400.0) + abs(scx - qcx) + abs(scy - qcy)
        if best_score is None or score < best_score:
            best_score = score
            best_q = str(item["question_number"])
    return best_q


def map_segments_to_questions(
    segments_by_page: List[List[Dict[str, Any]]],
    words_by_page: List[List[Dict[str, Any]]],
    expected_questions: List[Any],
    page_widths: List[float],
) -> Dict[str, Dict[str, Any]]:
    sparse_word_threshold = int(os.getenv("SPARSE_WORD_THRESHOLD", str(SPARSE_WORD_THRESHOLD)))
    mapping_coverage_min = float(os.getenv("MAPPING_COVERAGE_MIN", str(MAPPING_COVERAGE_MIN)))
    semantic_repair_sim_min = float(os.getenv("SEMANTIC_REPAIR_SIM_MIN", str(SEMANTIC_REPAIR_SIM_MIN)))
    semantic_override_anchor = _env_bool("SEMANTIC_OVERRIDE_ANCHOR", SEMANTIC_OVERRIDE_ANCHOR)
    sparse_allow_anchor = _env_bool("SPARSE_ALLOW_ANCHOR", SPARSE_ALLOW_ANCHOR)
    expected_ids = {normalize_question_id(str(q)) for q in expected_questions if q}
    mapped: Dict[str, Dict[str, Any]] = {}
    per_page_metrics: List[Dict[str, Any]] = []
    question_history: List[Dict[str, Any]] = []
    segment_meta: Dict[str, Dict[str, Any]] = {}
    anchor_by_segment_id: Dict[str, Dict[str, Any]] = {}
    anchors_by_page: Dict[int, List[Dict[str, Any]]] = {}
    total_segments = 0
    assigned_segment_ids: Set[str] = set()
    unassigned_segments: List[Dict[str, Any]] = []

    for page_idx, segments in enumerate(segments_by_page):
        page_num = page_idx + 1
        width = page_widths[page_idx] if page_idx < len(page_widths) else 1000.0
        page_words_raw = words_by_page[page_idx] if page_idx < len(words_by_page) else []
        page_words = len(page_words_raw)
        sparse_page = page_words < sparse_word_threshold

        page_margin_labels = detect_margin_labels(
            words=page_words_raw,
            expected_ids=expected_ids,
            width=width,
            page_num=page_num,
            left_ratio=ANCHOR_LEFT_RATIO,
            right_ratio=1.0,
        )
        sorted_segments = sorted(segments, key=lambda s: (float(s.get("y1", 0.0)), float(s.get("x1", 0.0))))

        labels_detected = 0
        for seg in sorted_segments:
            seg_id = str(seg.get("segment_id") or f"P{page_num}-S{len(segment_meta) + 1}")
            seg_text = str(seg.get("text", "")).strip()
            if not seg_text:
                continue
            total_segments += 1

            seg_box = _bbox(seg)
            seg_h = max(1.0, seg_box[3] - seg_box[1])
            token_count = _token_count(seg_text)
            in_left_margin = float(seg.get("x1", 0.0)) <= width * ANCHOR_LEFT_RATIO
            has_label = _segment_has_label(seg_text)
            if in_left_margin and has_label:
                labels_detected += 1
            overlapping_page_labels = [
                lb
                for lb in page_margin_labels
                if (seg_box[1] - max(10.0, seg_h * 0.8)) <= float(lb.get("y", 0.0)) <= (seg_box[3] + max(10.0, seg_h * 0.8))
            ]
            margin_q = str(overlapping_page_labels[0]["question_number"]) if overlapping_page_labels else None
            detected_q = margin_q
            if detected_q is None:
                detected_q = normalize_question_number(seg_text, expected_ids=expected_ids, page_num=page_num)
            is_table = _is_table_segment(seg, seg_text)
            is_working_note = _is_working_note_segment(seg_text)
            
            has_margin_anchor = margin_q is not None
            has_segment_anchor = in_left_margin and has_label and token_count >= 1
            strong_anchor = (
                (not sparse_page or sparse_allow_anchor)
                and (has_margin_anchor or has_segment_anchor)
                and detected_q in expected_ids
                and not is_working_note
            )

            seg["_is_table_segment"] = is_table
            seg["_is_working_note"] = is_working_note

            segment_meta[seg_id] = {
                "segment_id": seg_id,
                "page": page_num,
                "bbox": seg_box,
                "token_count": token_count,
                "in_left_margin": in_left_margin,
                "has_label": has_label,
                "sparse_page": sparse_page,
                "is_table": is_table,
                "is_working_note": is_working_note,
                "strong_anchor": strong_anchor,
                "detected_q": detected_q if detected_q in expected_ids else None,
                "text": seg_text,
                "seg": seg,
            }
            if strong_anchor and detected_q is not None:
                anchors_by_page.setdefault(page_num, []).append(
                    {
                        "question_number": str(detected_q),
                        "segment_id": seg_id,
                        "page": page_num,
                        "y": float(seg.get("y1", 0.0)),
                        "bbox": seg_box,
                        "raw": seg_text[:80],
                    }
                )

        anchors = sorted(anchors_by_page.get(page_num, []), key=lambda a: (float(a["y"]), str(a["segment_id"])))
        deduped_anchors: List[Dict[str, Any]] = []
        for anchor in anchors:
            if deduped_anchors:
                prev = deduped_anchors[-1]
                if (
                    str(prev["question_number"]) == str(anchor["question_number"])
                    and abs(float(prev["y"]) - float(anchor["y"])) <= 10.0
                ):
                    continue
            deduped_anchors.append(anchor)
        anchors_by_page[page_num] = deduped_anchors
        for anchor in deduped_anchors:
            anchor_by_segment_id[anchor["segment_id"]] = anchor

        per_page_metrics.append(
            {
                "page": page_num,
                "segments": len(sorted_segments),
                "labels_detected": labels_detected,
                "anchors_detected": len(deduped_anchors),
                "questions_assigned": [],
                "questions_assigned_count": 0,
                "sparse": sparse_page,
                "word_count": page_words,
            }
        )

    active_q: Optional[str] = None
    question_bbox: Dict[str, Tuple[float, float, float, float]] = {}
    per_page_assigned: Dict[int, Set[str]] = {}
    first_page_for_q: Dict[int, int] = {}

    for page_idx, segments in enumerate(segments_by_page):
        page_num = page_idx + 1
        sorted_segments = sorted(segments, key=lambda s: (float(s.get("y1", 0.0)), float(s.get("x1", 0.0))))
        page_has_anchor = bool(anchors_by_page.get(page_num))
        page_sparse = False
        if sorted_segments:
            first_seg_id = str(sorted_segments[0].get("segment_id") or "")
            if first_seg_id in segment_meta:
                page_sparse = bool(segment_meta[first_seg_id].get("sparse_page", False))
        page_active_q: Optional[str] = active_q if (not page_has_anchor and not page_sparse) else None

        for seg in sorted_segments:
            seg_id = str(seg.get("segment_id") or "")
            if not seg_id or seg_id not in segment_meta:
                continue
            meta = segment_meta[seg_id]
            if not str(seg.get("text", "")).strip():
                continue

            anchor = anchor_by_segment_id.get(seg_id)
            chosen_q: Optional[str] = None

            if anchor:
                chosen_q = str(anchor["question_number"])
                page_active_q = chosen_q
                active_q = chosen_q
            else:
                if page_active_q is not None and page_active_q in expected_ids:
                    chosen_q = page_active_q
                elif meta["sparse_page"]:
                    chosen_q = _nearest_previous_question(seg, page_num, question_history)
                    if chosen_q in expected_ids:
                        page_active_q = chosen_q
                        _append_trace(mapped.setdefault(chosen_q, _new_packet(chosen_q)), "sparse_attach")
                        mapped[chosen_q]["_stats"]["sparse_assignments"] += 1
                elif meta["is_working_note"]:
                    chosen_q = active_q or _nearest_previous_question(seg, page_num, question_history)
                    if chosen_q in expected_ids:
                        page_active_q = chosen_q
                        _append_trace(mapped.setdefault(chosen_q, _new_packet(chosen_q)), "working_note_attach")
                        mapped[chosen_q]["_stats"]["working_note_assignments"] += 1
                elif meta["is_character_note"] if "is_character_note" in meta else meta.get("is_working_note"): # safety
                     pass # handled above
                elif meta["is_table"]:
                    chosen_q = active_q or _nearest_previous_question(seg, page_num, question_history)
                    if chosen_q in expected_ids:
                        page_active_q = chosen_q
                        _append_trace(mapped.setdefault(chosen_q, _new_packet(chosen_q)), "table_sticky")
                        mapped[chosen_q]["_stats"]["sticky_table_assignments"] += 1
                elif not page_has_anchor and active_q in expected_ids:
                    chosen_q = active_q
                    page_active_q = chosen_q
                    _append_trace(mapped.setdefault(chosen_q, _new_packet(chosen_q)), "cross_page_merge")
                else:
                    if active_q in question_bbox:
                        candidate_box = question_bbox[active_q]
                        if _vertical_overlaps(meta["bbox"], candidate_box):
                            chosen_q = active_q
                            page_active_q = chosen_q

            if chosen_q is None or chosen_q not in expected_ids:
                unassigned_segments.append(meta)
                continue

            entry = mapped.setdefault(chosen_q, _new_packet(chosen_q))
            entry["segments"].append(seg)
            entry["page_refs"].add(int(seg.get("page", page_num) or page_num))
            if meta["is_table"]:
                entry["table_segments"].append(seg_id)
            if meta["is_working_note"]:
                entry["working_note_segments"].append(seg_id)
            for t in seg.get("tables", []) or []:
                entry["tables"].append(t)

            if anchor:
                entry["_stats"]["anchors"] += 1
                _append_trace(entry, "anchor_match")
                anchor_payload = {
                    "page": page_num,
                    "y": float(seg.get("y1", 0.0)),
                    "raw": str(seg.get("text", "")).strip()[:80],
                    "segment_id": seg_id,
                }
                if not entry.get("start_anchor"):
                    entry["start_anchor"] = anchor_payload
                entry["end_anchor"] = anchor_payload
            if chosen_q not in first_page_for_q:
                first_page_for_q[chosen_q] = page_num
            elif first_page_for_q.get(chosen_q) != page_num:
                _append_trace(entry, "cross_page_merge")

            box = meta["bbox"]
            if chosen_q in question_bbox:
                question_bbox[chosen_q] = _merge_bbox(question_bbox[chosen_q], box)
            else:
                question_bbox[chosen_q] = box
            question_history.append({"question_number": chosen_q, "bbox": box, "page": page_num})

            assigned_segment_ids.add(seg_id)
            per_page_assigned.setdefault(page_num, set()).add(chosen_q)
            active_q = chosen_q

    # Task 9 Cleanup: Removed semantic_repair fallback. 
    # Unassigned segments are now explicitly left unmapped for traceability.
    if unassigned_segments:
        logger.info(f"[Mapping] {len(unassigned_segments)} segments left unassigned (deterministic mapping)")

    low_confidence_questions: List[str] = []
    subpacket_count = 0
    for q_num, item in mapped.items():
        if not isinstance(q_num, str):
            continue
        item["page_refs"] = sorted({int(p) for p in (item.get("page_refs") or [])})
        item["segments"].sort(key=lambda s: (int(s.get("page", 1) or 1), float(s.get("y1", 0.0))))
        item["segment_ids"] = _dedupe_preserve_order([str(s.get("segment_id")) for s in item["segments"] if s.get("segment_id")])
        item["table_segments"] = _dedupe_preserve_order(item.get("table_segments") or [])
        item["working_note_segments"] = _dedupe_preserve_order(item.get("working_note_segments") or [])
        combined_text = " ".join(str(s.get("text", "")).strip() for s in item["segments"]).strip()
        item["combined_text"] = combined_text[:12000]
        item["extracted_text"] = item["combined_text"]
        item["mapping_trace"] = _dedupe_preserve_order(item.get("mapping_trace") or [])
        item["mapping_confidence"] = _compute_mapping_confidence(item)
        _build_subanswer_packets(item)
        subpacket_count += len(item.get("subanswers") or [])
        if item["mapping_confidence"] < 0.65:
            low_confidence_questions.append(str(q_num))
        item.pop("_stats", None)

    page_metric_index = {int(m["page"]): m for m in per_page_metrics}
    for page_num, assigned in per_page_assigned.items():
        pm = page_metric_index.get(int(page_num))
        if not pm:
            continue
        pm["questions_assigned"] = sorted(str(q) for q in assigned)
        pm["questions_assigned_count"] = len(assigned)

    mapped_count = len(assigned_segment_ids)
    mapping_coverage = (mapped_count / total_segments) if total_segments > 0 else 0.0
    consistency_flags: List[str] = []
    if mapping_coverage < mapping_coverage_min:
        consistency_flags.append("low_mapping_coverage")
    if low_confidence_questions:
        consistency_flags.append("low_confidence_packets")

    mapped["_meta"] = {
        "per_page": per_page_metrics,
        "mapping_coverage": round(mapping_coverage, 4),
        "packets_generated": len([k for k in mapped.keys() if isinstance(k, str) and k != "_meta"]),
        "subpacket_count": subpacket_count,
        "low_confidence_questions": sorted(set(low_confidence_questions)),
        "consistency_flags": consistency_flags,
    }
    return mapped
