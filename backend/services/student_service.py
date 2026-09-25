import sys
import os
import sqlite3

# Ensure project root is in sys.path for database module imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection


def add_student(roll_number, name, class_id):
    """
    Creates a new student record in the database.
    Returns the new student_id on success, or None on failure.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO students (roll_number, name, class_id) VALUES (?, ?, ?);",
            (roll_number, name, class_id)
        )
        conn.commit()
        student_id = cursor.lastrowid
        return student_id
    except sqlite3.Error as e:
        print(f"Error adding student: {e}")
        return None
    finally:
        conn.close()


def get_student_by_id(student_id):
    """
    Retrieves a student record by student_id.
    Returns a dictionary of student details or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT student_id, roll_number, name, class_id FROM students WHERE student_id = ?;",
            (student_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "student_id": row[0],
                "roll_number": row[1],
                "name": row[2],
                "class_id": row[3]
            }
        return None
    except sqlite3.Error as e:
        print(f"Error retrieving student by ID: {e}")
        return None
    finally:
        conn.close()


def get_student_by_roll_number(roll_number):
    """
    Retrieves a student record by roll_number.
    Returns a dictionary of student details or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT student_id, roll_number, name, class_id FROM students WHERE roll_number = ?;",
            (roll_number,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "student_id": row[0],
                "roll_number": row[1],
                "name": row[2],
                "class_id": row[3]
            }
        return None
    except sqlite3.Error as e:
        print(f"Error retrieving student by roll number: {e}")
        return None
    finally:
        conn.close()


def get_all_students():
    """
    Retrieves all student records from the database.
    Returns a list of student dictionaries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT student_id, roll_number, name, class_id FROM students ORDER BY student_id;")
        rows = cursor.fetchall()
        students = []
        for row in rows:
            students.append({
                "student_id": row[0],
                "roll_number": row[1],
                "name": row[2],
                "class_id": row[3]
            })
        return students
    except sqlite3.Error as e:
        print(f"Error retrieving all students: {e}")
        return []
    finally:
        conn.close()


def update_student(student_id, roll_number, name, class_id):
    """
    Updates an existing student record by student_id.
    Returns True if update was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE students SET roll_number = ?, name = ?, class_id = ? WHERE student_id = ?;",
            (roll_number, name, class_id, student_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error updating student: {e}")
        return False
    finally:
        conn.close()


def delete_student(student_id):
    """
    Deletes a student record by student_id.
    Returns True if deletion was successful, False otherwise.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM students WHERE student_id = ?;", (student_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting student: {e}")
        return False
    finally:
        conn.close()
