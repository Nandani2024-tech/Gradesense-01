import asyncio
import ast
import collections
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Set

from app.core.logging_config import logger
from app.core.exceptions import CustomServiceException
from app.infrastructure.serialization.safe_numeric import safe_float, safe_int, parse_section_math_expression
from app.layers.ai_structured.validation import normalize_structure_payload
from app.services.pipelines.steps import llm_step
from app.adapters.interfaces import AbstractLLMService
from app.prompts.ai_structured_prompts import (
    build_extraction_prompt,
    build_visual_extraction_prompt,
)

_ALLOWED_TYPES = {
    "mcq",
    "fill_blank",
    "very_short",
    "short",
    "long",
    "passage",
    "writing",
    "letter",
    "essay",
    "short_answer",
    "descriptive",
    "descriptive_choice",
    "passage_subparts",
    "or_group",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    return safe_float(value, default)


def _to_int(value: Any, default: int = 0) -> int:
    return safe_int(value, default)


def as_payload_dict(parsed: Any) -> Optional[Dict[str, Any]]:
    if isinstance(parsed, dict):
        if any(
            key in parsed
            for key in ("questions", "section_math_blocks", "total_questions", "total_marks", "effective_total_marks")
        ):
            return parsed
        return None
    if isinstance(parsed, list):
        rows = [row for row in parsed if isinstance(row, dict)]
        if rows and len(rows) == len(parsed):
            return {"questions": rows}
        return None
    return None


def extract_balanced_json_candidates(text: str, *, max_candidates: int = 16) -> List[str]:
    candidates: List[str] = []
    if not text:
        return candidates

    stack: List[str] = []
    start_idx: Optional[int] = None
    in_string = False
    escape = False

    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "{[":
            if not stack:
                start_idx = idx
            stack.append(ch)
            continue

        if ch in "}]":
            if not stack:
                continue
            opener = stack[-1]
            if (opener == "{" and ch == "}") or (opener == "[" and ch == "]"):
                stack.pop()
                if not stack and start_idx is not None:
                    snippet = text[start_idx:idx + 1].strip()
                    if snippet:
                        candidates.append(snippet)
                        if len(candidates) >= max_candidates:
                            break
                    start_idx = None
            else:
                stack.clear()
                start_idx = None

    return candidates


def sanitize_json_candidate(text: str) -> str:
    out = (text or "").strip().lstrip("\ufeff")
    out = re.sub(r"^\s*```(?:json)?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*```\s*$", "", out)
    out = re.sub(r"^\s*json\s*[:\n]", "", out, flags=re.IGNORECASE)
    out = out.strip().rstrip(";")
    out = out.replace("“", '"').replace("”", '"')
    out = out.replace("’", "'").replace("‘", "'")
    out = re.sub(r",(\s*[}\]])", r"\1", out)
    return out.strip()


def repair_json_string_content(text: str) -> str:
    if not text:
        return text

    out: List[str] = []
    in_string = False
    i = 0
    n = len(text)
    valid_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    while i < n:
        ch = text[i]

        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if ch == '"':
            out.append(ch)
            in_string = False
            i += 1
            continue

        if ch == "\\":
            if i + 1 >= n:
                out.append("\\\\")
                i += 1
                continue
            nxt = text[i + 1]
            if nxt in valid_escapes:
                out.append("\\")
                out.append(nxt)
                i += 2
                continue
            out.append("\\\\")
            i += 1
            continue

        if ch == "\n":
            out.append("\\n")
            i += 1
            continue
        if ch == "\r":
            out.append("\\r")
            i += 1
            continue
        if ch == "\t":
            out.append("\\t")
            i += 1
            continue
        if ord(ch) < 32:
            out.append(f"\\u{ord(ch):04x}")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_any_json_value(candidate: str) -> Any:
    if not candidate:
        return None

    probes: List[str] = []
    base = candidate.strip()
    probes.append(base)
    sanitized = sanitize_json_candidate(base)
    if sanitized and sanitized != base:
        probes.append(sanitized)
    repaired = repair_json_string_content(sanitized or base)
    if repaired and repaired not in probes:
        probes.append(repaired)

    decoder = json.JSONDecoder()
    seen: set[str] = set()
    for probe in probes:
        if not probe or probe in seen:
            continue
        seen.add(probe)
        try:
            return json.loads(probe)
        except Exception:
            pass
        try:
            parsed, _end = decoder.raw_decode(probe.lstrip())
            return parsed
        except Exception:
            pass
        try:
            return ast.literal_eval(probe)
        except Exception:
            pass
    return None


def looks_like_question_dict(obj: Dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return False
    qn = _to_int(obj.get("number"), 0)
    if qn <= 0:
        return False
    return bool(
        str(obj.get("question_text") or "").strip()
        or str(obj.get("instruction") or "").strip()
        or str(obj.get("question_type") or "").strip()
    )


def looks_like_section_math_block(obj: Dict[str, Any]) -> bool:
    if not isinstance(obj, dict):
        return False
    expr = str(obj.get("expression") or "").strip()
    if expr:
        parsed = parse_section_math_expression(expr)
        if parsed:
            return True
    count = _to_int(obj.get("question_count"), 0)
    if count <= 0:
        count = _to_int(obj.get("count"), 0)
    per = _to_float(obj.get("per_question_marks"), 0.0)
    if per <= 0:
        per = _to_float(obj.get("per"), 0.0)
    total = _to_float(obj.get("total_marks"), 0.0)
    if total <= 0:
        total = _to_float(obj.get("total"), 0.0)
    return count > 0 and per > 0 and total > 0


def normalize_visual_payload(payload: Dict[str, Any], page_offset: int, page_count: int) -> Dict[str, Any]:
    def _norm_page(value: Any) -> int:
        raw = _to_int(value, -1)
        if raw < 0:
            return page_offset
        if page_offset > 0 and raw < page_offset and 0 <= raw < max(1, page_count):
            return raw + page_offset
        return raw

    out = {
        "questions": [],
        "subparts": [],
        "margin_marks": [],
        "section_math": [],
        "or_connectors": [],
        "headers": [],
        "header_total": None,
    }
    if not isinstance(payload, dict):
        return out

    for row in payload.get("questions") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("number"), 0)
        if qn <= 0:
            continue
        out["questions"].append(
            {
                "number": qn,
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    for row in payload.get("subparts") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("q"), 0)
        label = str(row.get("label") or "").strip()
        if qn <= 0 or not label:
            continue
        out["subparts"].append(
            {
                "q": qn,
                "label": label,
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    for row in payload.get("margin_marks") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("q"), 0)
        if qn <= 0:
            continue
        out["margin_marks"].append(
            {
                "q": qn,
                "sub": row.get("sub"),
                "marks": round(float(_to_float(row.get("marks"), 0.0)), 4),
                "text": row.get("text") or row.get("raw"),
                "split": row.get("split"),
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    for row in payload.get("section_math_rules") or []:
        if not isinstance(row, dict):
            continue
        count = _to_int(row.get("count"), 0)
        per = _to_float(row.get("per"), 0.0)
        total = _to_float(row.get("total"), 0.0)
        if count <= 0 or per <= 0 or total <= 0:
            continue
        out["section_math"].append(
            {
                "count": count,
                "per": round(float(per), 4),
                "total": round(float(total), 4),
                "range": {
                    "start": _to_int(row.get("start_question"), 0),
                    "end": _to_int(row.get("start_question"), 0) + count - 1,
                },
                "expr": str(row.get("expression") or f"{count} x {round(float(per), 4)} = {round(float(total), 4)}"),
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    for row in payload.get("or_pairs") or []:
        if not isinstance(row, dict):
            continue
        q1 = _to_int(row.get("q1"), 0)
        q2 = _to_int(row.get("q2"), 0)
        if q1 <= 0 or q2 <= 0:
            continue
        out["or_connectors"].append(
            {
                "q1": q1,
                "q2": q2,
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    for row in payload.get("headers") or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        out["headers"].append(
            {
                "kind": str(row.get("kind") or "section"),
                "text": text,
                "bbox": list(row.get("bbox") or [0, 0, 0, 0]),
                "page": _norm_page(row.get("page_index")),
                "confidence": round(float(_to_float(row.get("confidence"), 0.0)), 4),
            }
        )

    if "header_total" in payload and isinstance(payload.get("header_total"), dict):
        out["header_total"] = payload.get("header_total")

    return out


def merge_questions(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    if len(str(incoming.get("question_text") or "")) > len(str(merged.get("question_text") or "")):
        merged["question_text"] = incoming.get("question_text")

    if incoming.get("instruction") and not merged.get("instruction"):
        merged["instruction"] = incoming.get("instruction")
    if incoming.get("section") and not merged.get("section"):
        merged["section"] = incoming.get("section")
    if incoming.get("question_type") and merged.get("question_type") == "descriptive":
        merged["question_type"] = incoming.get("question_type")

    in_marks = _to_float(incoming.get("marks"), 0.0)
    ex_marks = _to_float(merged.get("marks"), 0.0)
    in_conf = _to_float(incoming.get("ai_confidence"), 0.0)
    ex_conf = _to_float(merged.get("ai_confidence"), 0.0)
    if (in_marks > 0 and ex_marks <= 0) or (in_conf > ex_conf and in_marks > 0) or (in_marks > ex_marks):
        merged["marks"] = in_marks
        merged["mark_source"] = str(incoming.get("mark_source") or merged.get("mark_source") or "inferred").strip().lower()
        merged["mark_confidence"] = _to_float(incoming.get("mark_confidence"), _to_float(merged.get("mark_confidence"), 0.0))

    existing_evidence = list(merged.get("image_evidence") or [])
    seen = {
        (
            int(ev.get("page_index", -1)),
            tuple(ev.get("bbox") or []),
        )
        for ev in existing_evidence
        if isinstance(ev, dict)
    }
    for ev in (incoming.get("image_evidence") or []):
        if not isinstance(ev, dict):
            continue
        key = (int(ev.get("page_index", -1)), tuple(ev.get("bbox") or []))
        if key in seen:
            continue
        seen.add(key)
        existing_evidence.append(ev)
    merged["image_evidence"] = existing_evidence

    sub_by_label = {str(sq.get("label")): dict(sq) for sq in (merged.get("subquestions") or [])}
    for sq in (incoming.get("subquestions") or []):
        label = str(sq.get("label") or "").strip()
        if not label:
            continue
        if label not in sub_by_label:
            sub_by_label[label] = dict(sq)
            continue
        ex_sq = sub_by_label[label]
        if len(str(sq.get("text") or "")) > len(str(ex_sq.get("text") or "")):
            ex_sq["text"] = sq.get("text")
        if _to_float(sq.get("marks"), 0.0) > _to_float(ex_sq.get("marks"), 0.0):
            ex_sq["marks"] = _to_float(sq.get("marks"), 0.0)
        ex_ev = list(ex_sq.get("image_evidence") or [])
        ex_sq["image_evidence"] = ex_ev + [
            ev for ev in (sq.get("image_evidence") or []) if ev not in ex_ev
        ]
        ex_sq["confidence"] = max(
            _to_float(ex_sq.get("confidence"), 0.0),
            _to_float(sq.get("confidence"), 0.0),
        )
        sub_by_label[label] = ex_sq
    merged["subquestions"] = sorted(sub_by_label.values(), key=lambda s: str(s.get("label") or ""))

    merged["ai_confidence"] = max(ex_conf, in_conf)
    merged["confidence"] = max(
        _to_float(merged.get("confidence"), ex_conf),
        _to_float(incoming.get("confidence"), in_conf),
    )
    return merged


def build_or_groups_from_visual(visual_entities: Dict[str, Any]) -> Dict[int, str]:
    edges: List[Tuple[int, int]] = []
    for row in (visual_entities or {}).get("or_connectors") or []:
        if not isinstance(row, dict):
            continue
        q1 = _to_int(row.get("q1"), 0)
        q2 = _to_int(row.get("q2"), 0)
        if q1 > 0 and q2 > 0 and q1 != q2:
            edges.append((min(q1, q2), max(q1, q2)))
    if not edges:
        return {}

    parent: Dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        pa = find(a)
        pb = find(b)
        if pa != pb:
            parent[pb] = pa

    for a, b in edges:
        union(a, b)

    comps: Dict[int, List[int]] = collections.defaultdict(list)
    for node in list(parent.keys()):
        comps[find(node)].append(node)

    out: Dict[int, str] = {}
    gid_seq = 1
    for _, members in sorted(comps.items(), key=lambda kv: min(kv[1])):
        uniq = sorted(set(int(m) for m in members if int(m) > 0))
        if len(uniq) < 2:
            continue
        gid = f"visual_or_{gid_seq}"
        gid_seq += 1
        for qn in uniq:
            out[qn] = gid
    return out


def semantic_structure_from_visual_entities(visual_entities: Dict[str, Any]) -> Dict[str, Any]:
    questions: List[Dict[str, Any]] = []
    sub_by_q: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
    for row in (visual_entities or {}).get("subparts") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("q"), 0)
        label = str(row.get("label") or "").strip()
        if qn <= 0 or not label:
            continue
        sub_by_q[qn].append(
            {
                "label": label,
                "text": "",
                "marks": 0.0,
                "mark_source": "inferred",
                "mark_confidence": 0.0,
                "confidence": _to_float(row.get("confidence"), 0.0),
                "image_evidence": [
                    {
                        "page_index": _to_int(row.get("page"), 0),
                        "bbox": row.get("bbox"),
                        "visual_confidence": _to_float(row.get("confidence"), 0.0),
                    }
                ],
            }
        )

    for row in sorted((visual_entities or {}).get("questions") or [], key=lambda r: _to_int((r or {}).get("number"), 0)):
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("number"), 0)
        if qn <= 0:
            continue
        questions.append(
            {
                "number": qn,
                "section": None,
                "instruction": None,
                "question_text": "",
                "question_type": "descriptive",
                "marks": 0.0,
                "mark_source": "inferred",
                "mark_confidence": 0.0,
                "options": None,
                "subquestions": sorted(sub_by_q.get(qn) or [], key=lambda sq: str(sq.get("label") or "")),
                "or_group_id": None,
                "image_evidence": [
                    {
                        "page_index": _to_int(row.get("page"), 0),
                        "bbox": row.get("bbox"),
                        "visual_confidence": _to_float(row.get("confidence"), 0.0),
                    }
                ],
                "ai_confidence": _to_float(row.get("confidence"), 0.0),
                "confidence": _to_float(row.get("confidence"), 0.0),
            }
        )

    return normalize_structure_payload(
        {
            "questions": questions,
            "section_math_blocks": [],
            "total_questions": len(questions),
            "total_marks": 0.0,
            "effective_total_marks": 0.0,
            "numbering_contiguous": False,
        }
    )


def merge_semantic_with_visual_entities(stage2_structure: Dict[str, Any], visual_entities: Dict[str, Any]) -> Dict[str, Any]:
    def _demote_choice_subparts(question: Dict[str, Any]) -> bool:
        subparts = list(question.get("subquestions") or [])
        if not subparts:
            return False
        qtype = str((question or {}).get("question_type") or "").strip().lower()
        if qtype in {"passage", "passage_subparts"}:
            return False

        for sq in subparts:
            if _to_float(sq.get("marks"), 0.0) > 0 and str(sq.get("mark_source") or "").strip().lower() in {
                "margin",
                "section_math",
                "instruction",
            }:
                return False

        raw_text = f"{question.get('instruction') or ''}\n{question.get('question_text') or ''}"
        text = raw_text.lower()
        choice_phrases = [
            "any one",
            "any of the following",
            "attempt any one",
            "choose any one",
            "either of the following",
            "alternative question",
            "in lieu of",
        ]
        has_choice_signal = any(phrase in text for phrase in choice_phrases)
        if not has_choice_signal and re.search(r"(^|\n)\s*or\s*(\n|$)", raw_text, flags=re.IGNORECASE):
            has_choice_signal = True
        if qtype == "mcq":
            has_choice_signal = True

        if not has_choice_signal:
            return False

        options = list(question.get("options") or [])
        for sq in subparts:
            opt = str(sq.get("text") or "").strip()
            if opt and opt not in options:
                options.append(opt)
        if options:
            question["options"] = options
        question["subquestions"] = []
        return True

    def _allows_visual_subparts(question: Dict[str, Any]) -> bool:
        qtype = str((question or {}).get("question_type") or "").strip().lower()
        if qtype in {"mcq", "fill_blank", "very_short", "writing", "letter", "essay"}:
            return False
        options = (question or {}).get("options")
        if isinstance(options, list) and len(options) >= 2:
            return False
        return qtype in {"short", "long", "passage", "passage_subparts", "descriptive_choice", "or_group"}

    normalized = normalize_structure_payload(stage2_structure or {})
    q_by_num: Dict[int, Dict[str, Any]] = {
        _to_int(q.get("number"), 0): dict(q)
        for q in (normalized.get("questions") or [])
        if _to_int(q.get("number"), 0) > 0
    }
    visual_subparts_exist = bool((visual_entities or {}).get("subparts") or [])
    visual_labels_by_q: Dict[int, Set[str]] = collections.defaultdict(set)
    for row in (visual_entities or {}).get("subparts") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("q"), 0)
        label = str(row.get("label") or "").strip()
        if qn <= 0 or not label:
            continue
        visual_labels_by_q[qn].add(label.lower())

    if visual_subparts_exist:
        for qn, q in list(q_by_num.items()):
            if not _allows_visual_subparts(q):
                continue
            keep_labels: Set[str] = visual_labels_by_q.get(qn) or set()
            if keep_labels:
                filtered = []
                for sq in (q.get("subquestions") or []):
                    lbl = str(sq.get("label") or "").strip().lower()
                    if lbl and keep_labels and lbl in keep_labels:
                        filtered.append(sq)
                q["subquestions"] = filtered
            q_by_num[qn] = q

    for row in (visual_entities or {}).get("questions") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("number"), 0)
        if qn <= 0:
            continue
        if qn not in q_by_num:
            q_by_num[qn] = {
                "number": qn,
                "section": None,
                "instruction": None,
                "question_text": "",
                "question_type": "descriptive",
                "marks": 0.0,
                "mark_source": "inferred",
                "mark_confidence": 0.0,
                "options": None,
                "subquestions": [],
                "or_group_id": None,
                "image_evidence": [],
                "ai_confidence": 0.0,
                "confidence": 0.0,
            }
        q = q_by_num[qn]
        ev = {
            "page_index": _to_int(row.get("page"), 0),
            "bbox": row.get("bbox"),
            "visual_confidence": _to_float(row.get("confidence"), 0.0),
        }
        existing = list(q.get("image_evidence") or [])
        if ev not in existing:
            existing.append(ev)
        q["image_evidence"] = existing
        q_by_num[qn] = q

    for row in (visual_entities or {}).get("subparts") or []:
        if not isinstance(row, dict):
            continue
        qn = _to_int(row.get("q"), 0)
        label = str(row.get("label") or "").strip()
        if qn <= 0 or not label:
            continue
        q = q_by_num.get(qn)
        if not q:
            continue
        if not _allows_visual_subparts(q):
            continue
        subparts = list(q.get("subquestions") or [])
        if not any(str(sq.get("label") or "").strip().lower() == label.lower() for sq in subparts):
            subparts.append(
                {
                    "label": label,
                    "text": "",
                    "marks": 0.0,
                    "mark_source": "inferred",
                    "mark_confidence": 0.0,
                    "confidence": _to_float(row.get("confidence"), 0.0),
                    "image_evidence": [
                        {
                            "page_index": _to_int(row.get("page"), 0),
                            "bbox": row.get("bbox"),
                            "visual_confidence": _to_float(row.get("confidence"), 0.0),
                        }
                    ],
                }
            )
        q["subquestions"] = sorted(subparts, key=lambda sq: str(sq.get("label") or ""))
        q_by_num[qn] = q

    or_map = build_or_groups_from_visual(visual_entities)
    for qn, gid in or_map.items():
        if qn in q_by_num:
            q_by_num[qn]["or_group_id"] = gid

    for qn, q in list(q_by_num.items()):
        if _demote_choice_subparts(q):
            q_by_num[qn] = q

    section_math_blocks: List[Dict[str, Any]] = []
    for row in (visual_entities or {}).get("section_math") or []:
        if not isinstance(row, dict):
            continue
        range_raw = row.get("range")
        range_obj = None
        if isinstance(range_raw, dict):
            start = _to_int(range_raw.get("start"), 0)
            end = _to_int(range_raw.get("end"), 0)
            if start > 0 and end >= start:
                range_obj = {"start": start, "end": end}
        section_math_blocks.append(
            {
                "section": None,
                "expression": str(row.get("expr") or ""),
                "question_count": _to_int(row.get("count"), 0),
                "per_question_marks": _to_float(row.get("per"), 0.0),
                "total_marks": _to_float(row.get("total"), 0.0),
                "page_index": _to_int(row.get("page"), 0),
                "confidence": _to_float(row.get("confidence"), 0.0),
                "range": range_obj,
            }
        )

    merged = {
        "questions": [q_by_num[k] for k in sorted(q_by_num.keys())],
        "section_math_blocks": section_math_blocks,
        "total_questions": len(q_by_num),
        "total_marks": 0.0,
        "effective_total_marks": 0.0,
        "numbering_contiguous": True,
    }
    return normalize_structure_payload(merged)


def clip_to_expected_question_count(
    structure: Dict[str, Any],
    visual_entities: Dict[str, Any],
    expected_question_count: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    expected = _to_int(expected_question_count, 0)
    if expected <= 0:
        return structure, visual_entities

    normalized = normalize_structure_payload(structure or {})
    kept_questions = []
    for q in (normalized.get("questions") or []):
        qn = _to_int(q.get("number"), 0)
        if 1 <= qn <= expected:
            kept_questions.append(q)

    by_num: Dict[int, Dict[str, Any]] = {}
    for q in kept_questions:
        qn = _to_int(q.get("number"), 0)
        if qn <= 0:
            continue
        if qn not in by_num:
            by_num[qn] = q
        else:
            by_num[qn] = merge_questions(by_num[qn], q)

    normalized["questions"] = [by_num[n] for n in sorted(by_num.keys())]
    normalized["total_questions"] = len(normalized["questions"])

    ve = dict(visual_entities or {})
    ve["questions"] = [
        row for row in (ve.get("questions") or [])
        if 1 <= _to_int((row or {}).get("number"), 0) <= expected
    ]
    ve["subparts"] = [
        row for row in (ve.get("subparts") or [])
        if 1 <= _to_int((row or {}).get("q"), 0) <= expected
    ]
    ve["margin_marks"] = [
        row for row in (ve.get("margin_marks") or [])
        if 1 <= _to_int((row or {}).get("q"), 0) <= expected
    ]
    ve["or_connectors"] = [
        row for row in (ve.get("or_connectors") or [])
        if 1 <= _to_int((row or {}).get("q1"), 0) <= expected
        and 1 <= _to_int((row or {}).get("q2"), 0) <= expected
    ]
    return normalized, ve


def extract_partial_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    snippets = extract_balanced_json_candidates(raw_text, max_candidates=4096)
    if not snippets:
        return None

    questions_by_number: Dict[int, Dict[str, Any]] = {}
    section_math_blocks: List[Dict[str, Any]] = []
    section_math_seen: set[Tuple[str, int, float, float]] = set()

    for snippet in snippets:
        parsed = parse_any_json_value(snippet)
        if parsed is None:
            continue

        payload = as_payload_dict(parsed)
        if isinstance(payload, dict):
            for q in (payload.get("questions") or []):
                if not isinstance(q, dict):
                    continue
                qn = _to_int(q.get("number"), 0)
                if qn <= 0:
                    continue
                if qn not in questions_by_number:
                    questions_by_number[qn] = dict(q)
                else:
                    questions_by_number[qn] = merge_questions(questions_by_number[qn], q)
            for b in (payload.get("section_math_blocks") or []):
                if not isinstance(b, dict):
                    continue
                key = (
                    str(b.get("expression") or "").strip(),
                    _to_int(b.get("question_count"), 0),
                    round(_to_float(b.get("per_question_marks"), 0.0), 4),
                    round(_to_float(b.get("total_marks"), 0.0), 4),
                )
                if key in section_math_seen:
                    continue
                section_math_seen.add(key)
                section_math_blocks.append(dict(b))
            continue

        if isinstance(parsed, dict) and looks_like_question_dict(parsed):
            qn = _to_int(parsed.get("number"), 0)
            if qn not in questions_by_number:
                questions_by_number[qn] = dict(parsed)
            else:
                questions_by_number[qn] = merge_questions(questions_by_number[qn], parsed)
            continue

        if isinstance(parsed, dict) and looks_like_section_math_block(parsed):
            key = (
                str(parsed.get("expression") or "").strip(),
                _to_int(parsed.get("question_count"), 0),
                round(_to_float(parsed.get("per_question_marks"), 0.0), 4),
                round(_to_float(parsed.get("total_marks"), 0.0), 4),
            )
            if key not in section_math_seen:
                section_math_seen.add(key)
                section_math_blocks.append(dict(parsed))
            continue

    if not questions_by_number and not section_math_blocks:
        return None

    ordered_questions = [questions_by_number[n] for n in sorted(questions_by_number.keys())]
    return {
        "questions": ordered_questions,
        "section_math_blocks": section_math_blocks,
        "total_questions": len(ordered_questions),
        "total_marks": sum(_to_float(q.get("marks"), 0.0) for q in ordered_questions),
        "effective_total_marks": 0.0,
        "numbering_contiguous": False,
    }


def try_parse_candidate(candidate: str) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None

    parsed = parse_any_json_value(candidate)
    payload = as_payload_dict(parsed)
    if payload is not None:
        return payload
    return None


def parse_json_object(raw_text: str) -> Dict[str, Any]:
    if not raw_text:
        raise CustomServiceException("empty_llm_response", 500)

    text = raw_text.strip()
    candidates: List[str] = [text]
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
        block = (match.group(1) or "").strip()
        if block:
            candidates.append(block)

    candidates.extend(extract_balanced_json_candidates(raw_text))

    obj_match = re.search(r"\{\s*\"questions\"[\s\S]*\}", raw_text)
    if obj_match:
        candidates.append(obj_match.group(0).strip())
    arr_match = re.search(r"\[[\s\S]*\]", raw_text)
    if arr_match:
        candidates.append(arr_match.group(0).strip())

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        parsed = try_parse_candidate(candidate)
        if parsed is not None:
            return parsed

    partial = extract_partial_payload(raw_text)
    if partial:
        logger.warning(
            "STRUCTURE_JSON_PARTIAL_RECOVERY questions=%s section_math_blocks=%s",
            len(partial.get("questions") or []),
            len(partial.get("section_math_blocks") or []),
        )
        return partial

    preview = text[:400].replace("\n", "\\n")
    logger.warning(
        "STRUCTURE_JSON_PARSE_FAILED len=%s preview=%s",
        len(raw_text or ""),
        preview,
    )

    raise CustomServiceException("invalid_json_response", 500)


def parse_visual_json_object(raw_text: str) -> Dict[str, Any]:
    logger.info("DEBUG_RAW_VISUAL_LLM_RESPONSE: %s", raw_text)
    if not raw_text:
        raise CustomServiceException("empty_llm_response", 500)

    text = raw_text.strip()
    candidates: List[str] = [text]
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
        block = (match.group(1) or "").strip()
        if block:
            candidates.append(block)

    candidates.extend(extract_balanced_json_candidates(raw_text))
    arr_match = re.search(r"\[[\s\S]*\]", raw_text)
    if arr_match:
        candidates.append(arr_match.group(0).strip())
    obj_match = re.search(r"\{[\s\S]*\}", raw_text)
    if obj_match:
        candidates.append(obj_match.group(0).strip())

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        parsed = parse_any_json_value(candidate)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            if len(parsed) == 1 and isinstance(parsed[0], dict):
                return parsed[0]
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                if any(k in item for k in ("questions", "subparts", "margin_marks", "section_math_rules", "or_pairs", "headers")):
                    return item

    preview = text[:400].replace("\n", "\\n")
    logger.warning(
        "VISUAL_JSON_PARSE_FAILED len=%s preview=%s",
        len(raw_text or ""),
        preview,
    )
    raise CustomServiceException("invalid_json_response", 500)


def normalize_type(value: Any) -> str:
    t = str(value or "descriptive").strip().lower()
    if t in _ALLOWED_TYPES:
        return t
    alias = {
        "objective": "mcq",
        "fill in the blank": "fill_blank",
        "fill_in_the_blank": "fill_blank",
        "very short": "very_short",
        "short answer": "short",
        "long answer": "long",
        "theory": "descriptive",
        "or": "or_group",
    }
    return alias.get(t, "descriptive")


def normalize_batch_payload(payload: Dict[str, Any], page_offset: int) -> Dict[str, Any]:
    payload = payload or {}
    questions = payload.get("questions") or []
    normalized_questions: List[Dict[str, Any]] = []
    section_math_blocks: List[Dict[str, Any]] = []

    for q in questions:
        if not isinstance(q, dict):
            continue
        qn = _to_int(q.get("number"), 0)
        if qn <= 0:
            continue

        subquestions: List[Dict[str, Any]] = []
        for sq in (q.get("subquestions") or []):
            if not isinstance(sq, dict):
                continue
            label = str(sq.get("label") or "").strip()
            if not label:
                continue
            subquestions.append(
                {
                    "label": label,
                    "text": str(sq.get("text") or "").strip(),
                    "marks": 0.0,
                    "mark_source": "inferred",
                    "mark_confidence": 0.0,
                    "confidence": _to_float(sq.get("confidence"), 0.0),
                    "image_evidence": list(sq.get("image_evidence") or []),
                }
            )

        evidence = []
        for ev in (q.get("image_evidence") or []):
            if not isinstance(ev, dict):
                continue
            try:
                page_index = int(ev.get("page_index", 0)) + page_offset
            except Exception:
                page_index = page_offset
            evidence.append(
                {
                    "page_index": max(0, page_index),
                    "bbox": ev.get("bbox"),
                    "visual_confidence": _to_float(ev.get("visual_confidence"), 0.0),
                }
            )

        normalized_questions.append(
            {
                "number": qn,
                "section": (str(q.get("section") or "").strip() or None),
                "instruction": (str(q.get("instruction") or "").strip() or None),
                "question_text": str(q.get("question_text") or "").strip(),
                "question_type": normalize_type(q.get("question_type")),
                "marks": 0.0,
                "mark_source": "inferred",
                "mark_confidence": 0.0,
                "options": list(q.get("options") or []) or None,
                "subquestions": subquestions,
                "or_group_id": None,
                "image_evidence": evidence,
                "ai_confidence": _to_float(q.get("ai_confidence", q.get("confidence")), 0.0),
                "confidence": _to_float(q.get("confidence", q.get("ai_confidence")), 0.0),
            }
        )

    return {
        "questions": normalized_questions,
        "section_math_blocks": section_math_blocks,
        "total_questions": int(payload.get("total_questions") or len(normalized_questions)),
        "total_marks": 0.0,
        "effective_total_marks": 0.0,
        "numbering_contiguous": bool(payload.get("numbering_contiguous", False)),
    }

async def extract_visual_entities_pipeline(
    question_paper_images: List[str],
    model_name: str,
    llm_service: AbstractLLMService,
) -> Dict[str, Any]:
    """Layer 1: multimodal visual evidence (Gemini Vision), fallback to OCR visual layer."""
    batch_size = max(1, int(os.getenv("AI_STRUCTURED_PAGE_BATCH_SIZE", "4")))
    chunks: List[Tuple[int, List[str]]] = []
    for i in range(0, len(question_paper_images), batch_size):
        chunk_slice = question_paper_images[i:i + batch_size]
        chunks.append((i, list(chunk_slice)))

    async def _extract_visual_chunk(start_idx: int, chunk_images: List[str], idx: int, total: int) -> Dict[str, Any]:
        prompt = build_visual_extraction_prompt(
            batch_index=idx,
            total_batches=total,
            page_offset=start_idx,
        )
        # Use a vision-capable model for the visual layer.
        vision_model = "llama3.2-vision:latest" if "llama" in str(model_name).lower() or "qwen" in str(model_name).lower() else model_name
        try:
            payload_str = await llm_step.call_visual_extraction_llm(llm_service, prompt, chunk_images)
            payload = parse_visual_json_object(payload_str)
            return normalize_visual_payload(payload, page_offset=start_idx, page_count=len(chunk_images))
        except Exception as exc:
            logger.warning("VISUAL_CHUNK_FAILED batch=%s/%s error=%s", idx, total, exc)
            return {
                "questions": [],
                "subparts": [],
                "margin_marks": [],
                "section_math": [],
                "or_connectors": [],
                "headers": [],
                "header_total": None,
            }

    total = len(chunks)
    async def _runner(item: Tuple[int, List[str]], idx: int) -> Dict[str, Any]:
        start_idx, imgs = item
        return await _extract_visual_chunk(start_idx, imgs, idx, total)

    tasks = [asyncio.create_task(_runner(item, idx + 1)) for idx, item in enumerate(chunks)]
    batch_payloads = await asyncio.gather(*tasks)

    merged: Dict[str, Any] = {
        "questions": [],
        "subparts": [],
        "margin_marks": [],
        "section_math": [],
        "or_connectors": [],
        "headers": [],
        "header_total": None,
    }
    for chunk_payload in batch_payloads:
        merged["questions"].extend(chunk_payload.get("questions") or [])
        merged["subparts"].extend(chunk_payload.get("subparts") or [])
        merged["margin_marks"].extend(chunk_payload.get("margin_marks") or [])
        merged["section_math"].extend(chunk_payload.get("section_math") or [])
        merged["or_connectors"].extend(chunk_payload.get("or_connectors") or [])
        merged["headers"].extend(chunk_payload.get("headers") or [])
        if not merged.get("header_total") and chunk_payload.get("header_total"):
            merged["header_total"] = chunk_payload.get("header_total")
    return merged


async def extract_semantic_structure_pipeline(
    question_paper_images: List[str],
    raw_ocr_text: str,
    prompt_extra_rules: List[str],
    llm_service: AbstractLLMService,
) -> Dict[str, Any]:
    """Layer 2: Gemini semantic extraction only (marks ignored)."""
    batch_size = max(1, int(os.getenv("AI_STRUCTURED_PAGE_BATCH_SIZE", "4")))
    chunks: List[Tuple[int, List[str]]] = []
    for i in range(0, len(question_paper_images), batch_size):
        chunk_slice = question_paper_images[i:i + batch_size]
        chunks.append((i, list(chunk_slice)))

    async def _extract_chunk(start_idx: int, chunk_images: List[str], idx: int, total: int) -> Dict[str, Any]:
        prompt = build_extraction_prompt(
            raw_ocr_text=raw_ocr_text,
            batch_index=idx,
            total_batches=total,
            extra_rules=prompt_extra_rules,
        )
        try:
            payload_str = await llm_step.call_extraction_llm(llm_service, prompt, chunk_images)
            payload = parse_json_object(payload_str)
            return normalize_batch_payload(payload, page_offset=start_idx)
        except Exception as exc:
            logger.warning("SEMANTIC_CHUNK_FAILED batch=%s/%s error=%s", idx, total, exc)
            return {
                "questions": [],
                "section_math_blocks": [],
                "total_questions": 0,
                "total_marks": 0.0,
                "effective_total_marks": 0.0,
                "numbering_contiguous": False,
            }

    total = len(chunks)
    async def _runner(item: Tuple[int, List[str]], idx: int) -> Dict[str, Any]:
        start_idx, imgs = item
        return await _extract_chunk(start_idx, imgs, idx, total)

    tasks = [asyncio.create_task(_runner(item, idx + 1)) for idx, item in enumerate(chunks)]
    batch_payloads = await asyncio.gather(*tasks)

    merged_structure_map: dict[int, dict[str, Any]] = {}
    for payload in batch_payloads:
        for q in (payload.get("questions") or []):
            qn = safe_int(q.get("number"), 0)
            if qn <= 0:
                continue
            if qn not in merged_structure_map:
                merged_structure_map[qn] = dict(q)
            else:
                merged_structure_map[qn] = merge_questions(merged_structure_map[qn], q)

    consolidated = {
        "questions": [merged_structure_map[k] for k in sorted(merged_structure_map.keys())],
        "section_math_blocks": [],
        "total_questions": len(merged_structure_map),
        "total_marks": 0.0,
        "effective_total_marks": 0.0,
        "numbering_contiguous": True,
    }
    return normalize_structure_payload(consolidated)


# MODULE INTERFACE START
to_float = _to_float
to_int = _to_int
__all__ = [
    "to_float",
    "to_int",
    "as_payload_dict",
    "extract_balanced_json_candidates",
    "sanitize_json_candidate",
    "repair_json_string_content",
    "parse_any_json_value",
    "looks_like_question_dict",
    "looks_like_section_math_block",
    "normalize_visual_payload",
    "merge_questions",
    "build_or_groups_from_visual",
    "semantic_structure_from_visual_entities",
    "merge_semantic_with_visual_entities",
    "clip_to_expected_question_count",
    "extract_partial_payload",
    "try_parse_candidate",
    "parse_json_object",
    "parse_visual_json_object",
    "normalize_type",
    "normalize_batch_payload",
    "extract_visual_entities_pipeline",
    "extract_semantic_structure_pipeline",
]
# MODULE INTERFACE END
