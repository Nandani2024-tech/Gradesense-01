"""Prompt templates for AI-structured layer."""

from __future__ import annotations

import json
from typing import Any, Dict, List


PROMPT_VERSION = "ai_structured_v3_multimodal_first"


EXTRACTION_SCHEMA = {
    "questions": [
        {
            "number": 1,
            "section": "string|null",
            "instruction": "string|null",
            "question_text": "string",
            "question_type": "mcq|fill_blank|very_short|short|long|passage|writing|letter|essay",
            "marks": 0,
            "mark_source": "margin|section_math|instruction|inferred",
            "mark_confidence": 0.0,
            "confidence": 0.0,
            "options": ["string"] or None,
            "subquestions": [{"label": "a|b|i|ii", "text": "string", "marks": 0, "mark_source": "margin|section_math|instruction|inferred", "mark_confidence": 0.0, "model_answer": "string", "rubric": "string"}],
            "or_group_id": "string|null",
            "model_answer": "string",
            "rubric": "string",
            "image_evidence": [{"page_index": 0, "bbox": [0, 0, 0, 0], "visual_confidence": 0.0}],
            "ai_confidence": 0.0,
        }
    ],
    "section_math_blocks": [
        {
            "section": "string|null",
            "expression": "12x1=12",
            "question_count": 12,
            "per_question_marks": 1,
            "total_marks": 12,
            "page_index": 0,
            "confidence": 0.0,
        }
    ],
    "total_questions": 0,
    "total_marks": 0,
    "effective_total_marks": 0,
    "numbering_contiguous": True,
}


VISUAL_EXTRACTION_SCHEMA = {
    "questions": [
        {
            "number": 1,
            "page_index": 0,
            "bbox": [0, 0, 0, 0],
            "confidence": 0.0,
        }
    ],
    "subparts": [
        {
            "q": 1,
            "label": "a",
            "page_index": 0,
            "bbox": [0, 0, 0, 0],
            "confidence": 0.0,
        }
    ],
    "margin_marks": [
        {
            "q": 1,
            "sub": "a|null",
            "marks": 0,
            "text": "2+2",
            "split": [2, 2],
            "page_index": 0,
            "bbox": [0, 0, 0, 0],
            "confidence": 0.0,
        }
    ],
    "section_math_rules": [
        {
            "expression": "4 x 3 = 12",
            "count": 4,
            "per": 3,
            "total": 12,
            "start_question": 27,
            "page_index": 0,
            "bbox": [0, 0, 0, 0],
            "confidence": 0.0,
        }
    ],
    "or_pairs": [
        {"q1": 23, "q2": 24, "page_index": 0, "bbox": [0, 0, 0, 0], "confidence": 0.0}
    ],
    "headers": [
        {"kind": "section", "text": "SECTION IV", "page_index": 0, "bbox": [0, 0, 0, 0], "confidence": 0.0}
    ],
}


ALIGNMENT_SCHEMA = {
    "answers": [
        {
            "question_number": 1,
            "sub_part": "a|null",
            "status": "answered|skipped|uncertain",
            "answer_text": "string",
            "detected_type": "mcq|written|blank",
            "page_index": 0,
            "bbox": [0, 0, 0, 0],
            "confidence": 0.0,
        }
    ]
}

QUALITY_SCHEMA = {
    "question_quality": 0.0,
    "question_status": "graded|not_attempted|not_found",
    "question_feedback": "string",
    "concepts_detected": ["string"],
    "concepts_missing": ["string"],
    "concept_coverage": 0.0,
    "confidence": 0.0,
    "sub_qualities": [
        {
            "label": "a",
            "quality": 0.0,
            "status": "graded|not_attempted|not_found",
            "feedback": "Specific feedback for this sub-part.",
            "concepts_detected": ["string"],
            "concepts_missing": ["string"],
            "concept_coverage": 0.0
        }
    ],
}


OBJECTIVE_KEY_SCHEMA = {
    "question_number": 1,
    "key": "A|B|C|D|text",
    "confidence": 0.0,
}


STUDENT_OPTION_SCHEMA = {
    "question_number": 1,
    "selected_option": "A|B|C|D|",
    "confidence": 0.0,
    "reason": "string",
}


