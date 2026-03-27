import re
import unicodedata

class UIDCollisionError(Exception):
    """Raised when identically numbered questions appear in the same section, causing UID collision."""
    pass

def normalize_section(section: str) -> str:
    """
    Standardizes section names: lowercase, remove special characters, 
    replace spaces and hyphens with underscores.
    """
    if not section:
        return "default"
    
    # Normalize unicode (to handle accented chars if any)
    text = unicodedata.normalize('NFKD', str(section)).encode('ascii', 'ignore').decode('ascii')
    
    # Lowercase
    text = text.lower()
    
    # Replace special characters with space, then collapse spaces to underscores
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '_', text).strip('_')
    
    return text or "default"

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
