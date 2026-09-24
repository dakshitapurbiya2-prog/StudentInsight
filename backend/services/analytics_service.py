import sys
import os
import sqlite3

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def get_student_profile(student_id: int):
    """
    1. Retrieves full student profile including department and class details.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            s.student_id,
            s.roll_number,
            s.name AS student_name,
            c.class_id,
            c.class_name,
            d.department_id,
            d.name AS department_name
        FROM students s
        JOIN classes c ON s.class_id = c.class_id
        JOIN departments d ON c.department_id = d.department_id
        WHERE s.student_id = ?;
        """,
        (student_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "student_id": row[0],
        "roll_number": row[1],
        "name": row[2],
        "class_id": row[3],
        "class_name": row[4],
        "department_id": row[5],
        "department_name": row[6]
    }


def get_all_student_marks(student_id: int):
    """
    2. Retrieves all detailed marks records of a student with subject, exam, and teacher info.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            m.mark_id,
            sub.subject_id,
            sub.subject_name,
            t.name AS teacher_name,
            e.exam_id,
            e.exam_name,
            e.exam_date,
            m.marks_obtained,
            m.max_marks,
            ROUND((m.marks_obtained / m.max_marks) * 100, 2) AS percentage
        FROM marks m
        JOIN subjects sub ON m.subject_id = sub.subject_id
        LEFT JOIN teachers t ON sub.teacher_id = t.teacher_id
        JOIN exams e ON m.exam_id = e.exam_id
        WHERE m.student_id = ?
        ORDER BY e.exam_id, sub.subject_id;
        """,
        (student_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    marks_list = []
    for row in rows:
        marks_list.append({
            "mark_id": row[0],
            "subject_id": row[1],
            "subject_name": row[2],
            "teacher_name": row[3] or "Unassigned",
            "exam_id": row[4],
            "exam_name": row[5],
            "exam_date": row[6],
            "marks_obtained": row[7],
            "max_marks": row[8],
            "percentage": row[9]
        })
    return marks_list


def get_marks_grouped_by_exam(student_id: int):
    """
    3. Groups student's marks by exam with exam averages.
    """
    all_marks = get_all_student_marks(student_id)
    grouped = {}

    for item in all_marks:
        exam_id = item["exam_id"]
        exam_name = item["exam_name"]
        if exam_id not in grouped:
            grouped[exam_id] = {
                "exam_id": exam_id,
                "exam_name": exam_name,
                "exam_date": item["exam_date"],
                "subjects": [],
                "total_obtained": 0.0,
                "total_max": 0.0
            }
        grouped[exam_id]["subjects"].append({
            "subject_id": item["subject_id"],
            "subject_name": item["subject_name"],
            "marks_obtained": item["marks_obtained"],
            "max_marks": item["max_marks"],
            "percentage": item["percentage"]
        })
        grouped[exam_id]["total_obtained"] += item["marks_obtained"]
        grouped[exam_id]["total_max"] += item["max_marks"]

    result = []
    for exam_id, data in grouped.items():
        exam_pct = round((data["total_obtained"] / data["total_max"]) * 100, 2) if data["total_max"] > 0 else 0.0
        result.append({
            "exam_id": data["exam_id"],
            "exam_name": data["exam_name"],
            "exam_date": data["exam_date"],
            "exam_average_percentage": exam_pct,
            "subjects": data["subjects"]
        })
    return result


def get_marks_grouped_by_subject(student_id: int):
    """
    4. Groups student's marks by subject with subject overall averages.
    """
    all_marks = get_all_student_marks(student_id)
    grouped = {}

    for item in all_marks:
        sub_id = item["subject_id"]
        sub_name = item["subject_name"]
        if sub_id not in grouped:
            grouped[sub_id] = {
                "subject_id": sub_id,
                "subject_name": sub_name,
                "teacher_name": item["teacher_name"],
                "exams": [],
                "total_obtained": 0.0,
                "total_max": 0.0
            }
        grouped[sub_id]["exams"].append({
            "exam_id": item["exam_id"],
            "exam_name": item["exam_name"],
            "marks_obtained": item["marks_obtained"],
            "max_marks": item["max_marks"],
            "percentage": item["percentage"]
        })
        grouped[sub_id]["total_obtained"] += item["marks_obtained"]
        grouped[sub_id]["total_max"] += item["max_marks"]

    result = []
    for sub_id, data in grouped.items():
        sub_pct = round((data["total_obtained"] / data["total_max"]) * 100, 2) if data["total_max"] > 0 else 0.0
        result.append({
            "subject_id": data["subject_id"],
            "subject_name": data["subject_name"],
            "teacher_name": data["teacher_name"],
            "subject_average_percentage": sub_pct,
            "exams": data["exams"]
        })
    return result


def get_student_average_percentage(student_id: int):
    """
    5. Calculates student's overall average percentage across all evaluations.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            SUM(marks_obtained) AS total_obtained,
            SUM(max_marks) AS total_max,
            COUNT(*) AS total_evaluations
        FROM marks
        WHERE student_id = ?;
        """,
        (student_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row[1] or row[1] == 0:
        return {
            "student_id": student_id,
            "overall_percentage": 0.0,
            "total_evaluations": 0,
            "performance_grade": "N/A"
        }

    total_obtained = row[0]
    total_max = row[1]
    total_evaluations = row[2]
    overall_percentage = round((total_obtained / total_max) * 100, 2)

    # Determine qualitative performance band
    if overall_percentage >= 85:
        grade = "Excellent"
    elif overall_percentage >= 75:
        grade = "Very Good"
    elif overall_percentage >= 60:
        grade = "Good"
    elif overall_percentage >= 50:
        grade = "Average"
    else:
        grade = "Needs Improvement"

    return {
        "student_id": student_id,
        "overall_percentage": overall_percentage,
        "total_evaluations": total_evaluations,
        "performance_grade": grade
    }


def get_subject_wise_percentage(student_id: int):
    """
    6. Calculates subject-wise percentage for a student.
    """
    grouped_subjects = get_marks_grouped_by_subject(student_id)
    return [
        {
            "subject_id": item["subject_id"],
            "subject_name": item["subject_name"],
            "teacher_name": item["teacher_name"],
            "percentage": item["subject_average_percentage"]
        }
        for item in grouped_subjects
    ]


def get_exam_wise_percentage(student_id: int):
    """
    7. Calculates exam-wise percentage for a student.
    """
    grouped_exams = get_marks_grouped_by_exam(student_id)
    return [
        {
            "exam_id": item["exam_id"],
            "exam_name": item["exam_name"],
            "exam_date": item["exam_date"],
            "percentage": item["exam_average_percentage"]
        }
        for item in grouped_exams
    ]


def get_exam_progress(student_id: int):
    """
    8. Calculates chronological progress across exams (e.g. Unit Test 1 -> 68%, Midterm -> 74%, Unit Test 2 -> 79%).
    """
    exam_percentages = get_exam_wise_percentage(student_id)
    
    # Sort by exam_id (or date) to maintain chronological order
    sorted_progress = sorted(exam_percentages, key=lambda x: x["exam_id"])

    progress_summary = []
    previous_pct = None

    for idx, item in enumerate(sorted_progress):
        current_pct = item["percentage"]
        trend = "N/A"
        delta = 0.0

        if previous_pct is not None:
            delta = round(current_pct - previous_pct, 2)
            if delta > 0:
                trend = f"+{delta}% (Improving)"
            elif delta < 0:
                trend = f"{delta}% (Declining)"
            else:
                trend = "0.0% (Stable)"

        progress_summary.append({
            "step": idx + 1,
            "exam_id": item["exam_id"],
            "exam_name": item["exam_name"],
            "exam_date": item["exam_date"],
            "percentage": current_pct,
            "change_from_previous": delta,
            "trend": trend
        })
        previous_pct = current_pct

    return progress_summary
