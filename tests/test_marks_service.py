import sys
import os
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import backend.database.database as db_module
ORIGINAL_DB_PATH = db_module.DB_PATH
TEST_DB_PATH = os.path.join(BASE_DIR, "data", "test_marks_service.db")

from backend.database.database import create_tables, get_connection
from backend.services.student_service import add_student
from backend.services.teacher_service import add_teacher
from backend.services.subject_service import add_subject
from backend.services.exam_service import add_exam
from backend.services.marks_service import (
    add_marks,
    get_marks_by_student,
    get_marks_by_exam,
    get_marks_by_subject,
    update_marks,
    delete_marks
)


class TestMarksService(unittest.TestCase):

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
        cursor.execute("INSERT INTO departments (name) VALUES ('Marks Test Dept');")
        cursor.execute("INSERT INTO classes (class_name, department_id) VALUES ('Marks Test Class', 1);")
        conn.commit()
        conn.close()

        cls.student_id = add_student(roll_number="M101", name="Marks Test Student", class_id=1)
        cls.teacher_id = add_teacher(name="Marks Test Teacher", email="marksteacher@test.com")
        cls.subject_id = add_subject(subject_name="Marks Test Subject", class_id=1, teacher_id=cls.teacher_id)
        cls.exam_id = add_exam(exam_name="Marks Test Exam", class_id=1, exam_date="2026-12-10")

    @classmethod
    def tearDownClass(cls):
        """Restore original DB_PATH."""
        db_module.DB_PATH = ORIGINAL_DB_PATH

    def test_6_add_marks(self):
        """Test adding marks evaluation record."""
        mark_id = add_marks(
            student_id=self.student_id,
            subject_id=self.subject_id,
            exam_id=self.exam_id,
            marks_obtained=85.5,
            max_marks=100.0
        )
        self.assertIsNotNone(mark_id, "Failed to add marks.")
        self.assertGreater(mark_id, 0)

    def test_7_read_marks(self):
        """Test reading marks by student, by exam, and by subject."""
        mark_id = add_marks(
            student_id=self.student_id,
            subject_id=self.subject_id,
            exam_id=self.exam_id,
            marks_obtained=90.0,
            max_marks=100.0
        )

        by_student = get_marks_by_student(self.student_id)
        self.assertIsInstance(by_student, list)
        self.assertGreater(len(by_student), 0)

        by_exam = get_marks_by_exam(self.exam_id)
        self.assertIsInstance(by_exam, list)
        self.assertGreater(len(by_exam), 0)

        by_subject = get_marks_by_subject(self.subject_id)
        self.assertIsInstance(by_subject, list)
        self.assertGreater(len(by_subject), 0)

    def test_8_update_marks(self):
        """Test updating marks obtained and max marks for a record."""
        mark_id = add_marks(
            student_id=self.student_id,
            subject_id=self.subject_id,
            exam_id=self.exam_id,
            marks_obtained=70.0,
            max_marks=100.0
        )

        success = update_marks(mark_id=mark_id, marks_obtained=95.0, max_marks=100.0)
        self.assertTrue(success, "Failed to update marks.")

        student_marks = get_marks_by_student(self.student_id)
        updated_entry = next((m for m in student_marks if m["mark_id"] == mark_id), None)
        self.assertIsNotNone(updated_entry)
        self.assertEqual(updated_entry["marks_obtained"], 95.0)

    def test_9_delete_marks(self):
        """Test deleting a marks evaluation record."""
        mark_id = add_marks(
            student_id=self.student_id,
            subject_id=self.subject_id,
            exam_id=self.exam_id,
            marks_obtained=60.0,
            max_marks=100.0
        )

        success = delete_marks(mark_id=mark_id)
        self.assertTrue(success, "Failed to delete marks.")

        student_marks = get_marks_by_student(self.student_id)
        deleted_entry = next((m for m in student_marks if m["mark_id"] == mark_id), None)
        self.assertIsNone(deleted_entry, "Marks record still exists after deletion.")


if __name__ == "__main__":
    unittest.main()
