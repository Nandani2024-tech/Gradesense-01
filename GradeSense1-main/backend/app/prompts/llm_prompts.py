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
