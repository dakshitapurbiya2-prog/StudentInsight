import sys
import os
import unittest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.main import app
from backend.services import analytics_service

client = TestClient(app)


class TestStudentAnalyticsAPI(unittest.TestCase):

    def test_1_get_student_profile(self):
        """Test GET /analytics/student/1/profile"""
        response = client.get("/analytics/student/1/profile")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["student_id"], 1)
        self.assertIn("name", data)
        self.assertIn("department_name", data)

    def test_2_get_all_student_marks(self):
        """Test GET /analytics/student/1/marks"""
        response = client.get("/analytics/student/1/marks")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_3_get_marks_grouped_by_exam(self):
        """Test GET /analytics/student/1/marks/by-exam"""
        response = client.get("/analytics/student/1/marks/by-exam")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("exam_average_percentage", data[0])

    def test_4_get_marks_grouped_by_subject(self):
        """Test GET /analytics/student/1/marks/by-subject"""
        response = client.get("/analytics/student/1/marks/by-subject")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("subject_average_percentage", data[0])

    def test_5_get_student_average(self):
        """Test GET /analytics/student/1/average"""
        response = client.get("/analytics/student/1/average")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("overall_percentage", data)
        self.assertIn("performance_grade", data)

    def test_6_get_subject_percentages(self):
        """Test GET /analytics/student/1/subjects-percentage"""
        response = client.get("/analytics/student/1/subjects-percentage")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertIn("percentage", data[0])

    def test_7_get_exam_percentages(self):
        """Test GET /analytics/student/1/exams-percentage"""
        response = client.get("/analytics/student/1/exams-percentage")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertIn("percentage", data[0])

    def test_8_get_exam_progress(self):
        """Test GET /analytics/student/1/progress"""
        response = client.get("/analytics/student/1/progress")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)
        self.assertIn("change_from_previous", data[1])
        self.assertIn("trend", data[1])

    def test_9_get_student_dashboard(self):
        """Test GET /analytics/student/1/dashboard"""
        response = client.get("/analytics/student/1/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("profile", data)
        self.assertIn("overall_average", data)
        self.assertIn("subject_performance", data)
        self.assertIn("exam_performance", data)
        self.assertIn("exam_progress", data)


if __name__ == "__main__":
    unittest.main()
