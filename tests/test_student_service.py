import sys
import os
import unittest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import backend.database.database as db_module
ORIGINAL_DB_PATH = db_module.DB_PATH
TEST_DB_PATH = os.path.join(BASE_DIR, "data", "test_student_service.db")

from backend.database.database import create_tables, get_connection
from backend.services.student_service import (
    add_student,
    get_student_by_id,
    get_student_by_roll_number,
    get_all_students,
    update_student,
    delete_student
)


class TestStudentService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Redirect DB_PATH to isolated test database and create tables."""
        db_module.DB_PATH = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except PermissionError:
                pass

        create_tables()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (name) VALUES ('Test Department');")
        cursor.execute("INSERT INTO classes (class_name, department_id) VALUES ('Test Class A', 1);")
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        """Restore original DB_PATH."""
        db_module.DB_PATH = ORIGINAL_DB_PATH

    def test_1_add_student(self):
        """Test adding a new student to the database."""
        student_id = add_student(roll_number="T101", name="Test Student 1", class_id=1)
        self.assertIsNotNone(student_id, "Failed to add student.")
        self.assertGreater(student_id, 0)

    def test_2_get_student(self):
        """Test getting a student by ID and by Roll Number."""
        student_id = add_student(roll_number="T102", name="Test Student 2", class_id=1)

        student_by_id = get_student_by_id(student_id)
        self.assertIsNotNone(student_by_id)
        self.assertEqual(student_by_id["name"], "Test Student 2")

        student_by_roll = get_student_by_roll_number("T102")
        self.assertIsNotNone(student_by_roll)
        self.assertEqual(student_by_roll["student_id"], student_id)

    def test_3_get_all_students(self):
        """Test retrieving all students from the database."""
        students = get_all_students()
        self.assertIsInstance(students, list)
        self.assertGreaterEqual(len(students), 2)

    def test_4_update_student(self):
        """Test updating an existing student's details."""
        student_id = add_student(roll_number="T103", name="Old Name", class_id=1)
        success = update_student(student_id, roll_number="T103", name="Updated Name", class_id=1)
        self.assertTrue(success, "Failed to update student.")
        updated_student = get_student_by_id(student_id)
        self.assertEqual(updated_student["name"], "Updated Name")

    def test_5_delete_student(self):
        """Test deleting a student from the database."""
        student_id = add_student(roll_number="T104", name="ToDelete Student", class_id=1)
        success = delete_student(student_id)
        self.assertTrue(success, "Failed to delete student.")
        deleted_student = get_student_by_id(student_id)
        self.assertIsNone(deleted_student, "Student still exists after deletion.")


if __name__ == "__main__":
    unittest.main()
