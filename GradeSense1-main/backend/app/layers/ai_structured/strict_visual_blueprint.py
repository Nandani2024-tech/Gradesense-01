"""Strict visual-only blueprint extraction for question papers (college)."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from app.core.logging_config import logger
from app.services.llm.config import get_llm_api_key
from app.services.llm import ImageContent, LlmChat, UserMessage


STRICT_VISUAL_BLUEPRINT_PROMPT_VERSION = "v1"

STRICT_VISUAL_BLUEPRINT_SYSTEM_PROMPT = """
You are an expert academic exam structure analyst.

You are receiving images of a COMPLETE question paper from first page to last page.

You must analyze the entire paper visually before producing output.

You must behave like a deterministic structural parser, not a conversational AI.

STRICT BEHAVIOR RULES:

1. You must analyze ALL pages before producing output.
2. Do NOT guess or invent marks.
3. Do NOT assume structure unless visually supported.
4. If marks are missing and no rule is visible, return null.
5. If a mathematical rule is visible (e.g., "5 x 2 = 10"), apply it strictly.
6. If you apply a rule, mark marks_inferred_from_rule = true.
7. Never hallucinate subparts.
8. If uncertain, lower confidence and use null.
9. All marks must be integers or multiples of 0.5 only.
10. Return JSON only. No explanation. No markdown. No commentary.

WHAT YOU MUST DETECT:

- Question numbers (Q1, 1., 1), etc.)
- Subparts (a), (b), i), ii), etc.
- Marks printed near question (left margin, right margin, inline)
- Section headings
- Section instructions
- OR / internal choice connections
- Implicit marking rules (n x m = total)
- Per-subpart marks
- Paper total marks (if printed)
- Section totals (if printed)

VISUAL PRIORITY RULES:

1. Margin marks override inferred rules.
2. Printed per-question marks override section rules.
3. Section rules apply only if no explicit per-question marks exist.
4. Subpart marks override total inference.
5. If total does not equal sum(subparts), set mark_consistency_warning = true.

PROCESS YOU MUST FOLLOW INTERNALLY:

Step 1: Identify all sections.
Step 2: Identify all question anchors.
Step 3: Detect all explicit marks.
Step 4: Detect implicit mathematical rules.
Step 5: Assign marks conservatively.
Step 6: Validate arithmetic consistency.
Step 7: Detect OR relationships.
Step 8: Validate paper total if present.

If any arithmetic mismatch occurs, flag it.

FINAL OUTPUT MUST MATCH EXACTLY THIS STRUCTURE:

{
  "paper_total_marks": number | null,
  "sections": [
    {
      "section_name": string,
      "section_instruction": string | null,
      "section_total_marks": number | null,
      "section_rule_detected": string | null
    }
  ],
  "questions": [
    {
      "question_number": number,
      "question_label_raw": string,
      "page_index": number,
      "total_marks_of_q": number | null,
      "marks_inferred_from_rule": boolean,
      "has_internal_choice": boolean,
      "choice_group_id": string | null,
      "subparts": [
        {
          "subpart_label": string,
          "marks": number | null
        }
      ],
      "mark_consistency_warning": boolean,
      "confidence": number
    }
  ],
  "implicit_rules_detected": [
    {
      "rule_text": string,
      "interpreted_as": string
    }
  ],
  "global_mark_consistency_warning": boolean
}

ADDITIONAL STRICT REQUIREMENTS:

