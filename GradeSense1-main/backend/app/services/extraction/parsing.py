"""
Parsing utilities for question extraction.
Contains regex-based helpers for identifying headers, subparts, and question numbers.
"""

import re
import json
from typing import List, Dict, Any, Optional

# Regex patterns
SECTION_RE = re.compile(r"^\s*(?:SECTION|PART|GROUP|UNIT)\s+[A-Z0-9IVX]+\b", re.IGNORECASE)
SUBPART_RE = re.compile(
    r"^\s*(?:[\(\[]\s*([a-z])\s*[\)\]]|([a-z])[\).]|[\(\[]\s*(i{1,4}|v|vi{0,3}|ix|x)\s*[\)\]]|(i{1,4}|v|vi{0,3}|ix|x)[\).])",
    re.IGNORECASE,
)
MARKS_RE = re.compile(r"\(?\b(\d+(?:\.\d+)?)\s*(?:marks?|m)\b\)?", re.IGNORECASE)
QUESTION_PREFIX_RE = re.compile(r"^\s*(?:Q\.?\s*|Question\s*)?(\d{1,3})[\).:\s]", re.IGNORECASE)
ISOLATED_Q_RE = re.compile(r"^\s*[Q]?[0-9]{1,3}\s*[\.:\)]?\s*$", re.IGNORECASE)

def is_section_heading(text: str) -> bool:
    """Returns True if text looks like a section header (e.g., 'SECTION A')."""
    if not text:
        return False
    return bool(SECTION_RE.search(text.strip()))

def is_subpart_pattern(text: str) -> bool:
    """Returns True if text starts with a subpart label like (a) or i)."""
    if not text:
        return False
    return bool(SUBPART_RE.match(text.strip()))

def has_marks_pattern(text: str) -> bool:
    """Returns True if text contains mark indicators like (5 marks)."""
    if not text:
        return False
    return bool(MARKS_RE.search(text))

def is_isolated_question_prefix(text: str) -> bool:
    """Returns True if text is just a question number like 'Q1.' or '2)'."""
    if not text:
        return False
    return bool(ISOLATED_Q_RE.match(text.strip()))

def parse_question_number(text: Any) -> Optional[int]:
    """Extracts integer question number from text."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    
    t = str(text).strip()
    if not t:
        return None
    
    match = re.search(r"(\d+)", t)
    if match:
        try:
            val = int(match.group(1))
            return val if val > 0 else None
        except ValueError:
            pass
    return None

def parse_qnum_from_anchor(text: str) -> Optional[int]:
    """Specialized anchor parser for question numbers."""
    return parse_question_number(text)

def extract_table_bboxes(tables_data: List[dict]) -> List[List[float]]:
    """Extracts bounding boxes from list of table objects."""
    bboxes = []
    for table in tables_data or []:
        box = table.get("box") or table.get("bbox")
        if box and len(box) == 4:
            bboxes.append([float(v) for v in box])
    return bboxes

def line_inside_table(line: dict, table_bboxes: List[List[float]]) -> bool:
    """Returns True if the line's center is inside any table bounding box."""
    if not table_bboxes:
        return False
    
    lx = float(line.get("x", 0.0) or (line.get("x1", 0.0) + line.get("x2", 0.0)) / 2.0)
    ly = float(line.get("y", 0.0) or (line.get("y1", 0.0) + line.get("y2", 0.0)) / 2.0)
    
    for bbox in table_bboxes:
        if len(bbox) == 4:
            if bbox[0] <= lx <= bbox[2] and bbox[1] <= ly <= bbox[3]:
                return True
    return False

def infer_type(text: str) -> str:
    """Infers question type based on keywords."""
    t = (text or "").lower()
    if any(k in t for k in ("journal", "entry", "dr", "cr", "accounting", "ledger", "account")):
        return "accounting"
    if any(k in t for k in ("calculate", "compute", "value", "ratio", "goodwill")):
        return "calculation"
    return "theory"

def expected_components(q_type: str) -> List[str]:
    """Returns typical components expected for a given question type."""
    if q_type == "accounting":
        return ["journal_entries", "ledger_accounts", "final_accounts"]
    if q_type == "calculation":
        return ["formulas", "steps", "final_answer"]
    return ["explanation", "keywords", "examples"]

def infer_subparts_from_text(text: str) -> List[str]:
    """Identifies potential sub-question labels within a block of text."""
    if not text:
        return []
    parts = []
    for m in SUBPART_RE.finditer(text):
        token = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if token:
            parts.append(token.strip().lower())
    return sorted(list(set(parts)))

def regex_recover_question(span: dict, text: str) -> dict:
    """Basic recovery of question structure using span metadata if AI fails."""
    qn = span.get("question_number")
    combined = text or span.get("combined_text") or ""
    return {
        "question_number": qn,
        "question_text": combined.strip(),
        "rubric": "",
        "max_marks": 0.0,
        "sub_questions": []
    }

def normalize_llm_question(span: dict, payload: dict) -> dict:
    """Aligns AI-generated payload with verified span metadata."""
    if not payload:
        return payload
    qn = span.get("question_number")
    if qn is not None:
        payload["question_number"] = qn
    return payload

def parse_question_object_payload(text: str) -> Optional[dict]:
    """Parses JSON question object from raw LLM output."""
    if not text:
        return None
    try:
        # Strategy 1: Direct parse
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return None
