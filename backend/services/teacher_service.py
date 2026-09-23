import sys
import os
import sqlite3

# Ensure project root is in sys.path for database module imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def add_teacher(name, email=None):
    """
    Creates a new teacher record in the database.
    Returns the new teacher_id on success, or None on failure.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO teachers (name, email) VALUES (?, ?);",
            (name, email)
        )
        conn.commit()
        teacher_id = cursor.lastrowid
        return teacher_id
    except sqlite3.Error as e:
        print(f"Error adding teacher: {e}")
        return None
    finally:
        conn.close()


def get_teacher_by_id(teacher_id):
    """
    Retrieves a teacher record by teacher_id.
    Returns a dictionary of teacher details or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT teacher_id, name, email FROM teachers WHERE teacher_id = ?;",
            (teacher_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "teacher_id": row[0],
                "name": row[1],
                "email": row[2]
            }
        return None
    except sqlite3.Error as e:
        print(f"Error retrieving teacher by ID: {e}")
        return None
    finally:
        conn.close()


def get_all_teachers():
    """
    Retrieves all teacher records from the database.
    Returns a list of teacher dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT teacher_id, name, email FROM teachers ORDER BY teacher_id;")
        rows = cursor.fetchall()
        teachers = []
        for row in rows:
            teachers.append({
                "teacher_id": row[0],
                "name": row[1],
                "email": row[2]
            })
        return teachers
    except sqlite3.Error as e:
        print(f"Error retrieving all teachers: {e}")
        return []
    finally:
        conn.close()


def update_teacher(teacher_id, name, email=None):
    """
    Updates an existing teacher record by teacher_id.
    Returns True if update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE teachers SET name = ?, email = ? WHERE teacher_id = ?;",
            (name, email, teacher_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating teacher: {e}")
        return False
    finally:
        conn.close()


def delete_teacher(teacher_id):
    """
    Deletes a teacher record by teacher_id.
    Returns True if deletion was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM teachers WHERE teacher_id = ?;", (teacher_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting teacher: {e}")
        return False
    finally:
        conn.close()
