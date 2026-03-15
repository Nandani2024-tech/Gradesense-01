import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

COLLEGE_V2_PIPELINE_ENABLED = _env_flag("COLLEGE_V2_PIPELINE_ENABLED", "true")
COLLEGE_V2_HARD_STOP = _env_flag("COLLEGE_V2_HARD_STOP", "true")
UNIVERSAL_PIPELINE_ENABLED = _env_flag("UNIVERSAL_PIPELINE_ENABLED", "false")
UNIVERSAL_HARD_STOP = _env_flag("UNIVERSAL_HARD_STOP", "true")
UNIVERSAL_PIPELINE_EXAM_TYPES = [
    item.strip().lower()
    for item in os.getenv("UNIVERSAL_PIPELINE_EXAM_TYPES", "college,school,universal").split(",")
    if item.strip()
]
UNIVERSAL_ORPHAN_BLOCK_RATIO_THRESHOLD = float(os.getenv("UNIVERSAL_ORPHAN_BLOCK_RATIO_THRESHOLD", "0.15"))
UNIVERSAL_CONTINUITY_SPATIAL_WEIGHT = float(os.getenv("UNIVERSAL_CONTINUITY_SPATIAL_WEIGHT", "0.4"))
UNIVERSAL_CONTINUITY_STRUCTURAL_WEIGHT = float(os.getenv("UNIVERSAL_CONTINUITY_STRUCTURAL_WEIGHT", "0.3"))
UNIVERSAL_CONTINUITY_SEMANTIC_WEIGHT = float(os.getenv("UNIVERSAL_CONTINUITY_SEMANTIC_WEIGHT", "0.3"))
UNIVERSAL_CONTINUITY_ATTACH_THRESHOLD = float(os.getenv("UNIVERSAL_CONTINUITY_ATTACH_THRESHOLD", "0.65"))
UNIVERSAL_CONTINUITY_MAX_PAGE_GAP = int(os.getenv("UNIVERSAL_CONTINUITY_MAX_PAGE_GAP", "1"))
UNIVERSAL_CONTINUITY_SEMANTIC_PROVIDER = os.getenv("UNIVERSAL_CONTINUITY_SEMANTIC_PROVIDER", "gemini").strip().lower()

# Marking scheme validation
MARK_VALIDATION_ENABLED = _env_flag("MARK_VALIDATION_ENABLED", "true")
