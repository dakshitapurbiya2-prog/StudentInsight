import os
import sys
import unittest
import tempfile

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.parser import (
    parse_marksheet_pdf,
    parse_marksheet_text,
    to_import_records,
    export_to_json,
    export_to_csv,
)

SAMPLE_PDF = os.path.join(os.path.dirname(__file__), "..", "sample_data", "college_marks.pdf")


class TestMarksheetParser(unittest.TestCase):
    def setUp(self):
        self.pdf_path = os.path.abspath(SAMPLE_PDF)
        self.parsed_data = parse_marksheet_pdf(self.pdf_path)

    def test_metadata_extraction(self):
        meta = self.parsed_data.get("metadata", {})
        self.assertIn("BANSAL INSTITUTE", meta.get("institution", "").upper())
        self.assertIn("SEMESTER", meta.get("semester", "").upper())
        self.assertEqual(meta.get("branch", "").upper(), "AIML")
        self.assertIn("MST-2", meta.get("exam_name", "").upper())

    def test_subjects_and_max_marks(self):
        subjects = self.parsed_data.get("subjects", [])
        expected_subjects = ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"]
        self.assertEqual(subjects, expected_subjects)

        max_marks = self.parsed_data.get("max_marks", {})
        for subj in expected_subjects:
            self.assertEqual(max_marks.get(subj), 30.0)

    def test_student_count(self):
        students = self.parsed_data.get("students", [])
        self.assertEqual(len(students), 52)
        self.assertEqual(self.parsed_data.get("total_students"), 52)

    def test_first_student_record(self):
        student = self.parsed_data["students"][0]
        self.assertEqual(student["s_no"], 1)
        self.assertEqual(student["roll_number"], "0112AL251001")
        self.assertEqual(student["name"], "AASTHA SAHU")
        self.assertEqual(student["marks"]["BT-101"], 28.0)
        self.assertEqual(student["marks"]["BT-202"], 23.0)
        self.assertEqual(student["marks"]["BT-103"], 29.0)
        self.assertEqual(student["marks"]["BT-104"], 23.0)
        self.assertEqual(student["marks"]["BT-105"], 15.0)
        self.assertEqual(student["total_obtained"], 118.0)
        self.assertEqual(student["total_max"], 150.0)
        self.assertEqual(student["percentage"], 78.67)
        self.assertEqual(student["status"], "PASS")

    def test_absent_handling(self):
        # Student 9 (ARYAN GIRI) was absent in BT-103
        student_9 = next(s for s in self.parsed_data["students"] if s["s_no"] == 9)
        self.assertEqual(student_9["name"], "ARYAN GIRI")
        self.assertIsNone(student_9["marks"]["BT-103"])
        self.assertEqual(student_9["subject_status"]["BT-103"], "ABSENT")
        self.assertEqual(student_9["marks"]["BT-101"], 30.0)

        # Student 39 (RASHMI FULKER) was absent in all subjects
        student_39 = next(s for s in self.parsed_data["students"] if s["s_no"] == 39)
        self.assertEqual(student_39["name"], "RASHMI FULKER")
        self.assertEqual(student_39["status"], "ABSENT")
        self.assertEqual(student_39["total_obtained"], 0.0)
        for subj in self.parsed_data["subjects"]:
            self.assertIsNone(student_39["marks"][subj])

    def test_class_summary_statistics(self):
        summary = self.parsed_data.get("summary", {})
        self.assertEqual(summary["total_students"], 52)
        self.assertGreater(summary["passed"], 0)
        self.assertGreaterEqual(summary["all_absent"], 1)
        self.assertGreater(summary["class_average_percentage"], 0.0)

        subj_stats = self.parsed_data.get("subject_statistics", {})
        self.assertIn("BT-101", subj_stats)
        self.assertEqual(subj_stats["BT-101"]["highest"], 30.0)
        self.assertGreater(subj_stats["BT-101"]["average"], 0.0)

    def test_to_import_records(self):
        records = to_import_records(self.parsed_data)
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)

        first_rec = records[0]
        self.assertIn("roll_number", first_rec)
        self.assertIn("student_name", first_rec)
        self.assertIn("subject", first_rec)
        self.assertIn("marks", first_rec)
        self.assertIsInstance(first_rec["marks"], (int, float))

    def test_export_to_json_and_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "marks.json")
            csv_file = os.path.join(tmpdir, "marks.csv")

            export_to_json(self.parsed_data, output_path=json_file)
            self.assertTrue(os.path.exists(json_file))
            self.assertGreater(os.path.getsize(json_file), 100)

            export_to_csv(self.parsed_data, output_path=csv_file)
            self.assertTrue(os.path.exists(csv_file))
            self.assertGreater(os.path.getsize(csv_file), 100)


if __name__ == "__main__":
    unittest.main()
