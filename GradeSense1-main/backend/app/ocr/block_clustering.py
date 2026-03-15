from typing import List, Dict, Any
from .line_clustering import _median


def cluster_lines_to_blocks(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda l: (float(l.get("y1", 0)), float(l.get("x1", 0))))
    heights = [max(1.0, float(l.get("y2", 0)) - float(l.get("y1", 0))) for l in sorted_lines]
    median_line_height = _median(heights) or 8.0
    # Deterministic split: new segment when vertical gap exceeds 1.8x median line height.
    y_gap_threshold = median_line_height * 1.8

    blocks: List[List[Dict[str, Any]]] = []
    for line in sorted_lines:
        if not blocks:
            blocks.append([line])
            continue
        prev_line = blocks[-1][-1]
        gap = float(line.get("y1", 0)) - float(prev_line.get("y2", 0))
        if gap <= y_gap_threshold:
            blocks[-1].append(line)
        else:
            blocks.append([line])

    out: List[Dict[str, Any]] = []
    for idx, group in enumerate(blocks, start=1):
        xs = [float(l["x1"]) for l in group] + [float(l["x2"]) for l in group]
        ys = [float(l["y1"]) for l in group] + [float(l["y2"]) for l in group]
        out.append({
            "segment_id": f"S{idx}",
            "text": " ".join((l.get("text") or "") for l in group).strip(),
            "x1": min(xs),
            "y1": min(ys),
            "x2": max(xs),
            "y2": max(ys),
            "line_refs": [l.get("line_id") for l in group if l.get("line_id")],
            "confidence": sum(float(l.get("conf", 0.0)) for l in group) / max(1, len(group)),
            "page": int(group[0].get("page", 1) or 1),
            "lines": group,
        })
    out.sort(key=lambda b: (float(b["y1"]), float(b["x1"])))
    return out
