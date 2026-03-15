import re
from typing import Any, Dict, List

_SIMPLE_Q_ANCHOR = re.compile(r"(?:q\.?\s*)?0*(\d{1,3})(?:[\).:]|\b)", re.IGNORECASE)

def _text_only_build_packets(pdf_bytes: bytes, blueprint: List[Dict[str, Any]]) -> Dict[int, dict]:
    """Minimal packet builder that ignores layout and just splits by line anchors."""
    import fitz
    out: Dict[int, dict] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text = page.get_text("text") or ""
            for ln in text.splitlines():
                m = _SIMPLE_Q_ANCHOR.search(ln or "")
                if m:
                    qn = int(m.group(1))
                    if qn not in out:
                        out[qn] = {"combined_text": ""}
                    current = qn
                if out and 'current' in locals() and current:
                    out[current]["combined_text"] += ln + "\n"
    except Exception:
        pass
    return out
