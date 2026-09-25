from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any

from backend.services import director_analytics_service

router = APIRouter(prefix="/analytics/director", tags=["Head/Director Analytics"])


@router.get("/departments", status_code=status.HTTP_200_OK)
def get_departments_overview_endpoint():
    """
    1. Retrieve a list of all departments with student and class totals.
    """
    return director_analytics_service.get_all_departments_overview()


@router.get("/classes", status_code=status.HTTP_200_OK)
def get_classes_overview_endpoint():
    """
    2. Retrieve a list of all classes with department details and student count.
    """
    return director_analytics_service.get_all_classes_overview()


@router.get("/class/{class_id}/students-count", status_code=status.HTTP_200_OK)
def get_class_student_count_endpoint(class_id: int):
    """
    3. Retrieve the total number of students enrolled in a specific class.
    """
    result = director_analytics_service.get_class_student_count(class_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Class with ID {class_id} not found."
        )
    return result


@router.get("/class/{class_id}/average", status_code=status.HTTP_200_OK)
def get_class_average_endpoint(class_id: int):
    """
    4. Retrieve overall average percentage for all students in a class across evaluations.
    """
    return director_analytics_service.get_class_average_percentage(class_id)


@router.get("/subject/{subject_id}/average", status_code=status.HTTP_200_OK)
def get_subject_average_endpoint(subject_id: int):
    """
    5. Retrieve average percentage score achieved in a subject across all students.
    """
    return director_analytics_service.get_subject_average_percentage(subject_id)


@router.get("/class/{class_id}/exams-performance", status_code=status.HTTP_200_OK)
def get_exam_wise_class_performance_endpoint(class_id: int):
    """
    6. Retrieve exam-wise performance percentage breakdown for a class.
    """
    return director_analytics_service.get_exam_wise_class_performance(class_id)


@router.get("/exams/comparison", status_code=status.HTTP_200_OK)
def compare_class_performances_across_exams_endpoint():
    """
    7. Retrieve a comparative performance breakdown of all classes across exams.
    """
    return director_analytics_service.compare_class_performances_across_exams()


@router.get("/students-count-by-class", status_code=status.HTTP_200_OK)
def get_student_count_by_class_endpoint():
    """
    8. Retrieve student count breakdown across all classes.
    """
    return director_analytics_service.get_student_count_by_class()


@router.get("/class/{class_id}/subjects-performance", status_code=status.HTTP_200_OK)
def get_class_subject_performance_endpoint(class_id: int):
    """
    9. Retrieve performance breakdown for all subjects taught in a specific class.
    """
    return director_analytics_service.get_class_subject_performance(class_id)


@router.get("/dashboard", status_code=status.HTTP_200_OK)
def get_director_dashboard_endpoint():
    """
    Combined Head/Director Dashboard API: Returns college overall average, department summaries,
    class performance breakdown, and exam comparison in a single optimized response payload.
    """
    return director_analytics_service.get_director_dashboard_overview()
