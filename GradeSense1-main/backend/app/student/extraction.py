import uuid
import asyncio
import json
from typing import List

from app.core.logging_config import logger
from app.services.llm.config import get_llm_api_key, GEMINI_MODEL_NAME
from app.adapters.llm_adapter import GeminiLLMService


async def extract_student_info_from_paper(file_images: List[str], filename: str) -> tuple:
    """
    Extract student ID/roll number and name from the answer paper using AI
    Returns: (student_id, student_name) or (None, None) if extraction fails
    """
    api_key = get_llm_api_key()
    if not api_key:
        return (None, None)
    
    try:
        # Create Gemini model with system prompt
        system_prompt = """You are an expert at reading handwritten and printed student information from exam papers.

Extract the student's Roll Number/ID and Name from the answer sheet.

Return ONLY a JSON object in this exact format:
{
  "student_id": "the roll number or student ID (can be numbers or alphanumeric)",
  "student_name": "the student's full name"
}

Important:
- Student ID can be just numbers (e.g., "123", "2024001") or alphanumeric (e.g., "STU001", "CS-2024-001")
- Look for labels like "Roll No", "Roll Number", "Student ID", "ID No", "Reg No", "ID", etc.
- Student name is usually written at the top of the page near ID
- If you cannot find either field, use null
- Do NOT include any explanation, ONLY return the JSON"""

        llm_service = GeminiLLMService(api_key=api_key)
        
        # Use first page only (usually has student info)
        prompt_text = "Extract the student ID/roll number and name from this answer sheet."
        full_prompt = f"{system_prompt}\n\n{prompt_text}"
        
        logger.info("LLM_CALL provider=gemini model=%s images=1 prompt_len=%s", GEMINI_MODEL_NAME, len(full_prompt))

        # Make API call with timeout
        response_text = await asyncio.wait_for(
            llm_service.predict(
                prompt=full_prompt,
                images=[file_images[0]],
                model_name=GEMINI_MODEL_NAME,
                temperature=0
            ),
            timeout=120.0
        )
        response_text = (response_text or "").strip()
        
        # Parse JSON response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        
        student_id = result.get("student_id")
        student_name = result.get("student_name")
        
        # Basic validation
        if student_id and student_name:
            # Clean up
            student_id = str(student_id).strip()
            student_name = str(student_name).strip().title()
            
            # Validate student ID is not too short or too long
            if 1 <= len(student_id) <= 30 and len(student_name) >= 2:
                return (student_id, student_name)
        
        return (None, None)
        
    except Exception as e:
        logger.error(f"Error extracting student info from paper: {e}")
        return (None, None)
