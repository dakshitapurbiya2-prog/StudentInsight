import sys
import os
import sqlite3

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def process_marks_import(imported_records, exam_id, max_marks=100.0):
    """
    Processes structured marks data (e.g. parsed from PDF/CSV), performs multi-step
    validation, and saves valid records to the database.

    Validation rules:
    1. Check that exam_id exists in the database.
    2. Check missing or invalid record fields (roll_number, subject, numeric marks).
    3. Check that marks are between 0 and max_marks.
    4. Check that student roll_number exists.
    5. Check that subject exists for the student's class.
    """
    conn = get_connection()
    cursor = conn.cursor()

    result_summary = {
        "total_records": len(imported_records),
        "saved_records": 0,
        "failed_records": 0,
        "saved": [],
        "errors": []
    }

    # 1. Validate Exam Existence
    cursor.execute("SELECT class_id, exam_name FROM exams WHERE exam_id = ?;", (exam_id,))
    exam_row = cursor.fetchone()
    if not exam_row:
        conn.close()
        result_summary["failed_records"] = len(imported_records)
        result_summary["errors"].append({
            "record": None,
            "reason": f"Exam with ID {exam_id} does not exist in the database."
        })
        return result_summary

    exam_class_id = exam_row[0]

    # Process each record individually
    for record in imported_records:
        # 2. Check for missing structure or invalid keys
        if not isinstance(record, dict):
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": "Invalid record format. Expected a JSON object."
            })
            continue

        roll_number = str(record.get("roll_number", "")).strip()
        subject_name = str(record.get("subject", "")).strip()
        marks_value = record.get("marks")

        # Check required fields presence
        if not roll_number or not subject_name or marks_value is None:
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": "Missing required fields: roll_number, subject, or marks."
            })
            continue

        # 3. Check numeric marks validity
        try:
            marks = float(marks_value)
        except (ValueError, TypeError):
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Invalid marks value '{marks_value}'. Must be a valid number."
            })
            continue

        # Check bounds: non-negative and <= max_marks
        if marks < 0:
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Marks ({marks}) cannot be negative."
            })
            continue

        if marks > max_marks:
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Marks ({marks}) exceed maximum allowed marks ({max_marks})."
            })
            continue

        # 4. Check Student Existence by Roll Number
        cursor.execute(
            "SELECT student_id, name, class_id FROM students WHERE roll_number = ?;",
            (roll_number,)
        )
        student_row = cursor.fetchone()
        if not student_row:
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Student with roll number '{roll_number}' not found."
            })
            continue

        student_id, student_name, student_class_id = student_row

        # 5. Check Subject Existence for Student's Class
        cursor.execute(
            """
            SELECT subject_id FROM subjects 
            WHERE LOWER(subject_name) = LOWER(?) AND class_id = ?;
            """,
            (subject_name, student_class_id)
        )
        subject_row = cursor.fetchone()
        if not subject_row:
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Subject '{subject_name}' not found for student's class."
            })
            continue

        subject_id = subject_row[0]

        # 6. Save or Update Mark Record in Database
        try:
            cursor.execute(
                """
                SELECT mark_id FROM marks 
                WHERE student_id = ? AND subject_id = ? AND exam_id = ?;
                """,
                (student_id, subject_id, exam_id)
            )
            existing_mark = cursor.fetchone()

            if existing_mark:
                mark_id = existing_mark[0]
                cursor.execute(
                    """
                    UPDATE marks 
                    SET marks_obtained = ?, max_marks = ? 
                    WHERE mark_id = ?;
                    """,
                    (marks, max_marks, mark_id)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO marks (student_id, subject_id, exam_id, marks_obtained, max_marks)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (student_id, subject_id, exam_id, marks, max_marks)
                )
                mark_id = cursor.lastrowid

            conn.commit()

            result_summary["saved_records"] += 1
            result_summary["saved"].append({
                "mark_id": mark_id,
                "student_id": student_id,
                "roll_number": roll_number,
                "student_name": student_name,
                "subject": subject_name,
                "marks_obtained": marks,
                "max_marks": max_marks
            })
        except sqlite3.Error as e:
            conn.rollback()
            result_summary["failed_records"] += 1
            result_summary["errors"].append({
                "record": record,
                "reason": f"Database insertion error: {e}"
            })

    conn.close()
    return result_summary
