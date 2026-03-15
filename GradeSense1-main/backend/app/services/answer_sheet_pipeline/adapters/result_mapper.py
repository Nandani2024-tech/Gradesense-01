from typing import Any, Dict


def pipeline_result_to_question_map(pipeline_result: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Convert pipeline packets into the question map contract used by grading service."""
    packets = (pipeline_result or {}).get("packets", {}) or {}
    out: Dict[int, Dict[str, Any]] = {}
    for qn, pkt in packets.items():
        if not isinstance(qn, int):
            continue
        text_blocks = pkt.get("text_blocks", []) or []
        segments = [
            {
                "segment_id": blk.get("block_id"),
                "page": blk.get("page_number"),
                "text": blk.get("text", ""),
                "x1": (blk.get("bbox") or [0, 0, 0, 0])[0],
                "y1": (blk.get("bbox") or [0, 0, 0, 0])[1],
                "x2": (blk.get("bbox") or [0, 0, 0, 0])[2],
                "y2": (blk.get("bbox") or [0, 0, 0, 0])[3],
                "tables": [{}] if blk.get("is_table") else [],
            }
            for blk in text_blocks
        ]
        out[int(qn)] = {
            "question_number": int(qn),
            "segments": segments,
            "subquestions": {s.get("sub_id"): s.get("segment_ids", []) for s in (pkt.get("subanswers") or []) if s.get("sub_id")},
            "subanswers": pkt.get("subanswers", []),
            "page_refs": pkt.get("pages", []),
            "tables": [{"segment_id": sid} for sid in (pkt.get("table_segments", []) or [])],
            "table_segments": pkt.get("table_segments", []),
            "working_note_segments": pkt.get("working_note_segments", []),
            "segment_ids": pkt.get("segment_ids", []),
            "combined_text": pkt.get("combined_text", ""),
            "extracted_text": pkt.get("combined_text", ""),
            "subquestion_count": int(pkt.get("subquestion_count", 0) or 0),
            "mapping_confidence": float(pkt.get("mapping_confidence", 0.0) or 0.0),
            "mapping_trace": pkt.get("mapping_trace", []),
            "start_anchor": pkt.get("start_anchor"),
            "end_anchor": pkt.get("end_anchor"),
        }
    meta = packets.get("_meta", {}) if isinstance(packets, dict) else {}
    out["_meta"] = {
        "mapping_coverage": float(meta.get("mapping_coverage", 0.0) or 0.0),
        "packets_generated": int(meta.get("packets_generated", len([k for k in out.keys() if isinstance(k, int)])) or 0),
        "subpacket_count": int(meta.get("subpacket_count", 0) or 0),
        "low_confidence_questions": meta.get("low_confidence_questions", []),
        "consistency_flags": meta.get("consistency_flags", []),
        "page_segment_index": meta.get("page_segment_index", []),
    }
    return out
