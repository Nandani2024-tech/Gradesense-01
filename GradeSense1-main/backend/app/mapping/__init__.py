from .config import (
    ANCHOR_LEFT_RATIO,
    MAPPING_COVERAGE_MIN,
    SPARSE_WORD_THRESHOLD,
    SUBLABEL_DETECT_ENABLED,
    TABLE_STICKY_ENABLED,
    WORKING_NOTE_STICKY_ENABLED,
    SEMANTIC_REPAIR_SIM_MIN,
    SEMANTIC_OVERRIDE_ANCHOR,
    SPARSE_ALLOW_ANCHOR,
)
from .margin_detection import detect_margin_labels, normalize_question_number
from .subquestion_detection import detect_subquestion_id
from .segment_analysis import _jaccard_similarity
from .question_mapper_core import map_segments_to_questions
