"""
Tests for pdf_processing.normalizer and standardized Structure A output.
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.extractor import extract_text_from_pdf
from pdf_processing.parser import extract_metadata, parse_student_rows
from pdf_processing.cleaner import clean_student_records
from pdf_processing.normalizer import normalize_extracted_data
from pdf_processing.processor import process_pdf


def test_unit_normalization_rules():
    """Verify individual field normalization rules with synthetic dirty inputs."""
    dirty_metadata = {
        "institution_name": "  BANSAL   INSTITUTE   OF TECHNOLOGY  ",
        "course": "  b.tech  ",
        "semester": " ii ",
        "branch": " aiml ",
        "exam_name": "  mst-2  ",
        "exam_session": " july 2026 ",
        "maximum_marks": {"bt-101": "30", "BT-202": 30.0},
        "subjects": ["bt-101", "BT-202"],
        # academic_year is absent and must NOT be guessed
    }

    dirty_students = [
        {
            "serial_number": "1",
            "roll_number": "  0112al251001 ",
            "student_name": "  aastha   sahu  ",
            "marks": {"BT-101": "28", "BT-202": "abs"},
        }
    ]

    result = normalize_extracted_data(dirty_metadata, dirty_students)

    # 1. Roll number stripped and uppercased
    student = result["students"][0]
    assert student["roll_number"] == "0112AL251001", f"Unexpected roll: {student['roll_number']}"

    # 2. Student name stripped, collapsed whitespace, uppercased
    assert student["student_name"] == "AASTHA SAHU", f"Unexpected name: {student['student_name']}"

    # 3. Numeric marks remain numeric (integers)
    assert student["marks"]["BT-101"] == 28
    assert isinstance(student["marks"]["BT-101"], int)

    # 4. "ABS" remains exactly "ABS"
    assert student["marks"]["BT-202"] == "ABS"

    # 5. Subject order preserved and uppercase
    assert result["subjects"] == ["BT-101", "BT-202"]

    # 6. Metadata normalized
    meta = result["metadata"]
    assert meta["institution_name"] == "BANSAL INSTITUTE OF TECHNOLOGY"
    assert meta["course"] == "B.TECH"
    assert meta["semester"] == "II"
    assert meta["branch"] == "AIML"
    assert meta["maximum_marks"] == {"BT-101": 30, "BT-202": 30}

    # 7. Academic year remains None when absent (NEVER guessed)
    assert meta["academic_year"] is None

    # 8. Missing metadata is not silently invented
    empty_meta = {}
    empty_result = normalize_extracted_data(empty_meta, [])
    assert empty_result["metadata"]["course"] is None
    assert empty_result["metadata"]["branch"] is None
    assert empty_result["metadata"]["academic_year"] is None

    print("test_unit_normalization_rules: PASS")


def test_sample_pdf_structure_a():
    """Verify normalization against real sample PDF produces canonical Structure A."""
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    # Process using the end-to-end pipeline
    result = process_pdf(pdf_path)

    assert result["success"] is True, "Pipeline expected success=True"
    structure_a = result["structure_a"]
    assert structure_a is not None, "structure_a must not be None"

    # Top-level keys must match Structure A exactly
    assert set(structure_a.keys()) == {"metadata", "subjects", "students"}

    # Metadata checks
    meta = structure_a["metadata"]
    assert meta["institution_name"] == "BANSAL INSTITUTE OF SCIENCE AND TECHNOLOGY, BHOPAL"
    assert meta["course"] == "B.TECH"
    assert meta["semester"] == "II"
    assert meta["branch"] == "AIML"
    assert meta["exam_name"] == "MST-2"
    assert meta["exam_session"] == "JULY 2026"
    assert meta["academic_year"] is None  # Non-inference confirmed

    expected_subjects = ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"]
    assert structure_a["subjects"] == expected_subjects
    assert meta["maximum_marks"] == {s: 30 for s in expected_subjects}

    # 9. Sample PDF produces exactly 52 students
    students = structure_a["students"]
    assert len(students) == 52, f"Expected 52 students, got {len(students)}"

    # 10. Every student has exactly 5 subject marks
    for s in students:
        assert len(s["marks"]) == 5, f"Student {s['roll_number']} missing marks"
        assert list(s["marks"].keys()) == expected_subjects, "Subject alignment mismatch"

    # First student verification
    first = students[0]
    assert first["serial_number"] == 1
    assert first["roll_number"] == "0112AL251001"
    assert first["student_name"] == "AASTHA SAHU"
    assert first["marks"] == {"BT-101": 28, "BT-202": 23, "BT-103": 29, "BT-104": 23, "BT-105": 15}

    # Last student verification
    last = students[-1]
    assert last["serial_number"] == 52
    assert last["roll_number"] == "0112AL251078"
    assert last["student_name"] == "YASH SAHU"
    assert last["marks"] == {"BT-101": 7, "BT-202": 12, "BT-103": 5, "BT-104": 10, "BT-105": 11}

    # ABS checks: 9 marks across 5 students
    abs_students = [s for s in students if any(v == "ABS" for v in s["marks"].values())]
    assert len(abs_students) == 5, f"Expected 5 students with ABS, got {len(abs_students)}"

    total_abs = sum(1 for s in students for v in s["marks"].values() if v == "ABS")
    assert total_abs == 9, f"Expected 9 ABS marks, got {total_abs}"

    # Verify student 39 is ABS in all 5 subjects
    rashmi = next(s for s in students if s["roll_number"] == "0112AL251058")
    assert all(m == "ABS" for m in rashmi["marks"].values()), "Student 39 should have ABS in all subjects"

    print("test_sample_pdf_structure_a: PASS")


if __name__ == "__main__":
    test_unit_normalization_rules()
    test_sample_pdf_structure_a()
    print("\nALL NORMALIZER TESTS PASSED!")