EXTRACTION_SYSTEM_PROMPT = """
You are an exam paper structure extraction engine.
Your job is structural parsing, not summarization.

STRICT OUTPUT:
- Return strict JSON only. No Markdown, no code fences.
- Do not include raw newlines inside string values; use \n for line breaks.
- Do not include unescaped quotes inside string values.
- IMPORTANT: Return a VALID JSON object matching the schema below. Do not wrap in markdown blocks if possible, but if you do, ensure it is ```json ... ```. No conversational text.

STRUCTURE RULES:
1) Stage-1 only: do not assign marks. Set all marks and subquestion marks to 0.
2) Do not output or_group_id; the visual layer handles OR pairing.
3) Do not invent question numbers or create new questions.
4) Do not invent subquestions from MCQ options. MCQ options must be in options only.
5) Create subquestions only when explicit labels exist (a,b,c,i,ii) or multiple asks under the same number.
6) Section math (e.g., 12x1=12) is distribution evidence; do not split questions or create subquestions from it.
7) Preserve layout intent; do not merge distinct questions.
8) If the paper shows left-margin section math like n×m=x, it means the next n questions are m marks each. Do not create extra questions; do not assign marks.
9) If the paper says "any one/any of the following/alternative question", keep choices in question_text or options; do not create subquestions.
10) Extract the ideal answer for each question and subquestion into 'model_answer'.
11) Extract marking criteria or guidelines into 'rubric'.
"""


VISUAL_EXTRACTION_SYSTEM_PROMPT = """
You are a visual structure extraction engine for exam question papers.
Your job is to read the page images directly and output ONLY structural evidence.

STRICT OUTPUT:
- Return strict JSON only. No Markdown, no code fences.
- Do not include raw newlines inside string values; use \n for line breaks.
- Do not include unescaped quotes inside string values.

RULES:
1) Do NOT assign final marks or totals for questions. Only output visible margin marks and section math expressions.
2) Do NOT infer or compute missing marks.
3) Do NOT apply rules; return evidence only.
3) Detect question numbers, subpart labels, margin marks, section math expressions (n x m = total), OR connectors, and section headings.
4) Do NOT output question text or answers; output structural evidence only.
5) Include page_index (0-based), bbox [x1,y1,x2,y2] in pixels, and confidence for every item.
6) If section math appears inside a heading (e.g., "SECTION IV 4 x 3 = 12"), still extract the math.
7) If you can see the next question number after a section math expression, set start_question.
8) If a margin mark includes a split like "2+2", include the raw text in "text" and the parts in "split".
"""


def get_extraction_system_prompt() -> str:
    return EXTRACTION_SYSTEM_PROMPT.strip()


def get_visual_extraction_system_prompt() -> str:
    return VISUAL_EXTRACTION_SYSTEM_PROMPT.strip()


def _json_schema_block(schema_obj: Dict[str, Any]) -> str:
    return json.dumps(schema_obj, ensure_ascii=True, indent=2)


def build_extraction_prompt(
    *,
    raw_ocr_text: str,
    batch_index: int,
    total_batches: int,
    extra_rules: List[str] | None = None,
) -> str:
    rules = [
        "You are extracting structure, not summarizing prose.",
        "Question paper images are ground truth.",
        "OCR text is supporting evidence only.",
        "Do not invent question numbers.",
        "Do not assign marks; set all marks and subquestion marks to 0.",
        "Do not assign authoritative final marks; deterministic mark layer resolves marks from visual entities.",
        "Do not output or_group_id; visual layer detects OR connectors.",
        "MCQ options must be in options, never in subquestions.",
        "If the paper says 'any one/any of the following/alternative question', keep choices in question_text or options; do not create subquestions.",
        "Create subquestions only when explicit labels like (a)/(b)/(i)/(ii) are visible or multiple asks appear under the same number.",
        "Do not create subquestions from section math or marks text.",
        "Interpret section math N x M only as distribution evidence; do not split questions or create subquestions from it.",
        "If section math appears in the left margin (n x m = x), it applies to the next n questions; do not assign marks.",
        "Do not include section_math_blocks; visual layer detects section math.",
        "Return effective_total_marks only as 0 in stage-1.",
        "Preserve subparts exactly as written.",
        "Keep question_text concise and parseable JSON-safe text (plain ASCII punctuation preferred).",
        "If a question has long dot/blank leaders or repeated punctuation, collapse them to a short placeholder like '...'.",
        "Do not copy very long filler sequences from OCR (e.g., hundreds of dots/underscores).",
        "Return strict JSON only, no markdown.",
        "Do not include raw newlines inside string values; use \n for line breaks.",
        "Do not include unescaped quotes inside strings; JSON must be valid.",
        "Include image_evidence with page_index and approximate bbox for each question.",
        "Extract ideal answer into 'model_answer'.",
        "Extract marking criteria or guidelines into 'rubric'.",
    ]
    rules.extend(extra_rules or [])

    ocr_chunk = str(raw_ocr_text or "")
    return (
        "You are extracting exam structure for GradeSense.\n"
        f"Batch {batch_index}/{total_batches}.\n"
        "Follow all rules strictly:\n"
        + "\n".join(f"- {r}" for r in rules)
        + "\n\nRequired JSON schema:\n"
        + _json_schema_block(EXTRACTION_SCHEMA)
        + "\n\nOCR Support Text:\n"
        + ocr_chunk
    )


