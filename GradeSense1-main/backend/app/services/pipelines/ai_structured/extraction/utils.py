import re
import math
from typing import Any, Dict, List, Optional, Tuple
from app.core.logging_config import logger
from app.services.pipelines.ai_structured.extraction.validation import (
    normalize_structure_payload,
    compute_effective_total,
    compute_paper_effective_total,
)
from app.services.pipelines.ai_structured.utils.common import _to_float


def _structure_confidence(structure: Dict[str, Any]) -> float:
    confidences = [_to_float(q.get("ai_confidence"), 0.0) for q in (structure.get("questions") or [])]
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences), 2)


def _extract_marks_from_ma_headers(ma_text: Optional[str]) -> List[Dict[str, Any]]:
    """
    Parses Model Answer text for section-level mark instructions.
    Pattern: SECTION A (1 Mark Each), Q2-Q20 - 2 Marks, etc.
    """
    if not ma_text:
        return []
        
    rules = []
    # Pattern 1: SECTION X (Y Mark(s) Each)
    sec_matches = re.finditer(r"SECTION\s+([A-D])\s*\((\d+)\s*Marks?\s+Each\)", ma_text, re.IGNORECASE)
    for m in sec_matches:
        rules.append({
            "section": f"section {m.group(1).lower()}",
            "marks": _to_float(m.group(2), 0.0),
            "source": "inferred_from_ma_header"
        })
        
    # Pattern 2: Q(N)-Q(M) - (Y) Marks
    range_matches = re.finditer(r"Q(\d+)\s*[-–to]+?\s*Q(\d+)\s*[-–\s]+?(\d+)\s*Marks?", ma_text, re.IGNORECASE)
    for m in range_matches:
        rules.append({
            "range": (int(m.group(1)), int(m.group(2))),
            "marks": _to_float(m.group(3), 0.0),
            "source": "inferred_from_ma_header"
        })
        
    return rules


