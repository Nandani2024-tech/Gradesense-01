import os

MARGIN_X = 30
SKIP_INTRO_PAGES = int(os.environ.get("SKIP_ANNOTATION_INTRO_PAGES", "3"))

POSITIVE_LABELS = [
    "Well explained point", "Strong constitutional basis", "Relevant case law cited", 
    "Accurate data with source", "Good substantiation", "Proper legal framework",
    "Contextual understanding shown", "Evidence-based claim", "Strong argumentation"
]

CRITICAL_LABELS = [
    "Needs more examples", "Lacks substantiation", "Missing key statute", 
    "Vague explanation needed", "Should cite relevant case", "Incomplete coverage",
    "Needs schedule/article reference", "Lacks constitutional basis", "More clarity needed"
]
