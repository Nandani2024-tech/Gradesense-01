import re
from typing import Optional, Any

def is_valid_question_id(qid: str) -> bool:
    """
    Checks if a question ID follows the canonical format:
    Q1, Q1.a, Q1.b, Q2, etc. (Uppercase Q, optional dot and lowercase letters)
    """
    if not qid:
        return False
    return bool(re.match(r"^Q\d+(\.[a-z]+)?$", qid))

def normalize_sub_part(sub: Optional[str]) -> Optional[str]:
    """
    Standardizes sub-part labels: 'A', '(a)', 'a' -> 'a'
    Returns None if no valid sub-part is found.
    """
    if not sub:
        return None
    # Extract first alphabetical char
    match = re.search(r"([a-z])", str(sub), re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None

def build_canonical_question_id(question_number: Any, sub_part: Any = None) -> Optional[str]:
    """
    Constructs a canonical question ID from raw components (Task 1 bridge).
    Logic:
      if question_number is None -> None
      else -> Q{number}.{normalizedSub}
    """
    if question_number is None or str(question_number).strip() == "":
        return None
    
    # Extract only digits from question_number
    num_match = re.search(r"(\d+)", str(question_number))
    if not num_match:
        return None
    
    num = num_match.group(1)
    base_id = f"Q{num}"
    
    sub = normalize_sub_part(sub_part)
    if sub:
        return f"{base_id}.{sub}"
    
    return base_id

def normalize_question_id(qid: str) -> str:
    """
    Standardizes a question ID string to the canonical format if possible.
    Rules:
    - Convert to uppercase (prefix)
    - Trim spaces
    - Standardize separators (e.g., 'Q1 . a' -> 'Q1.a')
    - Lowercase sub-question labels
    
    FORBIDDEN:
    - No structural transformations like Q1A -> Q1.a
    """
    if not qid:
        return ""
        
    # 1. Basic trim and uppercase prefix
    s = str(qid).strip()
    
    # 2. Rule: q1 -> Q1, 1 -> Q1
    # Check for plain number or Q + number
    match_simple = re.match(r"(?i)^q?\s*(\d+)$", s)
    if match_simple:
        num = match_simple.group(1)
        return f"Q{num}"
        
    # 3. Rule: Q1 . a -> Q1.a, Q1 A -> Q1.a, Q1.a -> Q1.a
    # Matches Q, then number, then optional separator, then letter(s)
    # Separators: dot, space, dash, underscore
    match_complex = re.match(r"(?i)^q?\s*(\d+)\s*[\.\s\-_]?\s*([a-z]+)$", s)
    if match_complex:
        num = match_complex.group(1)
        sub = match_complex.group(2).lower()
        
        # Check if it was Q1A (no separator and lowercase letter? No, Q1A is mixed)
        # Actually the contract says: Does NOT auto-fix Q1A.
        if re.match(r"(?i)^q?\d+[a-z]+$", s):
             # This matches Q1A, Q1a. We should reject if there's no separator.
             pass
        else:
            return f"Q{num}.{sub}"

    # Return as-is if no rule applies; validation layer will catch if it's still invalid
    return s
