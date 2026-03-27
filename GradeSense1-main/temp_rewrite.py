import sys
import re

filepath = r"c:\BaseLine\GradeSense1-main\backend\app\services\pipelines\ai_extraction_service.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("def _merge_semantic_with_visual_entities("):
        start_idx = i
    if line.startswith("def _clip_to_expected_question_count("):
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print("Could not find function boundaries")
    sys.exit(1)

new_func = """def _merge_semantic_with_visual_entities(
    stage2_structure: Dict[str, Any],
    visual_entities: Dict[str, Any],
    page_ocr_texts: Optional[List[str]] = None,
    full_ocr_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    from app.utils.identity_manager import build_question_uid, normalize_section
    import copy
    import re

    def _demote_choice_subparts(question: Dict[str, Any]) -> bool:
        subparts = list(question.get("subquestions") or [])
        if not subparts: return False
        qtype = str((question or {}).get("question_type") or "").strip().lower()
        if qtype in {"passage", "passage_subparts"}: return False
        for sq in subparts:
            if _to_float(sq.get("marks"), 0.0) > 0 and str(sq.get("mark_source") or "").strip().lower() in {"margin", "section_math", "instruction"}:
                return False
        raw_text = f"{question.get('instruction') or ''}\\n{question.get('question_text') or ''}"
        text = raw_text.lower()
        choice_phrases = ["any one", "any of the following", "attempt any one", "choose any one", "either of the following", "alternative question", "in lieu of"]
        has_choice_signal = any(phrase in text for phrase in choice_phrases) or bool(re.search(r"(^|\\n)\\s*or\\s*(\\n|$)", raw_text, flags=re.IGNORECASE)) or qtype == "mcq"
        if not has_choice_signal: return False
        options = list(question.get("options") or [])
        preserved_subquestions = []
        demoted_any = False
        for sq in subparts:
            opt = str(sq.get("text") or "").strip()
            if qtype != "mcq" and opt and _to_float(sq.get("marks"), 0.0) > 0:
                preserved_subquestions.append(sq)
            else:
                if opt and opt not in options: options.append(opt)
                demoted_any = True
        if options: question["options"] = options
        question["subquestions"] = preserved_subquestions
        return demoted_any

    def _allows_visual_subparts(question: Dict[str, Any]) -> bool:
        qtype = str((question or {}).get("question_type") or "").strip().lower()
        if qtype in {"mcq", "fill_blank", "very_short", "writing", "letter", "essay"}: return False
        options = (question or {}).get("options")
        if isinstance(options, list) and len(options) >= 2: return False
        return qtype in {"short", "long", "passage", "passage_subparts", "descriptive_choice", "or_group"}

    def _extract_header_context(text: str) -> Dict[str, Any]:
        res = {"marks": None, "range": None, "instruction": text}
        if not text: return res
        marks_match = re.search(r"(\\d+(?:\\.\\d+)?)\\s*marks?\\s*(?:each)?", text, re.I)
        if marks_match: res["marks"] = float(marks_match.group(1))
        else:
            simple_marks = re.search(r"\\((\\d+(?:\\.\\d+)?)\\)", text)
            if simple_marks: res["marks"] = float(simple_marks.group(1))
        range_match = re.search(r"(?:questions?|qn?\\.?)\\s*(\\d+)\\s*(?:to|-)\\s*(\\d+)", text, re.I)
        if range_match: res["range"] = (int(range_match.group(1)), int(range_match.group(2)))
        return res

    def _is_bbox_overlap(b1: List[float], b2: List[float], threshold: float = 0.5) -> bool:
        if not b1 or not b2 or len(b1) != 4 or len(b2) != 4: return False
        x_left = max(b1[0], b2[0])
        y_top = max(b1[1], b2[1])
        x_right = min(b1[2], b2[2])
        y_bottom = min(b1[3], b2[3])
        if x_right < x_left or y_bottom < y_top: return False
        overlap_area = (x_right - x_left) * (y_bottom - y_top)
        area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        return overlap_area / max(1e-5, area1) >= threshold

    semantic_questions = stage2_structure.get("questions") or []
    visual_anchors = (visual_entities or {}).get("questions") or []
    
    logger.info("LOG TAG: VISUAL_MERGE_START semantic_count=%s visual_anchors=%s", len(semantic_questions), len(visual_anchors))

    # 1. Header Contexts for spatial section assignment
    header_contexts = []
    for h in sorted((visual_entities or {}).get("headers") or [], 
                    key=lambda x: (_to_int(x.get("page"), 0), (x.get("bbox") or [0])[0])):
        h_text = str(h.get("text") or "").strip()
        ctx = _extract_header_context(h_text)
        ctx.update({"page": _to_int(h.get("page"), 0), "ymin": (h.get("bbox") or [0])[0], "instruction": h_text})
        header_contexts.append(ctx)

    # 2. VISUAL-FIRST MERGE: Build visual map as Source of Truth
    visual_map = {}
    ordered_keys = []
    
    for anchor in visual_anchors:
        if not isinstance(anchor, dict): continue
        qn = _parse_question_number(anchor.get("number"))
        if qn is None: continue
        
        p_idx = _to_int(anchor.get("page"), 0)
        a_bbox = anchor.get("bbox") or [0, 0, 0, 0]
        
        # Spatial section logic
        a_ymin = a_bbox[0] if a_bbox else 0
        spatial_sec = None
        for ctx in header_contexts:
            if ctx["page"] < p_idx or (ctx["page"] == p_idx and ctx["ymin"] < a_ymin):
                spatial_sec = ctx["instruction"]
            else: break
            
        base_key = (p_idx, tuple(a_bbox))
        idx = 0
        key = (base_key[0], base_key[1], idx)
        while key in visual_map:
            idx += 1
            key = (base_key[0], base_key[1], idx)
            
        ordered_keys.append(key)
        visual_map[key] = {
            "number": qn,
            "page": p_idx,
            "bbox": a_bbox,
            "confidence": _to_float(anchor.get("confidence"), 0.0),
            "section": spatial_sec,
            "candidates": [],
            "subquestions": copy.deepcopy(anchor.get("subquestions", [])),
            "original_anchor": copy.deepcopy(anchor),
        }

    # Detect overlaps
    for i in range(len(ordered_keys)):
        for j in range(i + 1, len(ordered_keys)):
            k1 = ordered_keys[i]
            k2 = ordered_keys[j]
            if k1[0] == k2[0] and _is_bbox_overlap(list(k1[1]), list(k2[1]), 0.5):
                logger.warning("LOG TAG: VISUAL_OVERLAP_DETECTED anchors >50%% page=%s box1=%s box2=%s", k1[0], k1[1], k2[1])

    # 3. SEMANTIC ENRICHMENT
    for sq in semantic_questions:
        best_key = None
        evs = sq.get("image_evidence") or []
        sq_page = _to_int(evs[0].get("page_index"), -1) if evs else -1
        sq_bbox = evs[0].get("bbox") if evs else None
        sq_num = _to_int(sq.get("number"), 0)
        
        # Priority 1: Match by page and bbox overlap > 50%
        if sq_page >= 0 and sq_bbox:
            for k in ordered_keys:
                if k[0] == sq_page and _is_bbox_overlap(sq_bbox, list(k[1]), 0.5):
                    best_key = k
                    break
                    
        # Priority 2: Fallback exact number match (since sections are removed from primary keys)
        if not best_key:
            for k in ordered_keys:
                if visual_map[k]["number"] == sq_num:
                    best_key = k
                    break
                    
        if best_key:
            visual_map[best_key]["candidates"].append(sq)
        else:
            logger.warning("LOG TAG: MISSING_SEMANTIC_MATCH number=%s section=%s", sq_num, sq.get("section"))

    logger.info("LOG TAG: VISUAL_MERGE_AFTER_SEMANTIC Total matched semantic enrichment candidates=%s", sum(len(v["candidates"]) for v in visual_map.values()))

    # 4. RESOLVE FINAL QUESTIONS
    final_questions = []
    final_q_by_key = {}
    
    for key in ordered_keys:
        v_node = visual_map[key]
        qn = v_node["number"]
        spatial_sec = v_node["section"]
        candidates = v_node["candidates"]
        
        if len(candidates) > 1:
            logger.warning("LOG TAG: SEMANTIC_CONFLICT Multiple semantics match visual anchor page=%s bbox=%s", key[0], key[1])
            
        best_cand = None
        if candidates:
            best_cand = max(candidates, key=lambda c: len(str(c.get("question_text") or "")))
            
        final_q = dict(v_node["original_anchor"])
        final_q["number"] = qn
        final_q["raw_number"] = str(qn)
        
        if best_cand:
            final_q["question_text"] = best_cand.get("question_text", "")
            final_q["question_type"] = best_cand.get("question_type", final_q.get("question_type") or "descriptive")
            if best_cand.get("question_uid"):
                final_q["question_uid"] = best_cand["question_uid"]
                final_q["uid"] = best_cand["uid"]
        else:
            final_q["question_text"] = ""
            final_q["question_type"] = final_q.get("question_type") or "descriptive"
            
        if "question_uid" not in final_q:
            uid = build_question_uid(spatial_sec or "default", qn)
            final_q["question_uid"] = f"{uid}_{key[0]}_{key[2]}"
            final_q["uid"] = final_q["question_uid"]
            
        final_q["section"] = final_q.get("section") or spatial_sec
        final_q["subquestions"] = v_node["subquestions"]
        
        ev = {
            "page_index": key[0],
            "bbox": list(key[1]),
            "visual_confidence": v_node["confidence"]
        }
        if "image_evidence" not in final_q or not final_q["image_evidence"]:
            final_q["image_evidence"] = []
        final_q["image_evidence"].append(ev)
        
        p_idx = key[0]
        a_bbox = key[1]
        
        llm_text = str(final_q.get("question_text") or "").strip()
        if not llm_text and full_ocr_results and 0 <= p_idx < len(full_ocr_results):
            lines = [str(L.get("text") or "").strip() for L in full_ocr_results[p_idx].get("lines", []) 
                     if _is_bbox_within(L.get("bbox"), list(a_bbox), threshold=0.5)]
            if lines:
                final_q["question_text"] = " ".join(lines)[:1024]
                final_q["question_text_source"] = "ocr_spatial_p3"
                
        matched_header = None
        for ctx in header_contexts:
            if ctx["range"] and ctx["range"][0] <= qn <= ctx["range"][1]: matched_header = ctx; break
            if ctx["page"] < p_idx or (ctx["page"] == p_idx and ctx["ymin"] < a_bbox[0]): matched_header = ctx
            else: break
        
        if matched_header and matched_header["marks"] is not None and _to_float(final_q.get("marks"), 0.0) <= 0:
            final_q["marks"] = matched_header["marks"]
            final_q["mark_source"] = "header_propagation"
            
        final_questions.append(final_q)
        final_q_by_key[key] = final_q

    for q in final_questions:
        _demote_choice_subparts(q)

    # 5. Visual Subparts and OR groups sync based on strict spatial / number match
    for row in (visual_entities or {}).get("subparts") or []:
        qn_sub = _to_int(row.get("q"), 0)
        label = str(row.get("label") or "").strip()
        if qn_sub <= 0 or not label: continue
        
        s_page = _to_int(row.get("page"), 0)
        s_bbox = row.get("bbox") or []
        
        target_q = None
        if s_bbox:
            for k in ordered_keys:
                if k[0] == s_page and visual_map[k]["number"] == qn_sub:
                    if _is_bbox_overlap(s_bbox, list(k[1]), 0.1):
                        target_q = final_q_by_key[k]
                        break
        if not target_q:
            for k in ordered_keys:
                if k[0] == s_page and visual_map[k]["number"] == qn_sub:
                    target_q = final_q_by_key[k]
                    break
        if not target_q:
            for k in ordered_keys:
                if visual_map[k]["number"] == qn_sub:
                    target_q = final_q_by_key[k]
                    break
                    
        if target_q and _allows_visual_subparts(target_q):
            subs = target_q.get("subquestions") or []
            ev = {"page_index": s_page, "bbox": s_bbox, "visual_confidence": _to_float(row.get("confidence"), 0.0)}
            norm_label = label.lower()
            match_found = False
            for sq in subs:
                if str(sq.get("label") or "").strip().lower() == norm_label:
                    sq.setdefault("image_evidence", []).append(ev)
                    sq["confidence"] = max(_to_float(sq.get("confidence"), 0.0), _to_float(row.get("confidence"), 0.0))
                    match_found = True; break
            
            if not match_found:
                subs.append({
                    "label": label, "text": "", "marks": 0.0, "mark_source": "inferred",
                    "confidence": _to_float(row.get("confidence"), 0.0), "image_evidence": [ev],
                    "source": "visual_gap_fill_matched"
                })
                target_q["subquestions"] = sorted(subs, key=lambda s: str(s.get("label") or "").strip().lower())

    # Map OR IDs without relying on (section, number) generated UIDs
    or_map = _build_or_groups_from_visual(visual_entities)
    for qn_or, gid in or_map.items():
        for k in ordered_keys:
            if visual_map[k]["number"] == qn_or:
                final_q_by_key[k]["or_group_id"] = gid

    section_math_blocks = []
    for row in (visual_entities or {}).get("section_math") or []:
        if isinstance(row, dict):
            section_math_blocks.append({
                "section": None, "expression": str(row.get("expr") or ""),
                "question_count": _to_int(row.get("count"), 0),
                "per_question_marks": _to_float(row.get("per"), 0.0),
                "total_marks": _to_float(row.get("total"), 0.0),
                "page_index": _to_int(row.get("page"), 0),
                "confidence": _to_float(row.get("confidence"), 0.0),
            })

    logger.info("LOG TAG: VISUAL_MERGE_FINAL_OUTPUT final_questions=%s", len(final_questions))

    # Strict assertion
    assert len(final_questions) == len(ordered_keys), "Visual anchor count mismatch"

    merged = {
        "questions": sorted(final_questions, key=lambda q: (str(q.get("section") or ""), _to_int(q.get("number"), 0))),
        "section_math_blocks": section_math_blocks,
        "total_questions": len(final_questions),
        "total_marks": 0.0,
    }
    
    return normalize_structure_payload(merged)
"""

new_lines = lines[:start_idx] + [new_func + "\n\n"] + lines[end_idx:]

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Replaced successfully.")
