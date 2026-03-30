import re
import unicodedata
from app.utils.text_utils import normalize_text_unicode_safe

class UIDCollisionError(Exception):
    """Raised when identically numbered questions appear in the same section, causing UID collision."""
    pass

class MissingUIDError(Exception):
    """Raised when question_uid is missing, violating canonical identity."""
    pass

class MissingSectionError(Exception):
    """Raised when question section is undefined, preventing deterministic UID."""
    pass

class DuplicateAnchorError(Exception):
    """Raised when multiple unresolvable visual anchors exist for the same UID."""
    pass

class AmbiguousMergeError(Exception):
    """Raised when visual blocks belong to the same question but have conflicting attributes (e.g. different sections)."""
    pass

def normalize_section(section: str) -> str:
    """
    Standardizes section names while preserving multilingual characters.
    Replaces spaces and hyphens with underscores, keeps it lowercased (where applicable).
    """
    if not section:
        return "default"
    
    # 1. Unicode-safe normalization
    text = normalize_text_unicode_safe(section)
    
    # 2. Lowercase (carefully, some languages don't have case)
    text = text.lower()
    
    # 3. Replace whitespaces, hyphens, colons and commas with underscores
    # We preserve everything else (including matras/vowel marks) to meet the "must preserve" requirement.
    text = re.sub(r'[\s:,-]+', '_', text)
    text = text.strip('_')
    
    # 4. Strict check: fallback if everything was stripped (zombie preventer)
    if not text:
        return "section_unk"
        
    return text

def canonicalize_uid(section: str, number: int, subpart: str = None, paper_id: str = None) -> str:
    """
    Consolidated UID generation (Phase 1).
    Format: [paper_id_]{section_slug}_q{number}[_s{subpart_slug}]
    """
    sec_slug = normalize_section(section)
    
    # Ensure number is a valid positive integer
    if number is None:
        num_part = "unk"
    else:
        try:
            # We keep it as a string if it's not a pure int to support "1", "1.1" etc if needed
            # but usually number is an int here.
            num_part = f"q{int(number)}"
        except:
            num_part = f"q{str(number).strip()}"
            
    prefix = f"{paper_id}_" if paper_id else ""
    base_uid = f"{prefix}{sec_slug}_{num_part}"
    
    if subpart:
        # Improved subpart slug: keep it alphabetic/numeric or keep it as-is if multilingual
        sub_slug = normalize_text_unicode_safe(str(subpart).lower())
        sub_slug = re.sub(r'[\s:,-]+', '_', sub_slug).strip('_')
        # Remove brackets like (a) -> a
        sub_slug = re.sub(r'[\(\)\[\]\{\}\.]', '', sub_slug)
        if sub_slug:
            return f"{base_uid}_s{sub_slug}"
            
    return base_uid

def build_question_uid(section: str, number: int, paper_id: str = None) -> str:
    """
    Legacy wrapper for backward compatibility with audit hooks.
    Uses canonicalize_uid internally.
    """
    return canonicalize_uid(section, number, paper_id=paper_id)

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

def assign_question_uids(questions: List[Dict[str, Any]], paper_id: str = None) -> None:
    """
    Enforces single source of truth for UID mapping across pipeline.
    Implements strict collision detection for the current batch.
    """
    seen_uids = set()
    for q in questions:
        sec = q.get("section") or "default"
        num = q.get("number")
        
        if num is None:
            continue
            
        uid = canonicalize_uid(sec, num, paper_id=paper_id)
        
        if uid in seen_uids:
            raise UIDCollisionError(f"Collision detected for UID: {uid}. Section: {sec}, Number: {num}")
        
        seen_uids.add(uid)
        q["question_uid"] = uid
        q["uid"] = uid
        
        # Handle subquestions recursively
        _recursive_assign_uids(q.get("subquestions") or [], sec, num, seen_uids, paper_id=paper_id)

def _recursive_assign_uids(subquestions: List[Dict[str, Any]], section: str, parent_number: int, seen_uids: set, parent_subpart: str = None, paper_id: str = None) -> None:
    for sq in subquestions:
        label = sq.get("label") or "sub"
        # Deep recursion: parent_subpart prefix ensures uniqueness for nested items (e.g. q1_sa_si)
        current_subpart = f"{parent_subpart}_{label}" if parent_subpart else label
        uid = canonicalize_uid(section, parent_number, subpart=current_subpart, paper_id=paper_id)
        
        if uid in seen_uids:
            raise UIDCollisionError(f"Collision detected for subpart UID: {uid}")
            
        seen_uids.add(uid)
        sq["question_uid"] = uid
        sq["uid"] = uid
        
        nested = sq.get("subquestions") or []
        if nested:
            _recursive_assign_uids(nested, section, parent_number, seen_uids, parent_subpart=current_subpart, paper_id=paper_id)
            _recursive_assign_uids(nested, section, parent_number, seen_uids, parent_subpart=current_subpart, paper_id=paper_id)
