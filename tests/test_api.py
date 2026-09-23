import sys
import os
import unittest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.main import app

client = TestClient(app)


class TestStudentInsightAPI(unittest.TestCase):

    def test_root_endpoint(self):
        """Test GET / returns welcome message."""
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data["project"], "StudentInsight")

    def test_get_all_students(self):
        """Test GET /students endpoint."""
        response = client.get("/students")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_all_teachers(self):
        """Test GET /teachers endpoint."""
        response = client.get("/teachers")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_all_subjects(self):
        """Test GET /subjects endpoint."""
        response = client.get("/subjects")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_all_exams(self):
        """Test GET /exams endpoint."""
        response = client.get("/exams")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_student_marks(self):
        """Test GET /marks/student/1 endpoint."""
        response = client.get("/marks/student/1")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)


if __name__ == "__main__":
    unittest.main()
