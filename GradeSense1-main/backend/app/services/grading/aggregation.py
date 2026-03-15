from typing import Dict, Any, List

def aggregate_from_sub_marks(contract: Dict[str, Any], sub_mark_map: Dict[str, float]) -> float:
    """Aggregate sub-marks into a total question mark based on contract rules.
    
    Supported Rules:
    - 'sum': Simply sum all sub-marks (capped at total_marks).
    - 'best_of': Take the single highest sub-mark.
    - 'attempt_k_of_n': Sum the top K highest sub-marks.
    - 'binary': All-or-nothing (requires all sub-parts to have >0 marks).
    """
    rule = str(contract.get("aggregation_rule") or "sum").lower()
    total_marks = float(contract.get("total_marks") or 0.0)
    
    if not sub_mark_map:
        return 0.0
        
    ordered_values = sorted(sub_mark_map.items(), key=lambda kv: kv[1], reverse=True)
    
    if rule == "best_of":
        return float(ordered_values[0][1]) if ordered_values else 0.0
        
    if rule == "attempt_k_of_n":
        k = int(contract.get("attempt_k") or 1)
        k = max(1, min(k, len(ordered_values)))
        return float(sum(v for _, v in ordered_values[:k]))
        
    if rule == "binary":
        # Rule: Full marks if all parts are correct/graded, 0 otherwise
        # Here we assume sub_mark_map only contains parts mentioned for this question
        return total_marks if all(v > 0 for _, v in ordered_values) else 0.0
        
    # Default: 'sum'
    total = float(sum(sub_mark_map.values()))
    return min(total, total_marks)
