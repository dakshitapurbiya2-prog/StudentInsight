import sys
import os
import sqlite3

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def get_all_departments_overview():
    """
    1. Returns a list of all departments with student and class counts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            d.department_id,
            d.name AS department_name,
            COUNT(DISTINCT c.class_id) AS total_classes,
            COUNT(DISTINCT s.student_id) AS total_students
        FROM departments d
        LEFT JOIN classes c ON d.department_id = c.department_id
        LEFT JOIN students s ON c.class_id = s.class_id
        GROUP BY d.department_id
        ORDER BY d.department_id;
        """
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "department_id": row[0],
            "department_name": row[1],
            "total_classes": row[2],
            "total_students": row[3]
        })
    return result


def get_all_classes_overview():
    """
    2. Returns a list of all classes with department name and student count.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            c.class_id,
            c.class_name,
            d.department_id,
            d.name AS department_name,
            COUNT(s.student_id) AS student_count
        FROM classes c
        JOIN departments d ON c.department_id = d.department_id
        LEFT JOIN students s ON c.class_id = s.class_id
        GROUP BY c.class_id
        ORDER BY c.class_id;
        """
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "class_id": row[0],
            "class_name": row[1],
            "department_id": row[2],
            "department_name": row[3],
            "student_count": row[4]
        })
    return result


def get_class_student_count(class_id: int):
    """
    3. Returns the student count for a specific class.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            c.class_id,
            c.class_name,
            COUNT(s.student_id) AS student_count
        FROM classes c
        LEFT JOIN students s ON c.class_id = s.class_id
        WHERE c.class_id = ?
        GROUP BY c.class_id;
        """,
        (class_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "class_id": row[0],
        "class_name": row[1],
        "student_count": row[2]
    }


