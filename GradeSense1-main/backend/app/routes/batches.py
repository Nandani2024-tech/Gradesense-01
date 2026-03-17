"""Batch routes."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.schemas.responses import (
    BatchBaseResponse, BatchDetailResponse, BatchStatsResponse,
    BatchStudentPerformance, MessageResponse
)

from app.deps import get_current_user
from app.models.user import User
from app.models.batch import BatchCreate
from app.services.batches.batch_service import batch_service

router = APIRouter(tags=["batches"])


@router.get("/batches", response_model=List[BatchBaseResponse])
async def get_batches(user: User = Depends(get_current_user)) -> List[BatchBaseResponse]:
    """Get all batches for current user"""
    batches = await batch_service.get_batches(user)
    return [BatchBaseResponse(**b) for b in batches]


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
async def get_batch(batch_id: str, user: User = Depends(get_current_user)) -> BatchDetailResponse:
    """Get batch details with students"""
    batch = await batch_service.get_batch(batch_id, user)
    return BatchDetailResponse(**batch)


@router.post("/batches", response_model=BatchBaseResponse)
async def create_batch(batch: BatchCreate, user: User = Depends(get_current_user)) -> BatchBaseResponse:
    """Create a new batch"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create batches")

    data = await batch_service.create_batch(batch.name, user.user_id)
    return BatchBaseResponse(**data)


@router.put("/batches/{batch_id}", response_model=MessageResponse)
async def update_batch(batch_id: str, batch: BatchCreate, user: User = Depends(get_current_user)) -> MessageResponse:
    """Update batch name"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update batches")

    await batch_service.update_batch(batch_id, batch.name, user.user_id)
    return MessageResponse(message="Batch updated")


@router.delete("/batches/{batch_id}", response_model=MessageResponse)
async def delete_batch(batch_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Delete a batch (only if empty)"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can delete batches")

    await batch_service.delete_batch(batch_id, user.user_id)
    return MessageResponse(message="Batch deleted")


@router.put("/batches/{batch_id}/close", response_model=MessageResponse)
async def close_batch(batch_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Close/archive a batch"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can close batches")

    await batch_service.set_batch_status(batch_id, "closed", user.user_id)
    return MessageResponse(message="Batch closed successfully")


@router.put("/batches/{batch_id}/reopen", response_model=MessageResponse)
async def reopen_batch(batch_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Reopen a closed batch"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can reopen batches")

    await batch_service.set_batch_status(batch_id, "active", user.user_id)
    return MessageResponse(message="Batch reopened successfully")


@router.post("/batches/{batch_id}/students", response_model=MessageResponse)
async def add_student_to_batch(batch_id: str, data: dict, user: User = Depends(get_current_user)) -> MessageResponse:
    """Add an existing student to a batch"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can manage batch students")

    student_id = data.get("student_id")
    if not student_id:
        raise HTTPException(status_code=400, detail="Student ID is required")

    await batch_service.add_student_to_batch(batch_id, student_id, user.user_id)
    return MessageResponse(message="Student added to batch successfully")


@router.delete("/batches/{batch_id}/students/{student_id}", response_model=MessageResponse)
async def remove_student_from_batch(batch_id: str, student_id: str, user: User = Depends(get_current_user)) -> MessageResponse:
    """Remove a student from a batch"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can manage batch students")

    await batch_service.remove_student_from_batch(batch_id, student_id, user.user_id)
    return MessageResponse(message="Student removed from batch successfully")


@router.get("/batches/{batch_id}/stats", response_model=BatchStatsResponse)
async def get_batch_stats(batch_id: str, user: User = Depends(get_current_user)) -> BatchStatsResponse:
    """Get batch statistics"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view batch stats")

    stats = await batch_service.get_batch_stats(batch_id, user.user_id)
    return BatchStatsResponse(**stats)


@router.get("/batches/{batch_id}/students", response_model=List[BatchStudentPerformance])
async def get_batch_students(batch_id: str, user: User = Depends(get_current_user)) -> List[BatchStudentPerformance]:
    """Get students in a batch with their performance"""
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can view batch students")

    students = await batch_service.get_batch_students_performance(batch_id, user.user_id)
    return [BatchStudentPerformance(**s) for s in students]
