import sys
import os
import unittest

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Redirect database path to a separate test database file
import backend.database.database as db_module
TEST_DB_PATH = os.path.join(BASE_DIR, "data", "test_studentinsight.db")
db_module.DB_PATH = TEST_DB_PATH

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
        """Runs once before all tests in this class to set up a clean test database."""
        # Remove old test database if it exists
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

        # Create all tables in the test database
        create_tables()

        # Seed initial department and class for student foreign keys
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (name) VALUES ('Test Department');")
        cursor.execute("INSERT INTO classes (class_name, department_id) VALUES ('Test Class A', 1);")
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        """Runs once after all tests complete to clean up the test database file."""
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except PermissionError:
                pass

    def test_1_add_student(self):
        """Test adding a new student to the database."""
        student_id = add_student(roll_number="T101", name="Test Student 1", class_id=1)
        self.assertIsNotNone(student_id, "Failed to add student.")
        self.assertGreater(student_id, 0)

    def test_2_get_student(self):
        """Test getting a student by ID and by Roll Number."""
        # Add a student to fetch
        student_id = add_student(roll_number="T102", name="Test Student 2", class_id=1)

        # Get by ID
        student_by_id = get_student_by_id(student_id)
        self.assertIsNotNone(student_by_id)
        self.assertEqual(student_by_id["name"], "Test Student 2")

        # Get by Roll Number
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

        # Update student name
        success = update_student(student_id, roll_number="T103", name="Updated Name", class_id=1)
        self.assertTrue(success, "Failed to update student.")

        # Verify update
        updated_student = get_student_by_id(student_id)
        self.assertEqual(updated_student["name"], "Updated Name")

    def test_5_delete_student(self):
        """Test deleting a student from the database."""
        student_id = add_student(roll_number="T104", name="ToDelete Student", class_id=1)

        # Delete student
        success = delete_student(student_id)
        self.assertTrue(success, "Failed to delete student.")

        # Verify deletion
        deleted_student = get_student_by_id(student_id)
        self.assertIsNone(deleted_student, "Student still exists after deletion.")


if __name__ == "__main__":
    unittest.main()
