"""Tolerant JSON parsing utilities for LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def parse_tolerant_json(raw_text: str) -> Dict[str, Any]:
    """
    Attempt to extract and parse a single JSON object from potentially messy text.
    Handles Markdown blocks, bracket finding, and direct parsing.
    """
    if not raw_text:
        return {}
    
    text = str(raw_text).strip()

    # 1. Try finding JSON blocks in Markdown
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
        block = match.group(1).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    # 2. Try finding the first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 3. Handle Truncated JSON: Attempt to close open braces/brackets
    start = text.find("{")
    if start != -1:
        candidate = text[start:]
        # Greedy repair: try appending common closing sequences
        # This handles the case where the LLM cuts off mid-list or mid-object
        for suffix in ["}", "]}", "]]}", "}]}", '"}]}', '"}]}']:
            try:
                parsed = json.loads(candidate + suffix)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue

    # 4. Final attempt: direct load
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    return {}


def extract_json_candidates(text: str) -> List[str]:
    """Helper to find multiple potential JSON object strings in a block of text."""
    if not text:
        return []
    
    candidates: List[str] = []
    # Similar to the logic in extraction_service if needed, but for now 
    # we'll stick to the core parser.
    return candidates


__all__ = ["parse_tolerant_json", "extract_json_candidates"]
