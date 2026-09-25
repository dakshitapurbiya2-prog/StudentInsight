from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

from backend.services import exam_service

router = APIRouter(prefix="/exams", tags=["Exams"])


# Pydantic Schemas for Request & Response Validation
class ExamCreate(BaseModel):
    exam_name: str
    class_id: int
    exam_date: Optional[str] = None


class ExamResponse(BaseModel):
    exam_id: int
    exam_name: str
    class_id: int
    exam_date: Optional[str] = None


@router.get("", response_model=List[ExamResponse], status_code=status.HTTP_200_OK)
def get_all_exams_endpoint():
    """
    Retrieve all exam records from the database.
    """
    return exam_service.get_all_exams()


@router.get("/{exam_id}", response_model=ExamResponse, status_code=status.HTTP_200_OK)
def get_exam_endpoint(exam_id: int):
    """
    Retrieve an exam record by exam_id.
    """
    exam = exam_service.get_exam_by_id(exam_id)
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Exam with ID {exam_id} not found."
        )
    return exam


@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
def create_exam_endpoint(exam_data: ExamCreate):
    """
    Schedule a new exam for a class.
    """
    exam_id = exam_service.add_exam(
        exam_name=exam_data.exam_name,
        class_id=exam_data.class_id,
        exam_date=exam_data.exam_date
    )
    if not exam_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create exam. Verify class_id exists."
        )

    created_exam = exam_service.get_exam_by_id(exam_id)
    return created_exam
