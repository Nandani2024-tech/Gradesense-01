import os
import yaml
from pathlib import Path
from typing import Dict, Any

PROMPTS_DIR = Path(__file__).parent

def _load_yaml(filename: str) -> Dict[str, Any]:
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

EXTRACTION_PROMPTS = _load_yaml("extraction_prompts.yaml")
GRADING_PROMPTS = _load_yaml("grading_prompts.yaml")

def get_prompt(group: str, key: str, **kwargs) -> str:
    """
    Retrieve and format a prompt from a loaded YAML dictionary.
    Usage: get_prompt("extraction", "model_answer_extraction.user", start_page=1, end_page=5, ...)
    """
    prompts_map = EXTRACTION_PROMPTS if group == "extraction" else GRADING_PROMPTS
    
    parts = key.split(".")
    curr = prompts_map
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        else:
            return ""
    
    if isinstance(curr, str):
        if kwargs:
            try:
                # Use simple replace for kwargs to avoid escaping issues with JSON-like prompts
                for k, v in kwargs.items():
                    curr = curr.replace(f"{{{k}}}", str(v))
                return curr
            except Exception as e:
                return curr
        return curr
    return ""
