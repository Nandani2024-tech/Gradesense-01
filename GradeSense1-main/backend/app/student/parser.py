from app.core.logging_config import logger


def parse_student_from_filename(filename: str) -> tuple:
    """
    Parse student ID and name from filename
    Expected formats: 
    - STU003_Sagar_Maths.pdf -> (STU003, Sagar)
    - 123_John_Doe.pdf -> (123, John Doe)
    - StudentName.pdf -> (None, StudentName)
    Returns: (student_id, student_name)
    """
    try:
        # Remove .pdf extension
        name_part = filename.replace(".pdf", "").replace(".PDF", "")
        
        # Common subject names to filter out
        subject_names = [
            'maths', 'math', 'mathematics', 'english', 'science', 'physics', 
            'chemistry', 'biology', 'history', 'geography', 'hindi', 'sanskrit',
            'social', 'economics', 'commerce', 'accounts', 'computer', 'it',
            'arts', 'music', 'pe', 'physical', 'education', 'exam', 'test'
        ]
        
        # Split by underscore or hyphen
        parts = name_part.replace("-", "_").split("_")
        
        if len(parts) >= 2:
            # First part is likely student ID
            potential_id = parts[0].strip()
            
            # Remaining parts form the name, excluding subject names
            name_parts = []
            for part in parts[1:]:
                if part.lower() not in subject_names:
                    name_parts.append(part)
            
            potential_name = " ".join(name_parts).strip().title()
            
            # Validate ID (should be alphanumeric, not too long)
            if potential_id and len(potential_id) <= 20:
                return (potential_id, potential_name if potential_name else None)
        
        # Fallback: try to clean up the filename as a name
        student_name = name_part.replace("_", " ").replace("-", " ").strip().title()
        
        if student_name and len(student_name) >= 2:
            return (None, student_name)
        
        return (None, None)
    except Exception as e:
        logger.error(f"Error parsing filename {filename}: {e}")
        return (None, None)
