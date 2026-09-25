from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Any, Dict, Optional, Union

from backend.services import marks_service
from backend.services import marks_import_service

router = APIRouter(prefix="/marks", tags=["Marks"])


# Pydantic Schemas for Request & Response Validation
class MarksCreate(BaseModel):
    student_id: int
    subject_id: int
    exam_id: int
    marks_obtained: float
    max_marks: float = 100.0


class MarksUpdate(BaseModel):
    marks_obtained: float
    max_marks: float = 100.0


class MarksResponse(BaseModel):
    mark_id: int
    student_id: int
    subject_id: int
    exam_id: int
    marks_obtained: float
    max_marks: float


# Schemas for Structured Marks Import (PDF Pipeline Integration)
class ExtractedMarkItem(BaseModel):
    roll_number: str
    subject: Optional[str] = None          # Subject full name e.g. "Mathematics"
    subject_code: Optional[str] = None     # Subject code e.g. "BT-101" (alternative to subject)
    marks: Union[float, str]               # Float value OR "ABS" for absent students


class MarksImportRequest(BaseModel):
    exam_id: int
    max_marks: float = 100.0
    records: List[ExtractedMarkItem]


@router.get("/student/{student_id}", response_model=List[MarksResponse], status_code=status.HTTP_200_OK)
def get_marks_by_student_endpoint(student_id: int):
    """
    Retrieve all marks evaluation records for a specific student.
    """
    return marks_service.get_marks_by_student(student_id)


@router.get("/exam/{exam_id}", response_model=List[MarksResponse], status_code=status.HTTP_200_OK)
def get_marks_by_exam_endpoint(exam_id: int):
    """
    Retrieve all marks evaluation records for a specific exam.
    """
    return marks_service.get_marks_by_exam(exam_id)


@router.get("/subject/{subject_id}", response_model=List[MarksResponse], status_code=status.HTTP_200_OK)
def get_marks_by_subject_endpoint(subject_id: int):
    """
    Retrieve all marks evaluation records for a specific subject.
    """
    return marks_service.get_marks_by_subject(subject_id)


@router.post("", response_model=MarksResponse, status_code=status.HTTP_201_CREATED)
def create_marks_endpoint(marks_data: MarksCreate):
    """
    Record a new evaluation score for a student.
    """
    mark_id = marks_service.add_marks(
        student_id=marks_data.student_id,
        subject_id=marks_data.subject_id,
        exam_id=marks_data.exam_id,
        marks_obtained=marks_data.marks_obtained,
        max_marks=marks_data.max_marks
    )
    if not mark_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not record marks. Verify student_id, subject_id, and exam_id exist."
        )

    # Fetch recorded mark to return in response
    student_marks = marks_service.get_marks_by_student(marks_data.student_id)
    recorded_mark = next((m for m in student_marks if m["mark_id"] == mark_id), None)
    if not recorded_mark:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Marks record created but could not be fetched."
        )
    return recorded_mark


@router.post("/import", status_code=status.HTTP_200_OK)
def import_structured_marks_endpoint(
    import_payload: MarksImportRequest,
    dry_run: bool = False
):
    """
    Accepts structured extracted marks data (e.g. from PDF processing pipeline),
    validates records against database rules, and saves valid entries.

    Query param:
    - dry_run=true  → Validates all records and returns what WOULD be saved/failed,
                       but does NOT write anything to the database. Safe for testing.
    - dry_run=false → (default) Validates and saves to database.
    """
    raw_records = [item.model_dump() for item in import_payload.records]
    result_summary = marks_import_service.process_marks_import(
        imported_records=raw_records,
        exam_id=import_payload.exam_id,
        max_marks=import_payload.max_marks,
        dry_run=dry_run
    )
    if dry_run:
        result_summary["dry_run"] = True
        result_summary["message"] = "Dry run complete. No data was saved to the database."
    return result_summary


@router.put("/{mark_id}", status_code=status.HTTP_200_OK)
def update_marks_endpoint(mark_id: int, marks_data: MarksUpdate):
    """
    Update marks_obtained or max_marks for an evaluation record by mark_id.
    """
    success = marks_service.update_marks(
        mark_id=mark_id,
        marks_obtained=marks_data.marks_obtained,
        max_marks=marks_data.max_marks
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marks record with ID {mark_id} not found."
        )
    return {"message": f"Marks record with ID {mark_id} successfully updated."}


@router.delete("/{mark_id}", status_code=status.HTTP_200_OK)
def delete_marks_endpoint(mark_id: int):
    """
    Delete a marks evaluation record by mark_id.
    """
    success = marks_service.delete_marks(mark_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marks record with ID {mark_id} not found."
        )
    return {"message": f"Marks record with ID {mark_id} successfully deleted."}