def build_visual_extraction_prompt(
    *,
    batch_index: int,
    total_batches: int,
    page_offset: int,
) -> str:
    rules = [
        "You are extracting visual structure from images only.",
        "Do not use OCR text; do not transcribe long text.",
        "Return strict JSON only.",
        "Only output structural evidence fields; no question text.",
        "Do not assign final marks; only include visible margin marks and section math expressions.",
        "Do not apply rules or compute totals; return evidence only.",
        "Use page_index as absolute index starting at 0.",
        f"This batch starts at page_index={page_offset}.",
    ]
    return (
        "You are extracting visual evidence for GradeSense.\n"
        f"Batch {batch_index}/{total_batches}.\n"
        "Follow all rules strictly:\n"
        + "\n".join(f"- {r}" for r in rules)
        + "\n\nRequired JSON schema:\n"
        + _json_schema_block(VISUAL_EXTRACTION_SCHEMA)
    )


def build_reconstruction_prompt(
    *,
    previous_structure: Dict[str, Any],
    validation_errors: List[str],
    raw_ocr_text: str,
) -> str:
    ocr_chunk = str(raw_ocr_text or "")
    prev_struct_chunk = str(json.dumps(previous_structure, ensure_ascii=True))[:30000]
    return (
        "Reconstruct the same exam structure and fix only validation errors.\n"
        "Hard guardrails:\n"
        "- Do not invent numbering.\n"
        "- Do not merge distinct questions.\n"
        "- This is structural parsing, not summarization.\n"
        "- Stage-1 only: do not assign marks; set all marks to 0.\n"
        "- Never split one question's marks unless explicit visual subparts exist.\n"
        "- Treat N x M as section distribution evidence; do not split questions.\n"
        "- Do not create subquestions from marks math alone.\n"
        "- Do not create subquestions from MCQ options.\n"
        "- If section math appears in the left margin (n x m = x), it applies to the next n questions; do not assign marks.\n"
        "- If the paper says 'any one/any of the following/alternative question', keep choices in question_text or options; do not create subquestions.\n"
        "- Do not output or_group_id; visual layer handles OR pairing.\n"
        "- Do not compute final totals or redistribute marks.\n"
        "- Keep mark hints only when explicitly visible in paper.\n"
        "- Do not include section_math_blocks; visual layer detects section math.\n"
        "- Keep visual evidence for every question.\n"
        "- Keep question_text concise and JSON-safe; collapse long dot leaders/repeated punctuation to '...'.\n"
        "- Do not include raw newlines inside string values; use \n for line breaks.\n"
        "- Do not include unescaped quotes inside strings.\n"
        "Return strict JSON only.\n\n"
        "Current extracted structure:\n"
        f"{prev_struct_chunk}\n\n"
        "Validation errors to fix:\n"
        + "\n".join(f"- {e}" for e in (validation_errors or ["unknown_error"]))
        + "\n\nSchema:\n"
        + _json_schema_block(EXTRACTION_SCHEMA)
        + "\n\nOCR Support Text:\n"
        + ocr_chunk
    )


