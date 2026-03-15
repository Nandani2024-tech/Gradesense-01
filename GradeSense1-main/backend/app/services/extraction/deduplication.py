from typing import List, Dict
from app.core.logging_config import logger
from app.services.extraction.parsing import parse_question_number
from app.services.extraction.utils import (
    _normalize_sub_id,
    _pick_better_text, # Kept as it's used in the function body
    _sub_sort_key,
    _question_number_key # Added as per instruction
)

def _dedupe_and_sort_questions(extracted_questions: List[dict]) -> List[dict]:
    """
    Merge duplicate questions (common in bilingual papers) and return sequential order.
    """
    merged: Dict[int, dict] = {}
    unknowns: List[dict] = []

    for raw in extracted_questions or []:
        q_num = parse_question_number(raw.get("question_number"))
        if q_num is None:
            candidate = dict(raw)
            candidate.setdefault("question_text", "")
            candidate.setdefault("rubric", "")
            candidate.setdefault("sub_questions", [])
            unknowns.append(candidate)
            continue

        candidate = dict(raw)
        candidate["question_number"] = q_num
        candidate.setdefault("question_text", "")
        candidate.setdefault("rubric", "")
        candidate.setdefault("sub_questions", [])

        if q_num not in merged:
            merged[q_num] = candidate
            continue

        existing = merged[q_num]
        
        # Improvement 2: Duplicate Question Detection (Main Level Conflict)
        ex_main = str(existing.get("question_text") or "").strip()
        cand_main = str(candidate.get("question_text") or "").strip()
        if ex_main and cand_main and ex_main.lower() != cand_main.lower() and len(ex_main) > 15 and len(cand_main) > 15:
            logger.warning(f"[DUPLICATE-DETECT] Conflict in Q{q_num} main text. Flagging for review.")
            existing["requires_manual_verification"] = True
            existing["status"] = "duplicate_conflict"
            
        existing["question_text"] = _pick_better_text(existing.get("question_text"), candidate.get("question_text"))
        existing["rubric"] = _pick_better_text(existing.get("rubric"), candidate.get("rubric"))

        # Keep the higher non-zero max marks if duplicates disagree.
        ex_marks = float(existing.get("max_marks") or 0)
        cand_marks = float(candidate.get("max_marks") or 0)
        if cand_marks > ex_marks:
            existing["max_marks"] = cand_marks

        # Merge sub-questions by normalized sub_id.
        existing_subs = { _normalize_sub_id(sq.get("sub_id")): sq for sq in (existing.get("sub_questions") or []) }
        for sq in (candidate.get("sub_questions") or []):
            key = _normalize_sub_id(sq.get("sub_id"))
            if not key:
                continue
            if key not in existing_subs:
                existing_subs[key] = sq
                continue
            
            ex_sq = existing_subs[key]
            
            # Improvement 2: Duplicate Question Detection (Sub Level Conflict)
            ex_rubric = str(ex_sq.get("rubric") or "").strip()
            cand_rubric = str(sq.get("rubric") or "").strip()
            if ex_rubric and cand_rubric and ex_rubric.lower() != cand_rubric.lower() and len(ex_rubric) > 10 and len(cand_rubric) > 10:
                logger.warning(f"[DUPLICATE-DETECT] Conflict in Q{q_num} subpart '{key}'. Flagging for review.")
                existing["requires_manual_verification"] = True
                existing["status"] = "duplicate_conflict"
                
            ex_sq["rubric"] = _pick_better_text(ex_sq.get("rubric"), sq.get("rubric"))
            ex_sq_marks = float(ex_sq.get("max_marks") or 0)
            sq_marks = float(sq.get("max_marks") or 0)
            if sq_marks > ex_sq_marks:
                ex_sq["max_marks"] = sq_marks

        existing["sub_questions"] = sorted(
            list(existing_subs.values()),
            key=lambda s: _sub_sort_key(str(s.get("sub_id", ""))),
        )
        merged[q_num] = existing

    ordered = [merged[q] for q in sorted(merged.keys())]
    return ordered + unknowns
