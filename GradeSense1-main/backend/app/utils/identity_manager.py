import re
import unicodedata

class UIDCollisionError(Exception):
    """Raised when identically numbered questions appear in the same section, causing UID collision."""
    pass

def normalize_section(section: str) -> str:
    """
    Standardizes section names: lowercase, remove special characters, 
    replace spaces and hyphens with underscores.
    """
    if not section:
        return "default"
    
    # Normalize unicode (to handle accented chars if any)
    text = unicodedata.normalize('NFKD', str(section)).encode('ascii', 'ignore').decode('ascii')
    
    # Lowercase
    text = text.lower()
    
    # Replace special characters with space, then collapse spaces to underscores
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '_', text).strip('_')
    
    return text or "default"

def build_question_uid(section: str, number: int) -> str:
    """
    Generates a globally unique identifier for a question within an exam.
    Format: {section_slug}_q{number}
    """
    section_slug = normalize_section(section)
    return f"{section_slug}_q{number}"
