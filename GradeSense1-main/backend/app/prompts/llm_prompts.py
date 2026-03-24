"""
Centralized LLM Prompts Module

This module contains all prompts used for interacting with Large Language Models.
Version each prompt (e.g., _v1) to allow for non-breaking changes and snapshot comparison.

To update a prompt:
1. Create a new version (e.g., v2).
2. Update the calling code to point to the new version when ready.
"""

# --- EXTRACTION PROMPTS ---

# Used in extraction/auto_extraction.py for full question paper analysis
EXTRACTION_SYSTEM_PROMPT_v1 = "You are an expert exam extraction AI. Extract the full question paper structure into valid JSON."

# Used in extraction/auto_extraction.py for model answer extraction
MODEL_ANSWER_EXTRACTION_SYSTEM_v1 = "You are an expert at extracting model answers from images and comparing them against a set of questions."

# Used in extraction/auto_extraction.py for individual question extraction
SINGLE_QUESTION_EXTRACTION_USER_v1 = "Extract this specific exam question as strict JSON."

# --- MARK VALIDATION PROMPTS ---

# Used in extraction/mark_validation.py (though currently unused, moved for centralization)
MARK_VALIDATION_SYSTEM_PROMPT_v1 = """You are an exam-analysis assistant. The user will upload a PDF of a question paper (any subject). Your goal is to extract the marks allocation for each question and each sub-question.

Tasks:
1) Identify each question number (e.g., Q1, Q2, etc.) and extract its mark value if explicitly given.
2) Detect implicit marking schemes. If the paper states a range with per-question marks and a total (e.g., "Q1–Q5: 2 marks each (total 10)"), assign the per-question marks accordingly.
3) Handle sub-parts. If a question has parts (e.g., Q1(a), Q1(b), or Q1a/Q1b), extract marks for each sub-part.
4) Be subject-agnostic; use only text/layout cues from the paper.
5) Do not hallucinate. If marks are unclear or not present, set them to null and add an entry in unknown_marks.

Output STRICT JSON only with this schema:
{
  "questions": [
    {
      "question_number": "Q1",
      "marks": 2,
      "subparts": [{"part": "a", "marks": 1}],
      "inferred_from_rule": false
    }
  ],
  "implicit_rules_detected": ["Q1–Q5: 2 marks each (total 10)"],
  "unknown_marks": ["Q12: marks not stated"],
  "total_questions_found": 0,
  "total_marks_inferred": 0
}

Rules:
- marks must be numeric or null
- subparts must be an array (empty if none)
- inferred_from_rule true only when derived from a stated rule
- Output valid JSON with no extra commentary.
"""

# --- REGRADING PROMPTS ---

# Used in llm/feedback_llm_service.py for student response re-evaluation
REGRADE_SYSTEM_PROMPT_v1 = "You are an expert grader."

REGRADE_USER_PROMPT_TEMPLATE_v1 = """# RE-GRADING TASK - Question {question_number}
## TEACHER'S CORRECTION GUIDANCE
{teacher_correction}
## QUESTION DETAILS
Question {question_number}: {rubric}
Maximum Marks: {max_marks}
## MODEL ANSWER REFERENCE
{model_answer_text}
## TASK
Re-grade ONLY Question {question_number} based on the teacher's correction guidance above.
## OUTPUT FORMAT
Return JSON:
{{
  "question_number": {question_number},
  "obtained_marks": <marks>,
  "ai_feedback": "<detailed feedback>",
  "sub_scores": []
}}
"""
# --- ANALYTICS & ERROR CATEGORIZATION PROMPTS ---

# Used in llm/grading_llm_service.py
CATEGORIZE_ERRORS_SYSTEM_PROMPT_v1 = "Identify common error patterns/categories from student feedback."

CATEGORIZE_ERRORS_USER_PROMPT_TEMPLATE_v1 = """Analyze these student errors for Question {question_number}:

Question: {question_rubric}
Max Marks: {max_marks}

Failed Student Feedbacks:
{feedback_samples}

Task: Identify 3-4 common error patterns/categories. For each category, provide:
1. Error type name (e.g., "Calculation Error", "Conceptual Misunderstanding", "Incomplete Answer")
2. Brief description
3. Which students fall into this category (by name)

Respond in JSON format:
{{
    "error_categories": [
        {{
            "type": "Calculation Error",
            "description": "Made arithmetic mistakes",
            "student_names": ["Alice", "Bob"]
        }}
    ]
}}
"""

ANALYTICS_SYSTEM_PROMPT_v1 = "You are a helpful educational analytics assistant. Provide a clear, concise answer based on the data. If you need specific data that isn't available, say so."

ANALYTICS_USER_PROMPT_TEMPLATE_v1 = """You are an AI analytics assistant for a teacher. Answer this question based on the data:

{data_summary}

Question: {query}
"""

# --- LEGACY PROMPT TEMPLATES ---

# From grading/constants.py
LEGACY_GRADING_PROMPT_v1 = """
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
"score": 5.0,
"feedback": "brief overall summary",
"strengths": "what the student did well",
"weaknesses": "what was missing or wrong",
"suggestions": "how to improve",
"detailed_explanation": "justification of the feedback"
}}

Do not include any additional text outside the JSON.
"""
