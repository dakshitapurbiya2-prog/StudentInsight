from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List

from backend.services import student_service

router = APIRouter(prefix="/students", tags=["Students"])


# Pydantic Schemas for Request & Response Validation
class StudentCreate(BaseModel):
    roll_number: str
    name: str
    class_id: int


class StudentUpdate(BaseModel):
    roll_number: str
    name: str
    class_id: int


class StudentResponse(BaseModel):
    student_id: int
    roll_number: str
    name: str
    class_id: int


@router.get("", response_model=List[StudentResponse], status_code=status.HTTP_200_OK)
def get_all_students_endpoint():
    """
    Retrieve all student records from the database.
    """
    return student_service.get_all_students()


@router.get("/{student_id}", response_model=StudentResponse, status_code=status.HTTP_200_OK)
def get_student_endpoint(student_id: int):
    """
    Retrieve a single student record by student_id.
    """
    student = student_service.get_student_by_id(student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return student


@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student_endpoint(student_data: StudentCreate):
    """
    Register a new student in the system.
    """
    student_id = student_service.add_student(
        roll_number=student_data.roll_number,
        name=student_data.name,
        class_id=student_data.class_id
    )
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create student. Check if roll_number already exists or class_id is valid."
        )

    created_student = student_service.get_student_by_id(student_id)
    return created_student


@router.put("/{student_id}", response_model=StudentResponse, status_code=status.HTTP_200_OK)
def update_student_endpoint(student_id: int, student_data: StudentUpdate):
    """
    Update an existing student's details by student_id.
    """
    success = student_service.update_student(
        student_id=student_id,
        roll_number=student_data.roll_number,
        name=student_data.name,
        class_id=student_data.class_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found or update failed."
        )

    updated_student = student_service.get_student_by_id(student_id)
    return updated_student


@router.delete("/{student_id}", status_code=status.HTTP_200_OK)
def delete_student_endpoint(student_id: int):
    """
    Delete a student record by student_id.
    """
    success = student_service.delete_student(student_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return {"message": f"Student with ID {student_id} successfully deleted."}
