import re
import json
import uuid
import asyncio
import inspect
import base64
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image

from app.core.logging_config import logger

def _images_to_pdf_bytes(images: List[str]) -> bytes:
    if not images:
        return b""
    pil_images: List[Image.Image] = []
    for img_b64 in images:
        raw = base64.b64decode(img_b64)
        pil = Image.open(BytesIO(raw)).convert("RGB")
        pil_images.append(pil)
    first, rest = pil_images[0], pil_images[1:]
    buf = BytesIO()
    first.save(buf, format="PDF", save_all=True, append_images=rest)
    return buf.getvalue()



def _parse_llm_json(response_text: str) -> Optional[Dict[str, Any]]:
    if not response_text:
        return None
    text = response_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:]
            text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass
    return None

def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None

def _parse_model_answer_json(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    candidates = [raw_text.strip()]
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
        block = (match.group(1) or "").strip()
        if block:
            candidates.append(block)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None

def _normalize_subpart_label(value: Any) -> str:
    cleaned = str(value or "").strip().lower()
    if not cleaned or cleaned in {"none", "null"}:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "", cleaned)
    return cleaned

from .parsing import parse_question_number as _parse_question_number

def _normalize_sub_id(value: Any) -> str:
    """Normalize sub-question id to a stable comparable key."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"^[\(\)\[\]\{\}\s\.\-]+|[\(\)\[\]\{\}\s\.\-]+$", "", text)
    text = re.sub(r"\s+", "", text)
    return text

def _question_number_key(value: Any) -> str:
    n = _parse_question_number(value)
    return str(n) if n is not None else ""

def _pick_better_text(current: str, candidate: str) -> str:
    """Prefer richer text while avoiding placeholder-only replacements."""
    current = (current or "").strip()
    candidate = (candidate or "").strip()
    if not current:
        return candidate
    if not candidate:
        return current

    placeholders = ("answer context not clear", "question")
    current_is_placeholder = any(p in current.lower() for p in placeholders)
    candidate_is_placeholder = any(p in candidate.lower() for p in placeholders)

    if current_is_placeholder and not candidate_is_placeholder:
        return candidate
    if candidate_is_placeholder and not current_is_placeholder:
        return current
    return candidate if len(candidate) > len(current) else current

def _sub_sort_key(sub_id: str):
    """Sort sub-ids like a,b,c,i,ii,iii,1,2 in natural exam order."""
    sid = _normalize_sub_id(sub_id)
    roman_map = {
        "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
        "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10
    }
    if sid in roman_map:
        return (0, roman_map[sid], sid)
    if len(sid) == 1 and sid.isalpha():
        return (1, ord(sid), sid)
    if sid.isdigit():
        return (2, int(sid), sid)
    return (3, 0, sid)

def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        if match:
            try:
                return float(match.group(1))
            except Exception:
                return None
        return None
