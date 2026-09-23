import sys
import os
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import backend.database.database as db_module
ORIGINAL_DB_PATH = db_module.DB_PATH
TEST_DB_PATH = os.path.join(BASE_DIR, "data", "test_marks_import.db")

from backend.database.database import create_tables, get_connection
from backend.services.student_service import add_student
from backend.services.teacher_service import add_teacher
from backend.services.subject_service import add_subject
from backend.services.exam_service import add_exam
from backend.services.marks_import_service import process_marks_import


class TestMarksImportService(unittest.TestCase):

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
        cursor.execute("INSERT INTO departments (name) VALUES ('Import Test Dept');")
        cursor.execute("INSERT INTO classes (class_name, department_id) VALUES ('Import Class A', 1);")
        conn.commit()
        conn.close()

        cls.student_id = add_student(roll_number="IMP101", name="Import Test Student", class_id=1)
        cls.teacher_id = add_teacher(name="Import Teacher", email="impteacher@test.com")
        cls.subject_id = add_subject(subject_name="Python", class_id=1, teacher_id=cls.teacher_id)
        cls.exam_id = add_exam(exam_name="Unit Test 1", class_id=1, exam_date="2026-12-15")

    @classmethod
    def tearDownClass(cls):
        """Restore original DB_PATH."""
        db_module.DB_PATH = ORIGINAL_DB_PATH

    def test_import_valid_record(self):
        """1. Test importing a perfectly valid extracted mark record."""
        payload = [
            {"roll_number": "IMP101", "subject": "Python", "marks": 88.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["total_records"], 1)
        self.assertEqual(result["saved_records"], 1)
        self.assertEqual(result["failed_records"], 0)
        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(result["saved"][0]["marks_obtained"], 88.0)

    def test_import_invalid_roll_number(self):
        """2. Test that a non-existent student roll_number is rejected with a clear error."""
        payload = [
            {"roll_number": "NON_EXISTENT_999", "subject": "Python", "marks": 85.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["saved_records"], 0)
        self.assertEqual(result["failed_records"], 1)
        self.assertIn("not found", result["errors"][0]["reason"].lower())

    def test_import_invalid_subject(self):
        """3. Test that a non-existent subject for the student's class is rejected."""
        payload = [
            {"roll_number": "IMP101", "subject": "Quantum Computing", "marks": 90.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["saved_records"], 0)
        self.assertEqual(result["failed_records"], 1)
        self.assertIn("subject 'quantum computing' not found", result["errors"][0]["reason"].lower())

    def test_import_invalid_exam_id(self):
        """4. Test that a non-existent exam_id stops processing with a clear error."""
        payload = [
            {"roll_number": "IMP101", "subject": "Python", "marks": 80.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=9999, max_marks=100.0)

        self.assertEqual(result["saved_records"], 0)
        self.assertEqual(result["failed_records"], 1)
        self.assertIn("exam with id 9999 does not exist", result["errors"][0]["reason"].lower())

    def test_import_negative_marks(self):
        """5. Test that negative marks are rejected."""
        payload = [
            {"roll_number": "IMP101", "subject": "Python", "marks": -15.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["saved_records"], 0)
        self.assertEqual(result["failed_records"], 1)
        self.assertIn("cannot be negative", result["errors"][0]["reason"].lower())

    def test_import_exceeding_max_marks(self):
        """6. Test that marks exceeding max_marks are rejected."""
        payload = [
            {"roll_number": "IMP101", "subject": "Python", "marks": 105.0}
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["saved_records"], 0)
        self.assertEqual(result["failed_records"], 1)
        self.assertIn("exceed maximum allowed marks", result["errors"][0]["reason"].lower())

    def test_import_batch_with_partial_errors(self):
        """7 & 8. Test batch containing valid and invalid items: only valid items are saved."""
        payload = [
            {"roll_number": "IMP101", "subject": "Python", "marks": 92.0},      # Valid -> Save
            {"roll_number": "FAKE_99", "subject": "Python", "marks": 75.0},      # Bad roll -> Fail
            {"roll_number": "IMP101", "subject": "Python", "marks": 120.0}      # Exceed max -> Fail
        ]
        result = process_marks_import(imported_records=payload, exam_id=self.exam_id, max_marks=100.0)

        self.assertEqual(result["total_records"], 3)
        self.assertEqual(result["saved_records"], 1)
        self.assertEqual(result["failed_records"], 2)


if __name__ == "__main__":
    unittest.main()
