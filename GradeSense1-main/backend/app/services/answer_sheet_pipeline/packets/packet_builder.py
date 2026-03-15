from typing import Dict, List, Optional


def build_packets(regions: List[dict], blueprint: List[dict]) -> Dict[int, dict]:
    """Stage 5 deterministic packet reconstruction."""
    expected_qs = {int(q["question_id"]) for q in blueprint if q.get("question_id") is not None}
    packets: Dict[int, dict] = {}
    active_q: Optional[int] = None
    last_seen_q: Optional[int] = None
    assigned = 0

    for r in regions:
        qn = r.get("question_anchor")
        if isinstance(qn, int) and qn in expected_qs and not r.get("is_working_note"):
            active_q = qn
            last_seen_q = qn

        chosen: Optional[int] = None
        if active_q in expected_qs:
            chosen = active_q
        elif last_seen_q in expected_qs and (r.get("is_working_note") or r.get("is_table")):
            chosen = last_seen_q
        elif r.get("question_anchor") in expected_qs:
            chosen = int(r["question_anchor"])
            active_q = chosen
            last_seen_q = chosen

        if chosen is None:
            continue

        pkt = packets.setdefault(
            chosen,
            {
                "question_id": chosen,
                "pages": [],
                "text_blocks": [],
                "tables": [],
                "workings": [],
                "subparts": {},
                "segment_ids": [],
                "mapping_trace": [],
                "start_anchor": None,
                "end_anchor": None,
            },
        )
        assigned += 1
        pkt["pages"].append(int(r["page_number"]))
        pkt["segment_ids"].append(str(r["block_id"]))
        pkt["text_blocks"].append(
            {
                "block_id": r["block_id"],
                "page_number": r["page_number"],
                "bbox": r["bbox"],
                "text": r["text"],
                "confidence": r["ocr_confidence"],
                "is_table": bool(r["is_table"]),
                "is_working_note": bool(r["is_working_note"]),
            }
        )
        if r["is_table"]:
            pkt["tables"].append(r["block_id"])
            pkt["mapping_trace"].append("table_sticky")
        if r["is_working_note"]:
            pkt["workings"].append(r["block_id"])
            pkt["mapping_trace"].append("working_note_attach")
        if r.get("subpart_id"):
            sid = str(r["subpart_id"])
            pkt["subparts"].setdefault(sid, []).append(r["block_id"])

        if isinstance(r.get("question_anchor"), int) and r["question_anchor"] == chosen:
            anchor = {
                "page": int(r["page_number"]),
                "y": float(r["bbox"][1]),
                "raw": (r.get("text", "") or "")[:80],
                "segment_id": str(r["block_id"]),
            }
            if pkt["start_anchor"] is None:
                pkt["start_anchor"] = anchor
            pkt["end_anchor"] = anchor
            pkt["mapping_trace"].append("anchor_match")

    for qn, pkt in packets.items():
        pkt["pages"] = sorted(set(pkt["pages"]))
        pkt["segment_ids"] = list(dict.fromkeys(pkt["segment_ids"]))
        pkt["tables"] = list(dict.fromkeys(pkt["tables"]))
        pkt["workings"] = list(dict.fromkeys(pkt["workings"]))
        pkt["mapping_trace"] = list(dict.fromkeys(pkt["mapping_trace"]))
        text = "\n".join(tb["text"] for tb in pkt["text_blocks"] if tb.get("text"))
        confs = [float(tb.get("confidence", 0.0) or 0.0) for tb in pkt["text_blocks"]]
        anchor_bonus = 0.15 if pkt.get("start_anchor") else 0.0
        table_bonus = 0.08 if pkt["tables"] else 0.0
        pkt["combined_text"] = text[:12000]
        pkt["mapping_confidence"] = round(min(0.99, (sum(confs) / max(1, len(confs))) + anchor_bonus + table_bonus), 4)
        pkt["subanswers"] = []
        for sid, block_ids in sorted(pkt["subparts"].items(), key=lambda it: it[0]):
            sid_set = set(block_ids)
            sub_blocks = [b for b in pkt["text_blocks"] if b["block_id"] in sid_set]
            sub_pages = sorted(set(int(b["page_number"]) for b in sub_blocks))
            sub_text = "\n".join(str(b.get("text", "") or "") for b in sub_blocks).strip()
            sub_confs = [float(b.get("confidence", 0.0) or 0.0) for b in sub_blocks]
            pkt["subanswers"].append(
                {
                    "sub_id": sid,
                    "segment_ids": list(dict.fromkeys(block_ids)),
                    "combined_text": sub_text[:5000],
                    "page_refs": sub_pages,
                    "mapping_confidence": round(sum(sub_confs) / max(1, len(sub_confs)), 4),
                }
            )
        pkt["subquestion_count"] = len(pkt["subanswers"])
        pkt["table_segments"] = pkt["tables"]
        pkt["working_note_segments"] = pkt["workings"]

    mapped_count = assigned
    total_regions = len(regions)
    mapping_coverage = mapped_count / total_regions if total_regions > 0 else 0.0
    low_conf = sorted([int(qn) for qn, pkt in packets.items() if float(pkt.get("mapping_confidence", 0.0) or 0.0) < 0.6])
    packets["_meta"] = {
        "mapping_coverage": round(mapping_coverage, 4),
        "packets_generated": len([k for k in packets.keys() if isinstance(k, int)]),
        "subpacket_count": sum(len(pkt.get("subanswers", [])) for qn, pkt in packets.items() if isinstance(qn, int)),
        "low_confidence_questions": low_conf,
        "consistency_flags": ["low_mapping_coverage"] if mapping_coverage < 0.85 else [],
        "page_segment_index": [
            {
                "segment_id": r["block_id"],
                "page": int(r["page_number"]),
                "text": (r.get("text", "") or "")[:600],
                "x1": float(r["bbox"][0]),
                "y1": float(r["bbox"][1]),
                "x2": float(r["bbox"][2]),
                "y2": float(r["bbox"][3]),
            }
            for r in regions
        ],
    }
    return packets
