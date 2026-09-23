import sys
import os
import sqlite3

# Ensure project root is in sys.path for database module imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def add_marks(student_id, subject_id, exam_id, marks_obtained, max_marks=100.0):
    """
    Inserts a new marks evaluation record into the database.
    Returns the new mark_id on success, or None on failure.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO marks (student_id, subject_id, exam_id, marks_obtained, max_marks)
            VALUES (?, ?, ?, ?, ?);
            """,
            (student_id, subject_id, exam_id, marks_obtained, max_marks)
        )
        conn.commit()
        mark_id = cursor.lastrowid
        return mark_id
    except sqlite3.Error as e:
        print(f"Error adding marks: {e}")
        return None
    finally:
        conn.close()


def get_marks_by_student(student_id):
    """
    Retrieves all marks records for a specific student.
    Returns a list of marks dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT mark_id, student_id, subject_id, exam_id, marks_obtained, max_marks
            FROM marks
            WHERE student_id = ?
            ORDER BY mark_id;
            """,
            (student_id,)
        )
        rows = cursor.fetchall()
        marks_list = []
        for row in rows:
            marks_list.append({
                "mark_id": row[0],
                "student_id": row[1],
                "subject_id": row[2],
                "exam_id": row[3],
                "marks_obtained": row[4],
                "max_marks": row[5]
            })
        return marks_list
    except sqlite3.Error as e:
        print(f"Error retrieving marks by student ID: {e}")
        return []
    finally:
        conn.close()


def get_marks_by_exam(exam_id):
    """
    Retrieves all marks records for a specific exam.
    Returns a list of marks dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT mark_id, student_id, subject_id, exam_id, marks_obtained, max_marks
            FROM marks
            WHERE exam_id = ?
            ORDER BY mark_id;
            """,
            (exam_id,)
        )
        rows = cursor.fetchall()
        marks_list = []
        for row in rows:
            marks_list.append({
                "mark_id": row[0],
                "student_id": row[1],
                "subject_id": row[2],
                "exam_id": row[3],
                "marks_obtained": row[4],
                "max_marks": row[5]
            })
        return marks_list
    except sqlite3.Error as e:
        print(f"Error retrieving marks by exam ID: {e}")
        return []
    finally:
        conn.close()


def get_marks_by_subject(subject_id):
    """
    Retrieves all marks records for a specific subject.
    Returns a list of marks dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT mark_id, student_id, subject_id, exam_id, marks_obtained, max_marks
            FROM marks
            WHERE subject_id = ?
            ORDER BY mark_id;
            """,
            (subject_id,)
        )
        rows = cursor.fetchall()
        marks_list = []
        for row in rows:
            marks_list.append({
                "mark_id": row[0],
                "student_id": row[1],
                "subject_id": row[2],
                "exam_id": row[3],
                "marks_obtained": row[4],
                "max_marks": row[5]
            })
        return marks_list
    except sqlite3.Error as e:
        print(f"Error retrieving marks by subject ID: {e}")
        return []
    finally:
        conn.close()


def update_marks(mark_id, marks_obtained, max_marks=100.0):
    """
    Updates the marks_obtained and max_marks for an existing evaluation by mark_id.
    Returns True if update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE marks
            SET marks_obtained = ?, max_marks = ?
            WHERE mark_id = ?;
            """,
            (marks_obtained, max_marks, mark_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating marks: {e}")
        return False
    finally:
        conn.close()


def delete_marks(mark_id):
    """
    Deletes a marks evaluation record by mark_id.
    Returns True if deletion was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM marks WHERE mark_id = ?;", (mark_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting marks: {e}")
        return False
    finally:
        conn.close()
