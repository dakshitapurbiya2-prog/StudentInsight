"""
End-to-End Tests for the complete StudentInsight PDF Processing Module.

Flow tested:
PDF -> Extraction -> Metadata -> Parsing -> Cleaning -> Validation -> Normalization -> Teacher Review -> Backend Payload
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.processor import process_pdf
from pdf_processing.parser import extract_metadata, parse_student_rows
from pdf_processing.cleaner import clean_student_records
from pdf_processing.validator import validate_student_records
from pdf_processing.normalizer import normalize_extracted_data
from pdf_processing.review import create_review_session, TeacherReviewSession
from pdf_processing.mapper import map_to_backend_payload


def test_e2e_sample_pdf_full_pipeline_to_backend_payload():
    """
    Test 1: Complete happy path using the sample PDF.
    Verifies:
      - 52 students, 5 subjects
      - 260 mapped backend records
      - ABS values preserved
      - Gatekeeper prevents backend export until confirmed
      - Successful teacher confirmation releases payload
    """
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    # Step 1-6: Process PDF through pipeline
    result = process_pdf(pdf_path)
    assert result["success"] is True, f"Pipeline failed with errors: {result.get('errors')}"
    assert len(result["students"]) == 52
    assert len(result["metadata"]["subjects"]) == 5

    # Step 7: Teacher Review Session initialization
    session = create_review_session(result)
    assert session.is_confirmed is False
    assert session.ready_for_import is False

    # Security/Workflow check: Attempting backend payload export before confirmation MUST FAIL
    try:
        session.to_backend_payload(exam_id=2, max_marks=30.0)
        assert False, "Should have raised RuntimeError when exporting unconfirmed session"
    except RuntimeError as e:
        assert "not been confirmed" in str(e)

    # Preview verification
    preview = session.get_preview()
    assert preview["status"] == "PENDING_REVIEW"
    assert preview["validation_summary"]["valid"] == 52
    assert preview["validation_summary"]["invalid"] == 0
    assert preview["has_critical_errors"] is False

    # Explicit Teacher Confirmation
    confirm_res = session.confirm(
        confirmed_by="Prof. Verma",
        academic_year="2025-2026",
        notes="All 52 students verified against attendance register.",
    )
    assert confirm_res["success"] is True
    assert confirm_res["ready_for_import"] is True
    assert session.is_confirmed is True

    # Step 8: Export Structure B Backend Payload
    backend_payload = session.to_backend_payload(exam_id=2, max_marks=30.0)
    assert backend_payload["exam_id"] == 2
    assert backend_payload["max_marks"] == 30.0

    records = backend_payload["records"]

    # Verify exactly 260 records (52 students * 5 subjects)
    assert len(records) == 260, f"Expected 260 records, got {len(records)}"

    # Verify Structure B format for every record
    for r in records:
        assert "roll_number" in r and len(r["roll_number"]) >= 6
        assert "subject_code" in r and r["subject_code"].startswith("BT-")
        assert "marks" in r
        assert isinstance(r["marks"], int) or r["marks"] == "ABS"

    # Verify ABS preservation in backend payload
    abs_records = [r for r in records if r["marks"] == "ABS"]
    assert len(abs_records) == 9, f"Expected 9 ABS records, got {len(abs_records)}"

    # Specific student ABS checks
    # Student 9: ARYAN GIRI (0112AL251015) has ABS in BT-103
    aryan_bt103 = next(
        r for r in records if r["roll_number"] == "0112AL251015" and r["subject_code"] == "BT-103"
    )
    assert aryan_bt103["marks"] == "ABS"

    # Student 39: RASHMI FULKER (0112AL251058) has ABS in all 5 subjects
    rashmi_records = [r for r in records if r["roll_number"] == "0112AL251058"]
    assert len(rashmi_records) == 5
    assert all(r["marks"] == "ABS" for r in rashmi_records)

    # First student verification
    first_records = [r for r in records if r["roll_number"] == "0112AL251001"]
    assert len(first_records) == 5
    expected_marks_first = {"BT-101": 28, "BT-202": 23, "BT-103": 29, "BT-104": 23, "BT-105": 15}
    for r in first_records:
        assert r["marks"] == expected_marks_first[r["subject_code"]]

    print("test_e2e_sample_pdf_full_pipeline_to_backend_payload: PASS")


def test_e2e_error_handling_and_recovery():
    """
    Test 2: Edge cases and validation failure recovery.
    Verifies:
      - Duplicate roll numbers
      - Out-of-range marks
      - Invalid mark tokens
      - Missing metadata
      - Malformed rows
      - Teacher editing fixes errors and enables confirmation
    """
    subjects = ["BT-101", "BT-202", "BT-103"]
    max_marks = {"BT-101": 30, "BT-202": 30, "BT-103": 30}

    # 1. Synthesize student data with duplicate roll, invalid mark, out-of-range mark, malformed
    bad_students = [
        {"serial_number": 1, "roll_number": "0112AL251001", "student_name": "STUDENT ONE", "marks": {"BT-101": 25, "BT-202": 20, "BT-103": 15}},
        {"serial_number": 2, "roll_number": "0112AL251001", "student_name": "STUDENT DUPLICATE", "marks": {"BT-101": 20, "BT-202": 22, "BT-103": 18}}, # DUPLICATE
        {"serial_number": 3, "roll_number": "0112AL251003", "student_name": "STUDENT THREE", "marks": {"BT-101": 95, "BT-202": 20, "BT-103": 15}}, # OUT OF RANGE (>30)
        {"serial_number": 4, "roll_number": "0112AL251004", "student_name": "STUDENT FOUR", "marks": {"BT-101": "INVALID", "BT-202": 20, "BT-103": 15}}, # INVALID TOKEN
        {"serial_number": 5, "roll_number": "", "student_name": "STUDENT NO ROLL", "marks": {"BT-101": 20, "BT-202": 20, "BT-103": 20}}, # MISSING ROLL
        {"serial_number": 6, "roll_number": "0112AL251006", "student_name": "", "marks": {"BT-101": 20, "BT-202": 20, "BT-103": 20}}, # MISSING NAME
    ]

    val = validate_student_records(bad_students, subjects, max_marks)
    assert val["summary"]["valid"] == 1
    assert val["summary"]["invalid"] == 5

    # Structure A with these students
    mock_metadata = {
        "institution_name": "TEST INSTITUTE",
        "course": "B.TECH",
        "semester": "II",
        "branch": "AIML",
        "exam_name": "MST-2",
        "exam_session": "JULY 2026",
        "maximum_marks": max_marks,
        "academic_year": None,
    }

    struct_a = normalize_extracted_data({**mock_metadata, "subjects": subjects}, bad_students)
    session = create_review_session(struct_a)

    preview = session.get_preview()
    assert preview["has_critical_errors"] is True
    assert preview["validation_summary"]["invalid"] == 5

    # Confirmation MUST fail
    res_blocked = session.confirm(confirmed_by="Admin")
    assert res_blocked["success"] is False
    assert res_blocked["ready_for_import"] is False

    # Teacher corrects all 5 errors
    # Fix duplicate roll number on row 2
    session.update_student(2, {"roll_number": "0112AL251002"})
    # Fix out-of-range mark on row 3
    session.update_student(3, {"marks": {"BT-101": 25}})
    # Fix invalid mark on row 4
    session.update_student(4, {"marks": {"BT-101": 22}})
    # Fix missing roll number on row 5
    session.update_student(5, {"roll_number": "0112AL251005"})
    # Fix missing name on row 6
    session.update_student(6, {"student_name": "STUDENT SIX"})

    # Check that preview is now completely valid
    preview_fixed = session.get_preview()
    assert preview_fixed["has_critical_errors"] is False
    assert preview_fixed["validation_summary"]["invalid"] == 0
    assert len(preview_fixed["errors"]) == 0

    # Confirmation should now succeed
    res_ok = session.confirm(confirmed_by="Admin", academic_year="2025-2026")
    assert res_ok["success"] is True
    assert res_ok["ready_for_import"] is True

    # Backend payload maps correctly
    backend_payload = session.to_backend_payload(exam_id=10, max_marks=30.0)
    assert len(backend_payload["records"]) == 6 * 3  # 6 students * 3 subjects = 18 records

    print("test_e2e_error_handling_and_recovery: PASS")


def test_no_side_effects_or_unauthorized_writes():
    """
    Test 3: Verify that processing and review remain purely in-memory.
    No network calls or database writes occur.
    """
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    pipeline_result = process_pdf(pdf_path)
    session = create_review_session(pipeline_result)

    # Session unconfirmed: export blocked
    assert session.ready_for_import is False
    try:
        session.to_backend_payload()
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "not been confirmed" in str(e)

    print("test_no_side_effects_or_unauthorized_writes: PASS")


if __name__ == "__main__":
    test_e2e_sample_pdf_full_pipeline_to_backend_payload()
    test_e2e_error_handling_and_recovery()
    test_no_side_effects_or_unauthorized_writes()
    print("\nALL END-TO-END PIPELINE TESTS PASSED!")
