import os
import sys
import unittest

# Ensure the project root directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.extractor import extract_text_from_pdf

SAMPLE_PDF = os.path.join(os.path.dirname(__file__), "..", "sample_data", "college_marks.pdf")


class TestExtractor(unittest.TestCase):
    def test_extract_text_valid_pdf(self):
        pdf_path = os.path.abspath(SAMPLE_PDF)
        text = extract_text_from_pdf(pdf_path)
        self.assertIsNotNone(text)
        self.assertGreater(len(text), 0)
        self.assertIn("BANSAL INSTITUTE", text)
        self.assertIn("BT-101", text)

    def test_extract_text_nonexistent_pdf(self):
        text = extract_text_from_pdf("non_existent_file.pdf")
        self.assertEqual(text, "")


if __name__ == "__main__":
    pdf_path = "sample_data/college_marks.pdf"
    extracted_text = extract_text_from_pdf(pdf_path)
    print(extracted_text)
    print("PDF extraction test completed")
    unittest.main()