def build_alignment_prompt(*, question_structure: Dict[str, Any], ocr_text: str = "") -> str:
    prompt = (
        "You are an exam answer extractor and grader.\n"
        "Your task is to identify and match student answers with the correct question numbers and subparts from the question paper.\n"
        "Use answer images as the absolute source of truth.\n"
    )

    if ocr_text:
        prompt += (
            "\n"
            "OCR_TEXT:\n"
            f"{ocr_text}\n"
            "\n"
            "Use OCR text as PRIMARY source. Use images ONLY if OCR is unclear.\n"
        )

    prompt += (
        "\n"
        "IMPORTANT RULES:\n"
        "1. Do NOT assume answers appear in order.\n"
        "2. Students may skip questions or subparts and answer them later in the document.\n"
        "3. Students may also answer skipped questions at the end of the answer sheet or anywhere else.\n"
        "4. Always scan the ENTIRE answer sheet before deciding a question is skipped.\n"
        "5. Match answers ONLY using question numbers or subpart labels written by the student.\n"
        "6. Never shift answers forward or backward because a question is missing.\n"
        "7. If Question 3 is missing but Question 4 appears, keep Question 4 as Question 4.\n"
        "8. If a skipped question appears later in the answer sheet, correctly assign it to that question number.\n"
        "9. Do NOT rely on answer sequence for matching.\n"
        "10. Maintain the original numbering from the question paper at all times.\n"
        "\n"
        "NUMBERING PATTERNS TO DETECT:\n"
        "Question numbers: Q1, Q2 | 1., 2., 3. | Question 1, Question 2\n"
        "Subparts: (i), (ii), (iii) | i., ii., iii. | i), ii), iii) | (a), (b), (c) | a), b), c)\n"
        "\n"
        "MATCHING STRATEGY:\n"
        "Step 1: Scan the entire answer sheet and detect all question numbers and subparts written by the student.\n"
        "Step 2: Map each detected answer to the correct question number and subpart.\n"
        "Step 3: If a question is not found anywhere in the answer sheet, do not hallucinate an answer mapping.\n"
        "Step 4: If a skipped question appears later in the answer sheet, assign it correctly to that question number.\n"
        "Step 5: Never assume unanswered questions mean all later answers belong to earlier questions.\n"
        "\n"
        "EXTRACTION DETAILS:\n"
        "- Transcribe the student's handwritten answer text into 'answer_text'.\n"
        "- For MCQs, also detect the selected option letter (A, B, C, D) if visible.\n"
        "- Provide the page_index and a bounding box [y1, x1, y2, x2] in percentage coordinates (0-100).\n"
        "- If a question has sub-questions in the structure, each sub-part MUST be a separate entry in the 'answers' list.\n"
        "\n"
        "FINAL CHECK BEFORE OUTPUT:\n"
        "- Confirm that the entire answer sheet was scanned.\n"
        "- Confirm that answers written later in the sheet were not missed.\n"
        "- Confirm that skipped questions were not incorrectly assigned other answers.\n"
        "- Do NOT reorder answers based on sequence.\n"
        "\n"
        "Return strict JSON only matching the schema below.\n\n"
        "Question structure (Target):\n"
        f"{(json.dumps(question_structure, ensure_ascii=True)[:50000])}\n\n"
        "Required schema:\n"
        + _json_schema_block(ALIGNMENT_SCHEMA)
    )
    return prompt


def build_quality_prompt(
    *,
    question: Dict[str, Any],
    student_answer_text: str,
    model_answer_text: str,
    grading_contract: Dict[str, Any],
) -> str:
    student_chunk = str(student_answer_text or "")[:15000]
    model_chunk = str(model_answer_text or "")[:15000]
    return (
        "You are an expert grading quality assessor.\n"
        "Your task is to evaluate a student's answer based on conceptual correctness and relevance.\n"
        "You are NOT allowed to assign final marks; return quality signals and evidence instead.\n"
        "Return strict JSON only.\n\n"
        "GRADING PRINCIPLES:\n"
        "- Focus on CONCEPTUAL CORRECTNESS: Accept informal language or non-standard phrasing if the meaning is correct.\n"
        "- Prioritize KEY IDEAS: Award credit for presence of core concepts mentioned in the model answer/rubric.\n"
        "- NO PENALTY for simplified explanations or student-friendly language.\n"
        "- IDENTIFY CONCEPTS: Explicitly list which concepts from the model answer are 'detected' and which are 'missing'.\n"
        "- DO NOT assume missing concepts unless clearly absent after scanning the entire answer.\n"
        "- Every deduction or 'missing' claim MUST be explicitly non-existent in the student answer.\n"
        "- DO NOT require exact textbook definitions.\n\n"
        "Question:\n"
        f"{json.dumps(question, ensure_ascii=True)}\n\n"
        "Grading contract (Signals): \n"
        f"{json.dumps(grading_contract, ensure_ascii=True)}\n\n"
        "Student answer:\n"
        f"{student_chunk}\n\n"
        "Model/reference answer:\n"
        f"{model_chunk}\n\n"
        "Required JSON schema:\n"
        + _json_schema_block(QUALITY_SCHEMA)
    )


def build_objective_key_prompt(*, question: Dict[str, Any], model_answer_text: str) -> str:
    model_chunk = str(model_answer_text or "")[:12000]
    return (
        "Infer objective key for one question.\n"
        "Do not grade, only infer key and confidence.\n"
        "Return strict JSON only.\n\n"
        "If model answer images are provided, use them when text is incomplete.\n\n"
        "Question:\n"
        f"{json.dumps(question, ensure_ascii=True)}\n\n"
        "Model/reference answer:\n"
        f"{model_chunk}\n\n"
        "Schema:\n"
        + _json_schema_block(OBJECTIVE_KEY_SCHEMA)
    )


def build_student_option_prompt(*, question: Dict[str, Any]) -> str:
    return (
        "Read the student's selected option for the given MCQ from the provided images.\n"
        "Look for ticks/circles/letters written by the student.\n"
        "Return empty string if not visible.\n"
        "Return strict JSON only.\n\n"
        "Question:\n"
        f"{json.dumps(question, ensure_ascii=True)}\n\n"
        "Schema:\n"
        + _json_schema_block(STUDENT_OPTION_SCHEMA)
    )
