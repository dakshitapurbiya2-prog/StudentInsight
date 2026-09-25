import sys
import os
import unittest
from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.main import app

client = TestClient(app)


class TestDirectorAnalyticsAPI(unittest.TestCase):

    def test_1_get_departments_overview(self):
        """Test GET /analytics/director/departments"""
        response = client.get("/analytics/director/departments")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("department_name", data[0])

    def test_2_get_classes_overview(self):
        """Test GET /analytics/director/classes"""
        response = client.get("/analytics/director/classes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("student_count", data[0])

    def test_3_get_class_student_count(self):
        """Test GET /analytics/director/class/1/students-count"""
        response = client.get("/analytics/director/class/1/students-count")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["class_id"], 1)
        self.assertIn("student_count", data)

    def test_4_get_class_average(self):
        """Test GET /analytics/director/class/1/average"""
        response = client.get("/analytics/director/class/1/average")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("class_average_percentage", data)

    def test_5_get_subject_average(self):
        """Test GET /analytics/director/subject/1/average"""
        response = client.get("/analytics/director/subject/1/average")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("subject_average_percentage", data)

    def test_6_get_exam_wise_class_performance(self):
        """Test GET /analytics/director/class/1/exams-performance"""
        response = client.get("/analytics/director/class/1/exams-performance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_7_compare_class_performances(self):
        """Test GET /analytics/director/exams/comparison"""
        response = client.get("/analytics/director/exams/comparison")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_8_get_student_count_by_class(self):
        """Test GET /analytics/director/students-count-by-class"""
        response = client.get("/analytics/director/students-count-by-class")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_9_get_class_subject_performance(self):
        """Test GET /analytics/director/class/1/subjects-performance"""
        response = client.get("/analytics/director/class/1/subjects-performance")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_10_get_director_dashboard(self):
        """Test GET /analytics/director/dashboard"""
        response = client.get("/analytics/director/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("college_overall_average", data)
        self.assertIn("departments", data)
        self.assertIn("classes_performance", data)
        self.assertIn("exam_comparison", data)


if __name__ == "__main__":
    unittest.main()
