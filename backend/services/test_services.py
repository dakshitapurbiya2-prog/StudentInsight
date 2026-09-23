import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.services.student_service import (
    add_student, get_student_by_id, get_student_by_roll_number,
    get_all_students, update_student, delete_student
)
from backend.services.teacher_service import (
    add_teacher, get_teacher_by_id, get_all_teachers, update_teacher, delete_teacher
)
from backend.services.subject_service import (
    add_subject, get_subject_by_id, get_all_subjects, update_subject, delete_subject
)
from backend.services.exam_service import (
    add_exam, get_exam_by_id, get_all_exams, update_exam, delete_exam
)
from backend.services.marks_service import (
    add_marks, get_marks_by_student, get_marks_by_exam,
    get_marks_by_subject, update_marks, delete_marks
)


def test_crud_services():
    print("Testing CRUD Services for StudentInsight...")
    print("=" * 50)

    # 1. Test Teacher Service
    t_id = add_teacher("Dr. Gupta", "gupta@college.edu")
    print(f"[Teacher CRUD] Added teacher ID: {t_id}")
    t = get_teacher_by_id(t_id)
    assert t["name"] == "Dr. Gupta"
    update_teacher(t_id, "Dr. A. K. Gupta", "akgupta@college.edu")
    t_updated = get_teacher_by_id(t_id)
    assert t_updated["name"] == "Dr. A. K. Gupta"

    # 2. Test Student Service
    s_id = add_student("999", "Test Student", 1)
    print(f"[Student CRUD] Added student ID: {s_id}")
    s = get_student_by_id(s_id)
    assert s["name"] == "Test Student"
    s_roll = get_student_by_roll_number("999")
    assert s_roll["student_id"] == s_id
    update_student(s_id, "999", "Test Student Updated", 1)
    assert get_student_by_id(s_id)["name"] == "Test Student Updated"

    # 3. Test Subject Service
    sub_id = add_subject("Test Subject", 1, t_id)
    print(f"[Subject CRUD] Added subject ID: {sub_id}")
    sub = get_subject_by_id(sub_id)
    assert sub["subject_name"] == "Test Subject"
    update_subject(sub_id, "Test Subject Advanced", 1, t_id)
    assert get_subject_by_id(sub_id)["subject_name"] == "Test Subject Advanced"

    # 4. Test Exam Service
    e_id = add_exam("Test Exam", 1, "2026-12-01")
    print(f"[Exam CRUD] Added exam ID: {e_id}")
    e = get_exam_by_id(e_id)
    assert e["exam_name"] == "Test Exam"
    update_exam(e_id, "Test Exam Final", 1, "2026-12-05")
    assert get_exam_by_id(e_id)["exam_name"] == "Test Exam Final"

    # 5. Test Marks Service
    m_id = add_marks(s_id, sub_id, e_id, 88.5, 100.0)
    print(f"[Marks CRUD] Added mark ID: {m_id}")
    student_marks = get_marks_by_student(s_id)
    assert len(student_marks) > 0
    update_marks(m_id, 92.0, 100.0)
    assert get_marks_by_student(s_id)[-1]["marks_obtained"] == 92.0

    # Cleanup temporary test items
    delete_marks(m_id)
    delete_exam(e_id)
    delete_subject(sub_id)
    delete_student(s_id)
    delete_teacher(t_id)

    print("=" * 50)
    print("SUCCESS: All CRUD services tested and verified successfully!")


if __name__ == "__main__":
    test_crud_services()
