from typing import List, Dict, Any
from .line_clustering import cluster_words_to_lines
from .block_clustering import cluster_lines_to_blocks


def _intersects(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return not (
        float(a.get("x2", 0)) < float(b.get("x1", 0))
        or float(a.get("x1", 0)) > float(b.get("x2", 0))
        or float(a.get("y2", 0)) < float(b.get("y1", 0))
        or float(a.get("y1", 0)) > float(b.get("y2", 0))
    )


def attach_tables_to_segments(segments: List[Dict[str, Any]], tables: List[Dict[str, Any]]) -> None:
    for seg in segments:
        seg["tables"] = []
        for table in tables or []:
            bbox = table.get("bbox") or [0, 0, 0, 0]
            tb = {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]}
            if _intersects(seg, tb):
                seg["tables"].append(table)


def build_page_segments(
    words: List[Dict[str, Any]],
    tables: List[Dict[str, Any]] = None,
    page: int = 1,
) -> List[Dict[str, Any]]:
    lines = cluster_words_to_lines(words)
    for line in lines:
        line["page"] = page
    segments = cluster_lines_to_blocks(lines)
    for seg in segments:
        seg["page"] = page
        seg["segment_id"] = f"P{page}-{seg['segment_id']}"
    attach_tables_to_segments(segments, tables or [])
    return segments
