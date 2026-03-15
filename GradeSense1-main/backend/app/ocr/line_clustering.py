from typing import List, Dict, Any


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return float(values[mid])
    return float(values[mid - 1] + values[mid]) / 2.0


def cluster_words_to_lines(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for w in words or []:
        text = str(w.get("text", "")).strip()
        if not text:
            continue
        try:
            x1 = float(w.get("x1", 0))
            y1 = float(w.get("y1", 0))
            x2 = float(w.get("x2", 0))
            y2 = float(w.get("y2", 0))
        except Exception:
            continue
        items.append({
            "text": text,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "yc": (y1 + y2) / 2.0,
            "conf": float(w.get("conf", w.get("confidence", 0.0)) or 0.0),
            "page": int(w.get("page", 1) or 1),
        })

    if not items:
        return []
    items.sort(key=lambda i: (i["yc"], i["x1"]))
    heights = [max(1.0, i["y2"] - i["y1"]) for i in items]
    y_tolerance = max(8.0, _median(heights) * 0.6)

    line_groups: List[List[Dict[str, Any]]] = []
    for item in items:
        if not line_groups:
            line_groups.append([item])
            continue
        last = line_groups[-1]
        if abs(item["yc"] - last[-1]["yc"]) <= y_tolerance:
            last.append(item)
        else:
            line_groups.append([item])

    lines: List[Dict[str, Any]] = []
    for idx, group in enumerate(line_groups, start=1):
        group.sort(key=lambda i: i["x1"])
        xs = [g["x1"] for g in group] + [g["x2"] for g in group]
        ys = [g["y1"] for g in group] + [g["y2"] for g in group]
        lines.append({
            "line_id": f"L{idx}",
            "text": " ".join(g["text"] for g in group).strip(),
            "x1": min(xs),
            "y1": min(ys),
            "x2": max(xs),
            "y2": max(ys),
            "conf": sum(g["conf"] for g in group) / max(1, len(group)),
            "page": group[0]["page"],
            "words": group,
        })
    return lines
