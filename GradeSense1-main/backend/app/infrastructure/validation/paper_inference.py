"""Paper inference logic for specific exam types."""

from typing import Optional

def infer_upsc_paper(exam_name: str = None, subject_name: str = None) -> Optional[str]:
    """
    Infer UPSC paper type from exam/subject name.
    
    TODO: Move these hardcoded checks to a configuration file in the future.
    """
    text = f"{exam_name or ''} {subject_name or ''}".lower()
    
    # Hardcoded checks for UPSC paper types
    if "essay" in text:
        return "Essay"
    if "gs1" in text or "gs-1" in text or "gs 1" in text or "general studies 1" in text:
        return "GS-1"
    if "gs2" in text or "gs-2" in text or "gs 2" in text or "general studies 2" in text:
        return "GS-2"
    if "gs3" in text or "gs-3" in text or "gs 3" in text or "general studies 3" in text:
        return "GS-3"
    if "gs4" in text or "gs-4" in text or "gs 4" in text or "general studies 4" in text or "ethics" in text:
        return "GS-4"
        
    return None
