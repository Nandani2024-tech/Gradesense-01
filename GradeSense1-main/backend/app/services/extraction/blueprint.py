import re
from typing import List, Dict, Any, Optional
from app.core.logging_config import logger
from .parsing import infer_type, expected_components, parse_question_number, MARKS_RE, SUBPART_RE

# Try matching imports from pipeline for consistency
try:
    import fitz
except ImportError:
    fitz = None

def build_question_blueprint_from_exam_questions(exam_questions: List[dict]) -> List[dict]:
    """
    Takes raw questions (maybe from a question_paper collection) and adds 
    grading blueprint fields (type, expected components).
    """
    blueprint_questions = []
    for q in exam_questions:
        q_text = str(q.get("text", "") or q.get("question_text", "") or "")
        q_type = infer_type(q_text)
        q_num = q.get("question_number") or q.get("id")
        qn = parse_question_number(q_num)
        blueprint_questions.append({
            "question_id": qn,
            "question_number": qn,
            "question_text": q_text,
            "max_marks": float(q.get("max_marks", 0.0) or q.get("marks", 0.0)),
            "type": q_type,
            "expected_components": expected_components(q_type),
            "sub_questions": q.get("sub_questions", [])
        })
    return blueprint_questions

def build_question_blueprint_from_pdf(pdf_bytes: bytes) -> List[dict]:
    """Extract coarse question blueprint directly from question paper PDF text."""
    blueprint: List[dict] = []
    if fitz is None:
        logger.warning("Question blueprint extraction skipped because PyMuPDF is not installed")
        return blueprint
    
    from .parsing import has_marks_pattern, MARKS_RE
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_blocks = []
        for page in doc:
            text_blocks.append(page.get_text("text") or "")
        doc.close()
        joined = "\n".join(text_blocks)
    except Exception as e:
        logger.warning("Question blueprint PDF parse failed: %s", e)
        return blueprint

    # Regex split to find question anchors (e.g., Q1, 1.)
    chunks = re.split(r"\n\s*(?:Q\.?\s*)?(\d{1,3})[\).:\s]", joined)
    if len(chunks) < 3:
        return blueprint

    for idx in range(1, len(chunks), 2):
        qn_raw = chunks[idx]
        body = chunks[idx + 1] if idx + 1 < len(chunks) else ""
        qn = parse_question_number(qn_raw)
        if qn is None:
            continue
            
        marks = 0.0
        marks_match = MARKS_RE.search(body)
        if marks_match:
            try:
                marks = float(marks_match.group(1))
            except:
                marks = 0.0
                
        q_type = infer_type(body)
        
        # Simple subpart detection for blueprinting
        parts = []
        from .parsing import SUBPART_RE
        for sm in SUBPART_RE.finditer(body):
            token = sm.group(1) or sm.group(2) or sm.group(3) or sm.group(4)
            if token:
                parts.append({
                    "part_id": token.strip().lower(),
                    "marks": 0.0,
                    "rubric": ""
                })
        
        blueprint.append({
            "question_id": qn,
            "question_number": qn,
            "parts": parts,
            "marks": marks,
            "max_marks": marks,
            "type": q_type,
            "expected_components": expected_components(q_type),
            "rubric": body[:1200].strip(),
            "question_text": f"Question {qn}",
        })
        
    return sorted(blueprint, key=lambda x: int(x.get("question_id", 0)))
