"""
Legacy wrapper for the newly modularized grading system.
This file maintains backward compatibility for all existing imports.
"""

# Re-export all constants
from .constants import *

# Re-export utility functions with original names
from .normalization import normalize_q_key as _normalize_q_key, normalize_sub_key as _normalize_sub_key
from .scoring_quality import calculate_candidate_quality as _candidate_quality
from .aggregation import aggregate_from_sub_marks as _aggregate_from_sub_marks

# Re-export main entry points
from .ai_grader import grade_with_ai
from .background_job import process_grading_job_in_background, _process_grading_job_core

# Re-export cache variables (for any direct access)
from .cache_storage import grading_cache, grading_cache_meta

# Backward compatibility with functions that might be called with older names/patterns
# everything is already handled by imports above as they use the correct names.

__all__ = [
    'grade_with_ai',
    'process_grading_job_in_background',
    '_process_grading_job_core',
    '_normalize_q_key',
    '_normalize_sub_key',
    '_candidate_quality',
    '_aggregate_from_sub_marks',
    'grading_cache',
    'grading_cache_meta'
]

# Ensure constants are also in __all__ if needed, 
# although from .constants import * already handles most of them.
