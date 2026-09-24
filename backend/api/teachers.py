from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

from backend.services import teacher_service

router = APIRouter(prefix="/teachers", tags=["Teachers"])


# Pydantic Schemas for Request & Response Validation
class TeacherCreate(BaseModel):
    name: str
    email: Optional[str] = None


class TeacherResponse(BaseModel):
    teacher_id: int
    name: str
    email: Optional[str] = None


@router.get("", response_model=List[TeacherResponse], status_code=status.HTTP_200_OK)
def get_all_teachers_endpoint():
    """
    Retrieve all teacher records from the database.
    """
    return teacher_service.get_all_teachers()


@router.get("/{teacher_id}", response_model=TeacherResponse, status_code=status.HTTP_200_OK)
def get_teacher_endpoint(teacher_id: int):
    """
    Retrieve a teacher record by teacher_id.
    """
    teacher = teacher_service.get_teacher_by_id(teacher_id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Teacher with ID {teacher_id} not found."
        )
    return teacher


@router.post("", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher_endpoint(teacher_data: TeacherCreate):
    """
    Add a new teacher to the system.
    """
    teacher_id = teacher_service.add_teacher(
        name=teacher_data.name,
        email=teacher_data.email
    )
    if not teacher_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create teacher. Check if email already exists."
        )

    created_teacher = teacher_service.get_teacher_by_id(teacher_id)
    return created_teacher
