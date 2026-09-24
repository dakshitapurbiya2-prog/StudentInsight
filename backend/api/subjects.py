from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

from backend.services import subject_service

router = APIRouter(prefix="/subjects", tags=["Subjects"])


# Pydantic Schemas for Request & Response Validation
class SubjectCreate(BaseModel):
    subject_name: str
    subject_code: Optional[str] = None    # e.g. "BT-101"
    class_id: int
    teacher_id: Optional[int] = None


class SubjectResponse(BaseModel):
    subject_id: int
    subject_name: str
    subject_code: Optional[str] = None
    class_id: int
    teacher_id: Optional[int] = None


@router.get("", response_model=List[SubjectResponse], status_code=status.HTTP_200_OK)
def get_all_subjects_endpoint():
    """
    Retrieve all subject records from the database.
    """
    return subject_service.get_all_subjects()


@router.get("/{subject_id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
def get_subject_endpoint(subject_id: int):
    """
    Retrieve a subject record by subject_id.
    """
    subject = subject_service.get_subject_by_id(subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with ID {subject_id} not found."
        )
    return subject


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject_endpoint(subject_data: SubjectCreate):
    """
    Add a new subject to a class curriculum.
    """
    subject_id = subject_service.add_subject(
        subject_name=subject_data.subject_name,
        subject_code=subject_data.subject_code,
        class_id=subject_data.class_id,
        teacher_id=subject_data.teacher_id
    )
    if not subject_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create subject. Verify class_id and teacher_id exist."
        )

    created_subject = subject_service.get_subject_by_id(subject_id)
    return created_subject
