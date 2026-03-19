"""Grading engine wrapper for AWS pipeline (Gemini)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from app.core.logging_config import logger
from app.services.llm.config import get_llm_api_key
from app.adapters.llm_adapter import GeminiLLMService


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


async def grade_question(*, question_payload: Dict[str, Any], answer_text: str) -> Dict[str, Any]:
    api_key = get_llm_api_key()
    if not api_key:
        return {"score": 0, "feedback": "Missing GEMINI_API_KEY", "confidence": 0.0}

    prompt = f"""Grade the answer strictly. Return JSON only.
Question: {question_payload.get('rubric') or question_payload.get('question_text')}
Max marks: {question_payload.get('max_marks')}
Answer: {answer_text}

Return JSON:
{{"score": 0, "feedback": "", "confidence": 0.0, "page_notes": []}}"""

    llm_service = GeminiLLMService(api_key=api_key)
    
    logger.info("LLM_CALL provider=gemini model=gemini-2.5-flash prompt_len=%s", len(prompt))
    
    response = await llm_service.predict(
        prompt=prompt,
        model_name="gemini-2.5-flash",
        temperature=0,
        response_mime_type="application/json"
    )
    payload = _parse_json(response or "")
    if not payload:
        logger.warning("[AWS][Grade] Failed to parse grading JSON")
        return {"score": 0, "feedback": "Grading parse failed", "confidence": 0.0}
    return payload

