from typing import Any, Dict, List, Optional
from app.services.answer_sheet_pipeline.regex_patterns import TO_ACCOUNT_RE, BY_ACCOUNT_RE, AMOUNT_RE, FORMULA_RE, WORKING_NOTE_RE


def structure_accounting_answer(packet: Optional[dict]) -> Dict[str, Any]:
    """Stage 7 accounting structuring from packet text blocks."""
    if not packet:
        return {
            "accounts": [],
            "journal_entries": [],
            "calculations": [],
            "totals": [],
            "reasoning": [],
        }

    lines: List[str] = []
    for blk in packet.get("text_blocks", []):
        text = str(blk.get("text", "") or "").strip()
        if not text:
            continue
        for ln in text.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)

    accounts = set()
    journal_entries: List[dict] = []
    calculations: List[str] = []
    totals: List[dict] = []
    reasoning: List[str] = []

    for line in lines:
        m_to = TO_ACCOUNT_RE.match(line)
        m_by = BY_ACCOUNT_RE.match(line)
        side = None
        acc_name = None
        if m_to:
            side = "Dr"
            acc_name = m_to.group(1).strip()
        elif m_by:
            side = "Cr"
            acc_name = m_by.group(1).strip()
        if acc_name:
            accounts.add(acc_name)
            amt_m = AMOUNT_RE.search(line)
            amount = amt_m.group(1).replace(",", "") if amt_m else None
            journal_entries.append({"side": side, "account": acc_name, "amount": amount, "line": line})

        low = line.lower()
        if "total" in low or "balance c/d" in low or "balance b/d" in low:
            amt_m = AMOUNT_RE.search(line)
            totals.append({"line": line, "amount": (amt_m.group(1).replace(",", "") if amt_m else None)})

        if FORMULA_RE.search(line) and any(ch.isdigit() for ch in line):
            calculations.append(line)
        if WORKING_NOTE_RE.search(line):
            reasoning.append(line)

    return {
        "accounts": sorted(accounts),
        "journal_entries": journal_entries,
        "calculations": calculations,
        "totals": totals,
        "reasoning": reasoning,
    }
