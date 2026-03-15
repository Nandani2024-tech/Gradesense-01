"""Color parsing and helper utilities for annotations."""

from typing import Tuple

def _parse_color(color_str: str) -> Tuple[int, int, int, int]:
    """Parse a color string to RGBA tuple."""
    if not color_str:
        return (255, 0, 0, 220)
    color_str = color_str.strip().lower()
    named = {
        "red": (220, 30, 30, 230),
        "green": (0, 150, 0, 230),
        "blue": (30, 30, 200, 230),
        "black": (0, 0, 0, 230),
    }
    if color_str in named:
        return named[color_str]
    if color_str.startswith("#") and len(color_str) >= 7:
        try:
            r = int(color_str[1:3], 16)
            g = int(color_str[3:5], 16)
            b = int(color_str[5:7], 16)
            return (r, g, b, 230)
        except ValueError:
            pass
    return (220, 30, 30, 230)
