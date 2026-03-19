import os
import re

# ==========================================
# FEATURE FLAGS & CORES CONFIGS
# ==========================================
DISABLE_ANNOTATIONS = os.getenv("DISABLE_ANNOTATIONS", "true").lower() in ("1", "true", "yes", "on")
MODEL_ANSWER_OPTIONAL = os.getenv("MODEL_ANSWER_OPTIONAL", "true").lower() in ("1", "true", "yes", "on")
DISABLE_GRADING_CACHE = os.getenv("DISABLE_GRADING_CACHE", "false").lower() in ("1", "true", "yes", "on")
GRADING_CACHE_VERSION = os.getenv("GRADING_CACHE_VERSION", "packet-v5").strip() or "packet-v5"

# ==========================================
# MAPPING THRESHOLDS
# ==========================================
MAPPING_HARD_STOP = os.getenv("MAPPING_HARD_STOP", "true").lower() in ("1", "true", "yes", "on")
MAPPED_QUESTION_RATIO_MIN = float(os.getenv("MAPPED_QUESTION_RATIO_MIN", "0.85"))
MAPPING_COVERAGE_GATE_MIN = float(os.getenv("MAPPING_COVERAGE_GATE_MIN", "0.75"))
UNRESOLVED_RATIO_MAX = float(os.getenv("UNRESOLVED_RATIO_MAX", "0.10"))

# ==========================================
# COLLEGE V2 PARTIAL GRADING
# ==========================================
COLLEGE_V2_PIPELINE_ENABLED = os.getenv("COLLEGE_V2_PIPELINE_ENABLED", "false").lower() in ("1", "true", "yes", "on")
COLLEGE_V2_PARTIAL_GRADING_ENABLED = os.getenv("COLLEGE_V2_PARTIAL_GRADING_ENABLED", "true").lower() in ("1", "true", "yes", "on")
COLLEGE_V2_PARTIAL_MIN_MAPPED = int(os.getenv("COLLEGE_V2_PARTIAL_MIN_MAPPED", "1"))
COLLEGE_V2_PARTIAL_MIN_COVERAGE = float(os.getenv("COLLEGE_V2_PARTIAL_MIN_COVERAGE", "0.85"))

# ==========================================
# PDF PROCESSING
# ==========================================
GRADING_PDF_DPI = int(os.getenv("GRADING_PDF_DPI", "150"))
GRADING_PDF_NORMALIZE = os.getenv("GRADING_PDF_NORMALIZE", "false").lower() in ("1", "true", "yes", "on")
GRADING_USE_CLEAN_CONVERSION = os.getenv("GRADING_USE_CLEAN_CONVERSION", "false").lower() in ("1", "true", "yes", "on")

# ==========================================
# PIPELINE CONFIGS
# ==========================================
ANSWER_PACKET_PIPELINE_MIN_COVERAGE = float(os.getenv("ANSWER_PACKET_PIPELINE_MIN_COVERAGE", "0.55"))
ANSWER_PACKET_PIPELINE_MIN_Q_RATIO = float(os.getenv("ANSWER_PACKET_PIPELINE_MIN_Q_RATIO", "0.55"))
ANSWER_PACKET_PIPELINE_MIN_PACKETS = int(os.getenv("ANSWER_PACKET_PIPELINE_MIN_PACKETS", "4"))
OCR_CHUNK_INCLUDE_NEIGHBORS = os.getenv("OCR_CHUNK_INCLUDE_NEIGHBORS", "false").lower() in ("1", "true", "yes", "on")
OCR_FORCE_FALLBACK_ON_SPARSE = os.getenv("OCR_FORCE_FALLBACK_ON_SPARSE", "false").lower() in ("1", "true", "yes", "on")

# ==========================================
# JOB & TIMEOUT CONFIGS
# ==========================================
QUESTION_EXTRACTION_WAIT_SECONDS = int(os.getenv("QUESTION_EXTRACTION_WAIT_SECONDS", "120"))
GRADING_JOB_TIMEOUT_SECONDS = 1800.0  # 30 minutes
GRADING_JOB_STALE_LOCK_MINUTES = 20

# ==========================================
# CHUNKED PROCESSING
# ==========================================
DEFAULT_CHUNK_SIZE = 10
DEFAULT_OVERLAP = 1

# ==========================================
# QUALITY SCORING BOOSTS/PENALTIES
# ==========================================
# Weights used to rank candidate scores
RANK_BOOST_STATUS_GRADED = 3.0
RANK_PENALTY_STATUS_NOT_FOUND = -8.0
RANK_PENALTY_STATUS_NOT_ATTEMPTED = -2.0
RANK_PENALTY_FEEDBACK_NOT_FOUND = -6.0
RANK_BOOST_HAS_ANNOTATIONS = 1.5
RANK_BOOST_FULL_SUB_COVERAGE = 3.0
RANK_BOOST_PARTIAL_SUB_COVERAGE = 1.0

# ==========================================
# OCR & PATTERNS
# ==========================================
OCR_PREFIXES_PATTERN = r'^(ans|answer|option)[\s\.:-]*'
MCQ_LETTERS_PATTERN = r'^\(?([A-H])\)?[\s\.]'
MCQ_EXACT_PATTERN = r'^\(?([A-H])\)?$'
CONCEPT_DELIMITERS = r'[\.,]\s*'
BULLET_PATTERNS = r'(?m)^\s*[\*\-\•\d\.]+\s+'
CLEAN_BULLET_PATTERN = r'^[\*\-\•\d\.]+\s*'
JSON_EXTRACTOR_PATTERN = r'(\{.*\})'

# Stopwords for concept matching
DEFAULT_STOPWORDS = ["the", "and", "of", "to", "in", "a", "an", "for", "on", "with"]

# Match ratio threshold for concept matching
MATCH_RATIO_THRESHOLD = 0.5

# ==========================================
# DEFAULTS & BOUNDS
# ==========================================
DEFAULT_SCORE_BOUNDS = (0.0, 1.0)
DEFAULT_GRADING_MODE = "balanced"
DEFAULT_UPSC_CAP_RATIO = 0.5

# ==========================================
# PROMPT TEMPLATES (Old - kept for reference if needed)
# ==========================================
LLM_PROMPT_TEMPLATE = """
You are an expert exam evaluator providing feedback on student answers extracted from OCR text.
You receive OCR text that may contain noise. Your task is to analyze the student's answer and provide helpful feedback.

### INPUT
Question Number: {question_number}
Question: {question_text}
Expected Answer / Model Answer: {model_answer}
Student Answer (OCR Text): {student_answer}

---

### CONCEPT ANALYSIS

Correct concepts detected:
{matched_concepts}

Missing concepts:
{missing_concepts}

---

### EVALUATION PROCESS

#### Step 1 — Interpret the Student Answer
Analyze the OCR text and identify the meaningful content. Ignore noise such as page numbers or formatting artifacts.

#### Step 2 — Analyze Concept Coverage
Based on the detected and missing concepts, evaluate how well the student understood the topic.

#### Step 3 — Generate Feedback
Provide brief feedback explaining:
* what the student did correctly
* what is missing or incorrect

Feedback should be clear and helpful.
Do not mention OCR or images in the feedback.

---

### OUTPUT FORMAT
Return only valid JSON. 
{{
"attempted": true or false,
"relevant": true or false,
"score": 5.0
"feedback": "brief overall summary",
"strengths": "what the student did well",
"weaknesses": "what was missing or wrong",
"suggestions": "how to improve",
"detailed_explanation": "justification of the feedback"
}}

Do not include any additional text outside the JSON.
"""
