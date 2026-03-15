from typing import Any, Dict, Optional

def _merge_question_meta(
    blueprint: list[Dict[str, Any]],
    meta: Optional[Dict[str, Any]],
) -> None:
    """Update blueprint entries in-place with values from user-provided meta."""
    if not meta:
        return
    for q in blueprint:
        qid = q.get("question_id")
        if qid is None:
            continue
        extra = meta.get(str(qid)) or meta.get(int(qid))
        if isinstance(extra, dict):
            q.update(extra)
