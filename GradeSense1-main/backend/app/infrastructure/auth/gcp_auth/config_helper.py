"""Configuration helpers for GCP authentication."""

import os
from pathlib import Path
from app.core.config import ROOT_DIR

def resolve_gcp_path(path_str: str) -> Path:
    """
    Resolve a path string to an absolute path.
    If the path is relative, it's assumed to be relative to ROOT_DIR.
    """
    path = Path(path_str)
    if not path.is_absolute():
        return ROOT_DIR / path
    return path

def get_env_var(name: str, default: str = None) -> str:
    """Helper to get environment variables."""
    return os.environ.get(name, default)
