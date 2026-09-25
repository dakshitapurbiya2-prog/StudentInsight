"""
Tests for pdf_processing.review (Teacher Verification Data Workflow).
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.processor import process_pdf
from pdf_processing.review import TeacherReviewSession, create_review_session


def test_review_session_preview_and_isolation():
    """Verify preview structure, editing, and original data immutability."""
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    pipeline_result = process_pdf(pdf_path)
    session = create_review_session(pipeline_result)

    # 1. Preview structure
    preview = session.get_preview()
    assert preview["status"] == "PENDING_REVIEW"
    assert preview["is_confirmed"] is False
    assert preview["ready_for_import"] is False
    assert preview["has_critical_errors"] is False
    assert len(preview["students"]) == 52
    assert len(preview["subjects"]) == 5
    assert preview["metadata"]["academic_year"] is None
    assert any("WARN_ACADEMIC_YEAR_ABSENT" in w for w in preview["warnings"])

    # 2. Edit a student record
    original_name = preview["students"][0]["student_name"]
    original_mark = preview["students"][0]["marks"]["BT-101"]

    updated = session.update_student(
        "0112AL251001",
        {"student_name": "AASTHA SAHU EDITED", "marks": {"BT-101": 29}},
    )
    assert updated["student_name"] == "AASTHA SAHU EDITED"
    assert updated["marks"]["BT-101"] == 29

    # Verify preview reflects edits
    new_preview = session.get_preview()
    assert new_preview["students"][0]["student_name"] == "AASTHA SAHU EDITED"
    assert new_preview["students"][0]["marks"]["BT-101"] == 29

    # 3. Verify original extracted data is 100% PRESERVED
    orig_data = session.get_original_data()
    orig_student = orig_data["structure_a"]["students"][0]
    assert orig_student["student_name"] == original_name
    assert orig_student["marks"]["BT-101"] == original_mark

    # 4. Verify ABS remains exactly "ABS"
    student_aryan = next(s for s in new_preview["students"] if s["roll_number"] == "0112AL251015")
    assert student_aryan["marks"]["BT-103"] == "ABS"

    print("test_review_session_preview_and_isolation: PASS")


def test_blocking_confirmation_on_critical_errors():
    """Verify that confirmation is blocked when validation errors exist, and unblocked when fixed."""
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    pipeline_result = process_pdf(pdf_path)
    session = create_review_session(pipeline_result)

    # Introduce a critical error: mark exceeding maximum allowed (99 > 30)
    session.update_student("0112AL251001", {"marks": {"BT-101": 99}})

    preview = session.get_preview()
    assert preview["has_critical_errors"] is True
    assert preview["validation_summary"]["invalid"] == 1
    assert any("Mark out of range" in e for e in preview["errors"])

    # Attempt confirmation: MUST BE BLOCKED
    confirm_res = session.confirm(confirmed_by="Prof. Sharma")
    assert confirm_res["success"] is False
    assert confirm_res["ready_for_import"] is False
    assert "Confirmation blocked" in confirm_res["reason"]
    assert session.is_confirmed is False
    assert session.get_confirmed_data() is None

    # Teacher corrects the error back to valid mark (25 <= 30)
    session.update_student("0112AL251001", {"marks": {"BT-101": 25}})
    preview_fixed = session.get_preview()
    assert preview_fixed["has_critical_errors"] is False
    assert preview_fixed["validation_summary"]["invalid"] == 0

    # Confirmation should now SUCCEED
    confirm_ok = session.confirm(
        confirmed_by="Prof. Sharma",
        academic_year="2025-2026",
        notes="Reviewed and confirmed MST-2 marksheet.",
    )
    assert confirm_ok["success"] is True
    assert confirm_ok["ready_for_import"] is True
    assert session.is_confirmed is True

    # Check confirmed data
    confirmed_data = session.get_confirmed_data()
    assert confirmed_data is not None
    assert confirmed_data["metadata"]["academic_year"] == "2025-2026"
    assert confirmed_data["verification_audit"]["is_confirmed"] is True
    assert confirmed_data["verification_audit"]["confirmed_by"] == "Prof. Sharma"

    print("test_blocking_confirmation_on_critical_errors: PASS")


if __name__ == "__main__":
    test_review_session_preview_and_isolation()
    test_blocking_confirmation_on_critical_errors()
    print("\nALL TEACHER VERIFICATION TESTS PASSED!")
