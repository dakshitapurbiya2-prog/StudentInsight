import sys
import os
import sqlite3

# Ensure project root is in sys.path for database module imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def add_subject(subject_name, class_id, teacher_id=None):
    """
    Creates a new subject record in the database.
    Returns the new subject_id on success, or None on failure.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subjects (subject_name, class_id, teacher_id) VALUES (?, ?, ?);",
            (subject_name, class_id, teacher_id)
        )
        conn.commit()
        subject_id = cursor.lastrowid
        return subject_id
    except sqlite3.Error as e:
        print(f"Error adding subject: {e}")
        return None
    finally:
        conn.close()


def get_subject_by_id(subject_id):
    """
    Retrieves a subject record by subject_id.
    Returns a dictionary of subject details or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT subject_id, subject_name, class_id, teacher_id FROM subjects WHERE subject_id = ?;",
            (subject_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "subject_id": row[0],
                "subject_name": row[1],
                "class_id": row[2],
                "teacher_id": row[3]
            }
        return None
    except sqlite3.Error as e:
        print(f"Error retrieving subject by ID: {e}")
        return None
    finally:
        conn.close()


def get_all_subjects():
    """
    Retrieves all subject records from the database.
    Returns a list of subject dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT subject_id, subject_name, class_id, teacher_id FROM subjects ORDER BY subject_id;")
        rows = cursor.fetchall()
        subjects = []
        for row in rows:
            subjects.append({
                "subject_id": row[0],
                "subject_name": row[1],
                "class_id": row[2],
                "teacher_id": row[3]
            })
        return subjects
    except sqlite3.Error as e:
        print(f"Error retrieving all subjects: {e}")
        return []
    finally:
        conn.close()


def update_subject(subject_id, subject_name, class_id, teacher_id=None):
    """
    Updates an existing subject record by subject_id.
    Returns True if update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE subjects SET subject_name = ?, class_id = ?, teacher_id = ? WHERE subject_id = ?;",
            (subject_name, class_id, teacher_id, subject_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating subject: {e}")
        return False
    finally:
        conn.close()


def delete_subject(subject_id):
    """
    Deletes a subject record by subject_id.
    Returns True if deletion was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM subjects WHERE subject_id = ?;", (subject_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting subject: {e}")
        return False
    finally:
        conn.close()
