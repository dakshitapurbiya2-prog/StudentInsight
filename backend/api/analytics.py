from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from backend.services import analytics_service

router = APIRouter(prefix="/analytics/student", tags=["Student Performance Analytics"])


@router.get("/{student_id}/profile", status_code=status.HTTP_200_OK)
def get_student_profile_endpoint(student_id: int):
    """
    1. Retrieve full student profile (Name, Roll Number, Class, Department).
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student profile for ID {student_id} not found."
        )
    return profile


@router.get("/{student_id}/marks", status_code=status.HTTP_200_OK)
def get_all_student_marks_endpoint(student_id: int):
    """
    2. Retrieve all marks records of a student with subject, teacher, and exam details.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_all_student_marks(student_id)


@router.get("/{student_id}/marks/by-exam", status_code=status.HTTP_200_OK)
def get_marks_grouped_by_exam_endpoint(student_id: int):
    """
    3. Retrieve all marks for a student grouped by Exam.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_marks_grouped_by_exam(student_id)


@router.get("/{student_id}/marks/by-subject", status_code=status.HTTP_200_OK)
def get_marks_grouped_by_subject_endpoint(student_id: int):
    """
    4. Retrieve all marks for a student grouped by Subject.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_marks_grouped_by_subject(student_id)


@router.get("/{student_id}/average", status_code=status.HTTP_200_OK)
def get_student_average_endpoint(student_id: int):
    """
    5. Retrieve student's overall average percentage across all evaluations.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_student_average_percentage(student_id)


@router.get("/{student_id}/subjects-percentage", status_code=status.HTTP_200_OK)
def get_subject_percentages_endpoint(student_id: int):
    """
    6. Retrieve subject-wise performance percentage breakdown.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_subject_wise_percentage(student_id)


@router.get("/{student_id}/exams-percentage", status_code=status.HTTP_200_OK)
def get_exam_percentages_endpoint(student_id: int):
    """
    7. Retrieve exam-wise performance percentage breakdown.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_exam_wise_percentage(student_id)


@router.get("/{student_id}/progress", status_code=status.HTTP_200_OK)
def get_exam_progress_endpoint(student_id: int):
    """
    8. Retrieve chronological performance progress across exams (e.g. Unit Test 1 -> Midterm -> Unit Test 2).
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )
    return analytics_service.get_exam_progress(student_id)


@router.get("/{student_id}/dashboard", status_code=status.HTTP_200_OK)
def get_student_dashboard_endpoint(student_id: int):
    """
    Combined Dashboard API: Returns profile, overall average, subject breakdown, exam breakdown,
    and progress history in a single optimized payload for frontend analytics dashboards.
    """
    profile = analytics_service.get_student_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found."
        )

    return {
        "profile": profile,
        "overall_average": analytics_service.get_student_average_percentage(student_id),
        "subject_performance": analytics_service.get_subject_wise_percentage(student_id),
        "exam_performance": analytics_service.get_exam_wise_percentage(student_id),
        "exam_progress": analytics_service.get_exam_progress(student_id)
    }