def get_class_average_percentage(class_id: int):
    """
    4. Computes the overall average percentage for all students in a class across all evaluations.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            c.class_id,
            c.class_name,
            SUM(m.marks_obtained) AS total_obtained,
            SUM(m.max_marks) AS total_max,
            COUNT(DISTINCT s.student_id) AS total_students_evaluated
        FROM classes c
        JOIN students s ON c.class_id = s.class_id
        JOIN marks m ON s.student_id = m.student_id
        WHERE c.class_id = ?
        GROUP BY c.class_id;
        """,
        (class_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row[3] or row[3] == 0:
        return {
            "class_id": class_id,
            "class_name": "Unknown",
            "class_average_percentage": 0.0,
            "total_students_evaluated": 0
        }

    total_obtained = row[2]
    total_max = row[3]
    class_pct = round((total_obtained / total_max) * 100, 2)

    return {
        "class_id": row[0],
        "class_name": row[1],
        "class_average_percentage": class_pct,
        "total_students_evaluated": row[4]
    }


def get_subject_average_percentage(subject_id: int):
    """
    5. Computes the average percentage score for a subject across all students who took evaluations.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            sub.subject_id,
            sub.subject_name,
            c.class_name,
            t.name AS teacher_name,
            SUM(m.marks_obtained) AS total_obtained,
            SUM(m.max_marks) AS total_max,
            COUNT(m.mark_id) AS total_evaluations
        FROM subjects sub
        JOIN classes c ON sub.class_id = c.class_id
        LEFT JOIN teachers t ON sub.teacher_id = t.teacher_id
        JOIN marks m ON sub.subject_id = m.subject_id
        WHERE sub.subject_id = ?
        GROUP BY sub.subject_id;
        """,
        (subject_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row or not row[5] or row[5] == 0:
        return {
            "subject_id": subject_id,
            "subject_name": "Unknown",
            "subject_average_percentage": 0.0,
            "total_evaluations": 0
        }

    subject_pct = round((row[4] / row[5]) * 100, 2)

    return {
        "subject_id": row[0],
        "subject_name": row[1],
        "class_name": row[2],
        "teacher_name": row[3] or "Unassigned",
        "subject_average_percentage": subject_pct,
        "total_evaluations": row[6]
    }


def get_exam_wise_class_performance(class_id: int):
    """
    6. Computes average class performance per exam.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            e.exam_id,
            e.exam_name,
            e.exam_date,
            SUM(m.marks_obtained) AS total_obtained,
            SUM(m.max_marks) AS total_max,
            COUNT(DISTINCT s.student_id) AS student_count
        FROM exams e
        JOIN marks m ON e.exam_id = m.exam_id
        JOIN students s ON m.student_id = s.student_id
        WHERE e.class_id = ? AND s.class_id = ?
        GROUP BY e.exam_id
        ORDER BY e.exam_id;
        """,
        (class_id, class_id)
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        exam_pct = round((row[3] / row[4]) * 100, 2) if row[4] > 0 else 0.0
        result.append({
            "exam_id": row[0],
            "exam_name": row[1],
            "exam_date": row[2],
            "class_average_percentage": exam_pct,
            "students_participated": row[5]
        })
    return result


def compare_class_performances_across_exams():
    """
    7. Compares performance across all classes for each exam.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            c.class_id,
            c.class_name,
            e.exam_id,
            e.exam_name,
            SUM(m.marks_obtained) AS total_obtained,
            SUM(m.max_marks) AS total_max
        FROM classes c
        JOIN exams e ON c.class_id = e.class_id
        JOIN marks m ON e.exam_id = m.exam_id
        GROUP BY c.class_id, e.exam_id
        ORDER BY e.exam_id, c.class_id;
        """
    )
    rows = cursor.fetchall()
    conn.close()

    grouped_comparison = {}
    for row in rows:
        class_name = row[1]
        exam_id = row[2]
        exam_name = row[3]
        total_obtained = row[4]
        total_max = row[5]
        pct = round((total_obtained / total_max) * 100, 2) if total_max > 0 else 0.0

        if exam_name not in grouped_comparison:
            grouped_comparison[exam_name] = {
                "exam_id": exam_id,
                "exam_name": exam_name,
                "classes": []
            }
        grouped_comparison[exam_name]["classes"].append({
            "class_name": class_name,
            "average_percentage": pct
        })

    return list(grouped_comparison.values())


def get_student_count_by_class():
    """
    8. Returns student count breakdown grouped by class.
    """
    return get_all_classes_overview()


def get_class_subject_performance(class_id: int):
    """
    9. Returns average score for each subject taught in a specific class.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            sub.subject_id,
            sub.subject_name,
            t.name AS teacher_name,
            SUM(m.marks_obtained) AS total_obtained,
            SUM(m.max_marks) AS total_max
        FROM subjects sub
        LEFT JOIN teachers t ON sub.teacher_id = t.teacher_id
        JOIN marks m ON sub.subject_id = m.subject_id
        WHERE sub.class_id = ?
        GROUP BY sub.subject_id
        ORDER BY sub.subject_id;
        """,
        (class_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    result = []
    for row in rows:
        pct = round((row[3] / row[4]) * 100, 2) if row[4] > 0 else 0.0
        result.append({
            "subject_id": row[0],
            "subject_name": row[1],
            "teacher_name": row[2] or "Unassigned",
            "subject_average_percentage": pct
        })
    return result


def get_director_dashboard_overview():
    """
    Combined Director Dashboard Overview Payload.
    """
    classes_overview = get_all_classes_overview()

    # Calculate college-wide average
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(marks_obtained), SUM(max_marks) FROM marks;")
    totals = cursor.fetchone()
    conn.close()

    college_avg = 0.0
    if totals and totals[1] and totals[1] > 0:
        college_avg = round((totals[0] / totals[1]) * 100, 2)

    class_performance_list = []
    for c in classes_overview:
        cid = c["class_id"]
        c_avg = get_class_average_percentage(cid)
        class_performance_list.append({
            "class_id": cid,
            "class_name": c["class_name"],
            "department_name": c["department_name"],
            "student_count": c["student_count"],
            "class_average_percentage": c_avg["class_average_percentage"]
        })

    return {
        "college_overall_average": college_avg,
        "departments": get_all_departments_overview(),
        "classes_performance": class_performance_list,
        "exam_comparison": compare_class_performances_across_exams()
    }
