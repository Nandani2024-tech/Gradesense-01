import uuid
from datetime import datetime, timezone

from app.core.database import db
from app.core.logging_config import logger


async def get_or_create_student(
    student_id: str,
    student_name: str,
    batch_id: str,
    teacher_id: str
) -> tuple:
    """
    Get existing student or create new one
    Returns: (user_id, error_message)
    """
    # Check if student ID already exists
    existing = await db.users.find_one({"student_id": student_id, "role": "student"}, {"_id": 0})
    
    if existing:
        # Student exists - use existing student (allow re-grading)
        user_id = existing["user_id"]
        
        # Optionally update name if different (use the new one)
        if existing["name"].lower() != student_name.lower():
            # Log the name difference but don't treat as error - just use existing student
            logger.info(f"Student ID {student_id}: name '{student_name}' differs from existing '{existing['name']}', using existing student")
        
        # Add to batch if not already there
        if batch_id not in existing.get("batches", []):
            await db.users.update_one(
                {"user_id": user_id},
                {"$addToSet": {"batches": batch_id}}
            )
            # Also add student to batch document
            await db.batches.update_one(
                {"batch_id": batch_id},
                {"$addToSet": {"students": user_id}}
            )
        
        return (user_id, None)
    
    # Create new student
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    new_student = {
        "user_id": user_id,
        "email": f"{student_id.lower()}@school.temp",  # Temporary email
        "name": student_name,
        "role": "student",
        "student_id": student_id,
        "batches": [batch_id],
        "teacher_id": teacher_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(new_student)
    
    # Add student to batch document
    await db.batches.update_one(
        {"batch_id": batch_id},
        {"$addToSet": {"students": user_id}}
    )
    
    return (user_id, None)
