"""Adapter for answer extraction from PDF."""

from typing import Dict, Any, List
from app.services.extraction_pipeline import extract_answers_from_pdf

async def extract_answers(pdf_bytes: bytes, questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wraps extract_answers_from_pdf."""
    return await extract_answers_from_pdf(pdf_bytes, questions)