def _apply_audit_tree_marks(structure: Dict[str, Any], question_audit_tree: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    normalized = normalize_structure_payload(structure or {})
    audit_rows = [row for row in (question_audit_tree or []) if isinstance(row, dict)]
    
    # 1. Identity Map
    by_uid: Dict[str, Dict[str, Any]] = {
        str(q.get("question_uid")): q
        for q in (normalized.get("questions") or [])
        if q.get("question_uid")
    }
    
    # Track "Before" state for Dry-Run report
    before_marks = {uid: _to_float(q.get("marks"), 0.0) for uid, q in by_uid.items()}
    reconciliation_details = []

    # 2. Audit Tree Application (Highest Confidence: Direct Manual or LLM Observation)
    for row in audit_rows:
        qn = int(row.get("number") or 0)
        if qn <= 0:
            continue
        target_qs = [q for q in by_uid.values() if int(q.get("number") or 0) == qn]
        for q in target_qs:
            prev_m = _to_float(q.get("marks"), 0.0)
            new_m = _to_float(row.get("total_marks"), prev_m)
            if new_m != prev_m:
                q["marks"] = new_m
                q["mark_source"] = str(row.get("mark_source") or q.get("mark_source") or "audit_tree")
                q["distribution_mode"] = str(row.get("distribution_mode") or q.get("distribution_mode") or "direct")
                q["evidence_refs"] = list(row.get("evidence_refs") or q.get("evidence_refs") or [])

    questions = [by_uid[str(q.get("question_uid"))] for q in (normalized.get("questions") or []) if q.get("question_uid")]
    
    # 3. RANGE-AWARE Math Block Inference (Resolves Global Rules with null sections)
    math_blocks = normalized.get("section_math_blocks") or []
    for q in questions:
        # SAFEGUARD: skip if already has marks, or if optional/unselected OR group
        if _to_float(q.get("marks"), 0.0) > 0 or q.get("or_group_id") or q.get("question_type") == "optional":
            continue
            
        q_num = int(q.get("number") or 0)
        # Normalize section: replace underscore with space for robust matching
        q_sec = str(q.get("section") or "").strip().lower().replace("_", " ")
        
        # Priority: Range Match > Section Name Match (only if no range on block)
        matched_block = None
        for b in math_blocks:
            r = b.get("range")
            if r:
                # If block has a range, it MUST match the question number range
                if q_num >= int(r.get("start", 0)) and q_num <= int(r.get("end", 0)):
                    matched_block = b
                    break
            elif b.get("section"):
                b_sec = str(b.get("section")).strip().lower().replace("_", " ")
                if b_sec == q_sec:
                    # If block has NO range, it can match the entire section
                    matched_block = b
                    break
        
        if matched_block and _to_float(matched_block.get("per_question_marks"), 0.0) > 0:
            q["marks"] = _to_float(matched_block.get("per_question_marks"), 0.0)
            q["mark_source"] = "inferred_from_range_block"
            logger.info("IAI_RECONCILE: question=%s mark=%s source=range_block", q_num, q["marks"])

    # 4. SEMANTIC Header Inference (Reading the Answer Key text)
    ma_rules = _extract_marks_from_ma_headers(normalized.get("model_answer_text"))
    for q in questions:
        # SAFEGUARD: skip if already has marks, or if optional/unselected OR group
        if _to_float(q.get("marks"), 0.0) > 0 or q.get("or_group_id") or q.get("question_type") == "optional":
            continue
            
        q_num = int(q.get("number") or 0)
        q_sec = str(q.get("section") or "").strip().lower().replace("_", " ")
        
        for rule in ma_rules:
            match = False
            rule_sec = str(rule.get("section") or "").replace("_", " ")
            
            if rule.get("range"):
                start, end = rule["range"]
                if q_num >= start and q_num <= end:
                    match = True
            elif rule_sec == q_sec:
                match = True
                
            if match:
                q["marks"] = rule["marks"]
                q["mark_source"] = rule["source"]
                logger.info("IAI_RECONCILE: question=%s mark=%s source=ma_header", q_num, q["marks"])
                break

    # 5. REMAINER-BASED Algebraic Inference (Final Gap Filling)
    current_derived = compute_paper_effective_total(questions)
    target_total = _to_float(normalized.get("effective_total_marks"), 0.0)
    
    # 5. REMAINER-BASED Algebraic Inference (Final Gap Filling)
    current_derived = compute_paper_effective_total(questions)
    target_total = _to_float(normalized.get("effective_total_marks"), 0.0)
    
    if target_total > 0 and abs(current_derived - target_total) > 0.01:
        # SAFEGUARD: Do not assign remainder to unselected optional questions or OR-group members
        candidate_qs = [
            q for q in questions 
            if _to_float(q.get("marks"), 0.0) <= 0 
            and not q.get("or_group_id")  # Skip OR groups to prevent over-inflating optional branches
            and q.get("question_type") != "optional"
        ]
        
        if len(candidate_qs) == 1:
            gap = target_total - current_derived
            if gap > 0:
                target_q = candidate_qs[0]
                target_q["marks"] = round(gap, 4)
                target_q["mark_source"] = "reconciled_algebraic"
                logger.info("IAI_RECONCILE: question=%s mark=%s source=algebraic_remainder", target_q.get("number"), gap)
        else:
            # [OPEN QUESTION FIX]: If no 'sink' question remains or multiple candidates exist, flag for Review
            logger.warning("[IAI_RECONCILE_FAILED] Algebraic remainder sink failed. candidates=%s missing_marks=%s", 
                           len(candidate_qs), target_total - current_derived)
            normalized["blueprint_health_review_required"] = True

    # 6. EXTREME DEVIATION GUARD (Sanity Check)
    initial_margin_sum = sum(before_marks.values())
    final_reconciled_sum = compute_paper_effective_total(questions)
    
    # Check for any remaining required questions with 0 marks
    remaining_zeros = [q.get("number") for q in questions if _to_float(q.get("marks"), 0.0) <= 0 and not q.get("or_group_id") and q.get("question_type") != "optional"]
    if remaining_zeros:
        logger.warning("[IAI_RECONCILE_GAP] Required questions still have 0 marks: %s", remaining_zeros)
        normalized["blueprint_health_review_required"] = True

    # If we changed the total by more than 10%, flag for Review.
    if initial_margin_sum > 0 and (abs(final_reconciled_sum - initial_margin_sum) / initial_margin_sum) > 0.10:
        logger.warning("[IAI_EXTREME_DEVIATION] Reconciliation shifted marks by >10%%. initial=%s final=%s", initial_margin_sum, final_reconciled_sum)
        normalized["blueprint_health_review_required"] = True

    # 7. Generate Reconciliation Report (Dry-Run Documentation)
    for q in questions:
        uid = str(q.get("question_uid"))
        after_m = _to_float(q.get("marks"), 0.0)
        if after_m != before_marks.get(uid):
            reconciliation_details.append({
                "uid": uid,
                "number": q.get("number"),
                "before": before_marks.get(uid),
                "after": after_m,
                "source": q.get("mark_source")
            })
    
    normalized["reconciliation_report"] = reconciliation_details
    normalized["questions"] = questions
    normalized["total_marks"] = compute_paper_effective_total(questions)
    normalized["effective_total_marks"] = normalized["total_marks"]
    return normalized

