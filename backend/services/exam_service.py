import sys
import os
import sqlite3

# Ensure project root is in sys.path for database module imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def add_exam(exam_name, class_id, exam_date=None):
    """
    Creates a new exam record in the database.
    Returns the new exam_id on success, or None on failure.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO exams (exam_name, class_id, exam_date) VALUES (?, ?, ?);",
            (exam_name, class_id, exam_date)
        )
        conn.commit()
        exam_id = cursor.lastrowid
        return exam_id
    except sqlite3.Error as e:
        print(f"Error adding exam: {e}")
        return None
    finally:
        conn.close()


def get_exam_by_id(exam_id):
    """
    Retrieves an exam record by exam_id.
    Returns a dictionary of exam details or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT exam_id, exam_name, class_id, exam_date FROM exams WHERE exam_id = ?;",
            (exam_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "exam_id": row[0],
                "exam_name": row[1],
                "class_id": row[2],
                "exam_date": row[3]
            }
        return None
    except sqlite3.Error as e:
        print(f"Error retrieving exam by ID: {e}")
        return None
    finally:
        conn.close()


def get_all_exams():
    """
    Retrieves all exam records from the database.
    Returns a list of exam dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT exam_id, exam_name, class_id, exam_date FROM exams ORDER BY exam_id;")
        rows = cursor.fetchall()
        exams = []
        for row in rows:
            exams.append({
                "exam_id": row[0],
                "exam_name": row[1],
                "class_id": row[2],
                "exam_date": row[3]
            })
        return exams
    except sqlite3.Error as e:
        print(f"Error retrieving all exams: {e}")
        return []
    finally:
        conn.close()


def update_exam(exam_id, exam_name, class_id, exam_date=None):
    """
    Updates an existing exam record by exam_id.
    Returns True if update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE exams SET exam_name = ?, class_id = ?, exam_date = ? WHERE exam_id = ?;",
            (exam_name, class_id, exam_date, exam_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating exam: {e}")
        return False
    finally:
        conn.close()


def delete_exam(exam_id):
    """
    Deletes an exam record by exam_id.
    Returns True if deletion was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM exams WHERE exam_id = ?;", (exam_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting exam: {e}")
        return False
    finally:
        conn.close()
