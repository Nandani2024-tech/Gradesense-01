import re
import unicodedata

class UIDCollisionError(Exception):
    """Raised when identically numbered questions appear in the same section, causing UID collision."""
    pass

class MissingUIDError(Exception):
    """Raised when question_uid is missing, violating canonical identity."""
    pass

class MissingSectionError(Exception):
    """Raised when question section is undefined, preventing deterministic UID."""
    pass

def normalize_section(section: str) -> str:
    """
    Standardizes section names: lowercase, remove special characters, 
    replace spaces and hyphens with underscores.
    """
    if not section:
        raise MissingSectionError("Section normalization failed: section string is empty or None.")
    
    # Normalize unicode (to handle accented chars if any)
    text = unicodedata.normalize('NFKD', str(section)).encode('ascii', 'ignore').decode('ascii')
    
    # Lowercase
    text = text.lower()
    
    # Replace special characters with space, then collapse spaces to underscores
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '_', text).strip('_')
    
    if not text:
        raise MissingSectionError("Section normalization resulted in empty string.")
        
    return text

def build_question_uid(section: str, number: int) -> str:
    """
    Generates a globally unique identifier for a question within an exam.
    Format: {section_slug}_q{number}
    """
    section_slug = normalize_section(section)
    return f"{section_slug}_q{number}"

def normalize_question_id(qid: str) -> str:
    """Standardizes Question IDs from Vision models (e.g., '1', '22a', 'Q 34')."""
    if not qid:
        return ""
    s_qid = str(qid).strip()
    if "__q" in s_qid:
        return s_qid.lower()
        
    clean = re.sub(r'\s+', '', s_qid).upper()
    if clean and clean[0].isdigit():
        clean = f"Q{clean}"
    clean = re.sub(r'(Q\d+)([A-Z])', r'\1.\2', clean)
    return clean

def is_valid_question_id(qid: str) -> bool:
    """Checks if a question ID matches the canonical format (e.g., Q1, Q1.A)."""
    if not qid:
        return False
    return bool(re.match(r'^Q\d+(\.[A-Za-z0-9_]+)?$', str(qid).upper()))

def build_canonical_question_id(qn_raw: any, sub_raw: any) -> str | None:
    """Translates raw question_number and sub_part into a canonical ID."""
    if not qn_raw:
        return None
    qn_str = str(qn_raw).strip()
    if not qn_str:
        return None
        
    base = normalize_question_id(qn_str)
    
    if sub_raw:
        sub_str = str(sub_raw).strip()
        if sub_str:
            if "." not in base:
                return f"{base}.{sub_str.upper()}"
    return base

from typing import Any, Dict, List

def normalize_question_uid(uid: str) -> str:
    """
    Standardize question UIDs.
    MUTATION DISABLED: Must act as strict pass-through to enforce SSOT constraint.
    """
    if not uid:
        return ""
    
    return str(uid).strip().lower()

def assign_question_uids(questions: List[Dict[str, Any]]) -> None:
    """Enforces single source of truth for UID mapping across pipeline"""
    for q in questions:
        sec = q.get("section")
        if not sec:
            raise MissingSectionError(f"Question {q.get('number')} missing explicit section.")
            
        num = q.get("number")
        if not num: 
            continue
        uid = build_question_uid(sec, num)
        q["question_uid"] = uid
        q["uid"] = uid
