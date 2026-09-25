# Temporary test file to manually verify parse_student_rows()
# Run from the project root with:
#   python tests/test_parser.py

import os
import sys

# Make sure the project root is on the path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.extractor import extract_text_from_pdf
from pdf_processing.parser import parse_student_rows

# --- 1. Path to the sample PDF ---
PDF_PATH = "sample_data/college_marks.pdf"

# --- 2. Subject codes in the order they appear in the PDF ---
SUBJECTS = ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"]

# --- 3. Extract raw text from the PDF ---
raw_text = extract_text_from_pdf(PDF_PATH)

# --- 4. Parse the raw text into student records ---
students = parse_student_rows(raw_text, SUBJECTS)

# --- 5. Print results ---
print(f"Total students parsed: {len(students)}")
print()

print("First student:")
print(students[0])
print()

print("Last student:")
print(students[-1])
