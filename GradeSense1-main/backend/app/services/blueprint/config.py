"""Configuration constants for blueprint utilities."""

import os

SECTION_MARKERS = (
    "section a",
    "section b",
    "section c",
    "part a",
    "part b",
    "part c",
    "option i",
    "option ii",
)

# Default thresholds
BLUEPRINT_HEALTH_THRESHOLD = float(os.getenv("COLLEGE_V2_BLUEPRINT_HEALTH_THRESHOLD", "0.92"))
