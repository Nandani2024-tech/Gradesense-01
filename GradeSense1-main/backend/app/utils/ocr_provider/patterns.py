import re

# Question anchor patterns
# Matches: Q1, Q.1, 1., 1), Question 1, etc.
QUESTION_ANCHOR_RE = re.compile(
    r"^(?:q(?:uestion)?\s*)?(\d{1,3})(?!\d)\s*[).:-]\s*", 
    re.IGNORECASE
)

# Subpart patterns
# Matches: (a), a), (i), i., etc.
SUBPART_RE = re.compile(
    r"^\s*(?:[\(\[]\s*([a-z])\s*[\)\]]|([a-z])[\).]|[\(\[]\s*(i{1,4}|v|vi{0,3}|ix|x)\s*[\)\]]|(i{1,4}|v|vi{0,3}|ix|x)[\).])",
    re.IGNORECASE
)

# Working note patterns
WORKING_NOTE_RE = re.compile(
    r"\b(?:working\s*note|wn|note|calculation|working)\b", 
    re.IGNORECASE
)

# Mark value patterns
# Matches: 5 marks, (10), [5 + 5], etc.
MARK_VALUE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:marks?|mks?)\b", 
    re.IGNORECASE
)

MARK_SPLIT_RE = re.compile(
    r"^\s*[\(\[\{]?\s*(\d+(?:\.\d+)?(?:\s*\+\s*\d+(?:\.\d+)?)+)\s*[\)\]\}]?\s*$",
    re.IGNORECASE
)

MARK_ONLY_RE = re.compile(
    r"^\s*[\(\[\{]?\s*(\d+(?:\.\d+)?)\s*[\)\]\}]?\s*$"
)