- question_number must be numeric.
- page_index must match image order (first page = 1).
- confidence must be between 0 and 1.
- If structure unclear, confidence must be below 0.6.
- Do NOT omit questions even if marks are null.
- Output must be valid JSON only.
""".strip()


def _parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_multiple_half(value: float) -> bool:
    return abs(value * 2 - round(value * 2)) < 1e-6


def validate_strict_blueprint(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload_not_dict"]}

    required_top = [
        "paper_total_marks",
        "sections",
        "questions",
        "implicit_rules_detected",
        "global_mark_consistency_warning",
    ]
    for key in required_top:
        if key not in payload:
            errors.append(f"missing_top_key:{key}")

    paper_total = payload.get("paper_total_marks")
    if paper_total is not None:
        if not _is_number(paper_total):
            errors.append("paper_total_marks_not_number")
        elif not _is_multiple_half(float(paper_total)):
            errors.append("paper_total_marks_not_half_multiple")

    if not isinstance(payload.get("sections"), list):
        errors.append("sections_not_list")
    else:
        for idx, section in enumerate(payload.get("sections") or []):
            if not isinstance(section, dict):
                errors.append(f"sections[{idx}]_not_dict")
                continue
            if not isinstance(section.get("section_name"), str):
                errors.append(f"sections[{idx}].section_name_invalid")
            if section.get("section_instruction") is not None and not isinstance(section.get("section_instruction"), str):
                errors.append(f"sections[{idx}].section_instruction_invalid")
            stm = section.get("section_total_marks")
            if stm is not None:
                if not _is_number(stm):
                    errors.append(f"sections[{idx}].section_total_marks_not_number")
                elif not _is_multiple_half(float(stm)):
                    errors.append(f"sections[{idx}].section_total_marks_not_half_multiple")
            if section.get("section_rule_detected") is not None and not isinstance(section.get("section_rule_detected"), str):
                errors.append(f"sections[{idx}].section_rule_detected_invalid")

    questions = payload.get("questions")
    if not isinstance(questions, list):
        errors.append("questions_not_list")
    else:
        for idx, q in enumerate(questions or []):
            if not isinstance(q, dict):
                errors.append(f"questions[{idx}]_not_dict")
                continue
            qn = q.get("question_number")
            if not _is_number(qn):
                errors.append(f"questions[{idx}].question_number_invalid")
            if not isinstance(q.get("question_label_raw"), str):
                errors.append(f"questions[{idx}].question_label_raw_invalid")
            page_index = q.get("page_index")
            if not _is_number(page_index):
                errors.append(f"questions[{idx}].page_index_invalid")
            total_marks = q.get("total_marks_of_q")
            if total_marks is not None:
                if not _is_number(total_marks):
                    errors.append(f"questions[{idx}].total_marks_of_q_not_number")
                elif not _is_multiple_half(float(total_marks)):
                    errors.append(f"questions[{idx}].total_marks_of_q_not_half_multiple")
            if not _is_bool(q.get("marks_inferred_from_rule")):
                errors.append(f"questions[{idx}].marks_inferred_from_rule_invalid")
            if not _is_bool(q.get("has_internal_choice")):
                errors.append(f"questions[{idx}].has_internal_choice_invalid")
            if q.get("choice_group_id") is not None and not isinstance(q.get("choice_group_id"), str):
                errors.append(f"questions[{idx}].choice_group_id_invalid")
            if not _is_bool(q.get("mark_consistency_warning")):
                errors.append(f"questions[{idx}].mark_consistency_warning_invalid")
            conf = q.get("confidence")
            if not _is_number(conf):
                errors.append(f"questions[{idx}].confidence_invalid")
            else:
                c = float(conf)
                if c < 0 or c > 1:
                    errors.append(f"questions[{idx}].confidence_out_of_range")

            subparts = q.get("subparts")
            if not isinstance(subparts, list):
                errors.append(f"questions[{idx}].subparts_not_list")
            else:
                for sidx, sp in enumerate(subparts or []):
                    if not isinstance(sp, dict):
                        errors.append(f"questions[{idx}].subparts[{sidx}]_not_dict")
                        continue
                    if not isinstance(sp.get("subpart_label"), str):
                        errors.append(f"questions[{idx}].subparts[{sidx}].subpart_label_invalid")
                    sm = sp.get("marks")
                    if sm is not None:
                        if not _is_number(sm):
                            errors.append(f"questions[{idx}].subparts[{sidx}].marks_not_number")
                        elif not _is_multiple_half(float(sm)):
                            errors.append(f"questions[{idx}].subparts[{sidx}].marks_not_half_multiple")

    if not isinstance(payload.get("implicit_rules_detected"), list):
        errors.append("implicit_rules_detected_not_list")
    else:
        for idx, rule in enumerate(payload.get("implicit_rules_detected") or []):
            if not isinstance(rule, dict):
                errors.append(f"implicit_rules_detected[{idx}]_not_dict")
                continue
            if not isinstance(rule.get("rule_text"), str):
                errors.append(f"implicit_rules_detected[{idx}].rule_text_invalid")
            if not isinstance(rule.get("interpreted_as"), str):
                errors.append(f"implicit_rules_detected[{idx}].interpreted_as_invalid")

    if not _is_bool(payload.get("global_mark_consistency_warning")):
        errors.append("global_mark_consistency_warning_invalid")

    return {"valid": len(errors) == 0, "errors": errors}


def _compare_payloads(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> List[str]:
    diffs: List[str] = []
    if not isinstance(a, dict) or not isinstance(b, dict):
        return ["payload_missing_or_invalid"]

    if a.get("paper_total_marks") != b.get("paper_total_marks"):
        diffs.append("paper_total_marks_mismatch")

    qa = a.get("questions") or []
    qb = b.get("questions") or []
    if len(qa) != len(qb):
        diffs.append("question_count_mismatch")
    else:
        nums_a = [q.get("question_number") for q in qa if isinstance(q, dict)]
        nums_b = [q.get("question_number") for q in qb if isinstance(q, dict)]
        if nums_a != nums_b:
            diffs.append("question_numbers_mismatch")

    if a.get("global_mark_consistency_warning") != b.get("global_mark_consistency_warning"):
        diffs.append("global_mark_consistency_warning_mismatch")

    return diffs


async def run_strict_visual_blueprint(
    images: List[str],
    *,
    model_name: str = "qwen2.5:latest",
) -> Dict[str, Any]:
    api_key = get_llm_api_key()
    if not api_key:
        return {"payload": None, "valid": False, "errors": ["missing_gemini_api_key"]}
    if not images:
        return {"payload": None, "valid": False, "errors": ["no_images"]}

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    actual_model = model_name
    if provider == "ollama":
        # Strict visual blueprint MUST use a vision-capable model.
        actual_model = "llama3.2-vision:latest"

    chat = (
        LlmChat(
            api_key=api_key or "no-key",
            session_id=f"strict_visual_{uuid.uuid4().hex[:10]}",
            system_message=STRICT_VISUAL_BLUEPRINT_SYSTEM_PROMPT,
        )
        .with_model(provider, actual_model)
        .with_params(temperature=0.1, response_mime_type="application/json", max_output_tokens=8192)
    )

    message = UserMessage(
        text="",
        file_contents=[ImageContent(image_base64=img) for img in images],
    )
    raw = await chat.send_message(message)
    payload = _parse_json_object(raw or "")
    if not payload:
        logger.warning("STRICT_VISUAL_BLUEPRINT_PARSE_FAILED")
        return {"payload": None, "valid": False, "errors": ["invalid_json"]}

    validation = validate_strict_blueprint(payload)
    return {"payload": payload, "valid": validation["valid"], "errors": validation["errors"]}


async def run_strict_visual_blueprint_double_pass(
    images: List[str],
    *,
    model_name: str = "qwen2.5:latest",
) -> Dict[str, Any]:
    pass_a = await run_strict_visual_blueprint(images, model_name=model_name)
    pass_b = await run_strict_visual_blueprint(images, model_name=model_name)

    diffs = _compare_payloads(pass_a.get("payload"), pass_b.get("payload"))
    double_pass_match = len(diffs) == 0

    selected = pass_a if pass_a.get("valid") else pass_b

    return {
        "pass_a": pass_a,
        "pass_b": pass_b,
        "double_pass_match": double_pass_match,
        "double_pass_diffs": diffs,
        "selected_payload": selected.get("payload"),
        "selected_valid": bool(selected.get("valid")),
        "selected_errors": selected.get("errors") or [],
    }

