"""
tests/test_workflow_adapter.py

Unit tests for pdf_processing.workflow_adapter.

Tests all adapter functions (process_uploaded_bytes, update_student,
confirm_review, run_dry_run, execute_import, acknowledge_uncertain,
reset_workflow) using:
  - The real sample PDF for extraction tests
  - unittest.mock for all HTTP calls

No Streamlit dependency.  No live backend required.  No database writes.
"""

import json
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pdf_processing.workflow_adapter as wa
from pdf_processing.workflow_adapter import (
    STAGE_UPLOAD,
    STAGE_REVIEW,
    STAGE_DRY_RUN,
    STAGE_IMPORT_READY,
    STAGE_DONE,
    STAGE_UNCERTAIN,
)

# ── Sample PDF ────────────────────────────────────────────────────────────────
SAMPLE_PDF = os.path.join(
    os.path.dirname(__file__), "..", "pdf_processing", "samples", "sample_marks.pdf"
)


def _pdf_bytes() -> bytes:
    with open(SAMPLE_PDF, "rb") as f:
        return f.read()


# ── Mock HTTP helper ───────────────────────────────────────────────────────────
def _mock_response(status=200, json_data=None):
    mock = MagicMock()
    mock.status = status
    body = json.dumps(json_data).encode("utf-8") if json_data else b""
    mock.read.return_value = body
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


def _ok_dry_run():
    return {
        "total_records": 260, "saved_records": 251, "skipped_absent": 9,
        "failed_records": 0, "saved": [], "absent": [], "errors": [],
        "dry_run": True, "message": "Dry run complete.",
    }


def _ok_import():
    return {
        "total_records": 260, "saved_records": 251, "skipped_absent": 9,
        "failed_records": 0, "saved": [], "absent": [], "errors": [],
        "dry_run": False,
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────
def _state_after_upload():
    """Return state after a successful PDF upload."""
    state = wa.process_uploaded_bytes(_pdf_bytes(), filename="sample_marks.pdf")
    assert state["stage"] == STAGE_REVIEW, f"Expected REVIEW, got {state['stage']}"
    return state


def _state_after_confirm(state=None):
    """Return state after teacher confirmation."""
    if state is None:
        state = _state_after_upload()
    updated = wa.confirm_review(
        state=state,
        confirmed_by="Dr. Test",
        exam_id=2,
        max_marks=30.0,
        academic_year="2025-2026",
    )
    assert updated["stage"] == STAGE_DRY_RUN, f"Expected DRY_RUN, got {updated['stage']}: {updated.get('errors')}"
    return updated


def _state_after_dry_run(state=None):
    """Return state after a passing dry-run."""
    if state is None:
        state = _state_after_confirm()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_dry_run())):
        updated = wa.run_dry_run(state=state)
    assert updated["dry_run_passed"], f"Dry run did not pass: {updated.get('dry_run_summary')}"
    return updated


# ═════════════════════════════════════════════════════════════════════════════
# Group 1 — initial_state
# ═════════════════════════════════════════════════════════════════════════════

def test_initial_state_structure():
    """initial_state() returns a blank state at STAGE_UPLOAD."""
    s = wa.initial_state()
    assert s["stage"] == STAGE_UPLOAD
    assert s["pipeline_ok"] is False
    assert s["students"] == []
    assert s["subjects"] == []
    assert s["_session"] is None
    assert s["_workflow"] is None
    print("test_initial_state_structure: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 2 — process_uploaded_bytes
# ═════════════════════════════════════════════════════════════════════════════

def test_process_pdf_bytes_success():
    """Real sample PDF produces 52 students and 5 subjects."""
    state = wa.process_uploaded_bytes(_pdf_bytes(), filename="sample_marks.pdf")
    assert state["stage"] == STAGE_REVIEW
    assert state["pipeline_ok"] is True
    assert len(state["students"]) == 52
    assert len(state["subjects"]) == 5
    assert state["_session"] is not None
    print("test_process_pdf_bytes_success: PASS")


def test_process_pdf_metadata_extracted():
    """Extracted metadata includes course, semester, branch, exam_name."""
    state = wa.process_uploaded_bytes(_pdf_bytes())
    meta = state["metadata"]
    assert meta.get("course") or meta.get("branch"), f"Metadata missing: {meta}"
    print("test_process_pdf_metadata_extracted: PASS")


def test_process_pdf_abs_in_students():
    """At least one ABS mark is present in the extracted students."""
    state = wa.process_uploaded_bytes(_pdf_bytes())
    all_marks = [
        mark
        for s in state["students"]
        for mark in s.get("marks", {}).values()
    ]
    assert "ABS" in all_marks, "No ABS marks found in extracted students"
    print("test_process_pdf_abs_in_students: PASS")


def test_process_pdf_invalid_bytes():
    """Invalid bytes produce an error state at STAGE_UPLOAD."""
    state = wa.process_uploaded_bytes(b"NOT A PDF", filename="bad.pdf")
    assert state["stage"] == STAGE_UPLOAD
    assert state["pipeline_ok"] is False
    assert len(state["errors"]) > 0
    print("test_process_pdf_invalid_bytes: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 3 — update_student
# ═════════════════════════════════════════════════════════════════════════════

def test_update_student_mark():
    """Teacher can edit a student's mark without affecting original data."""
    state = _state_after_upload()
    first_roll = state["students"][0]["roll_number"]
    first_subj = state["subjects"][0]

    updated = wa.update_student(state, first_roll, {"marks": {first_subj: 20}})
    changed = next(s for s in updated["students"] if s["roll_number"] == first_roll)
    assert changed["marks"][first_subj] == 20
    print("test_update_student_mark: PASS")


def test_update_student_abs_preservation():
    """Setting a mark to 'ABS' via the adapter preserves it as string."""
    state = _state_after_upload()
    first_roll = state["students"][0]["roll_number"]
    first_subj = state["subjects"][0]

    updated = wa.update_student(state, first_roll, {"marks": {first_subj: "ABS"}})
    changed = next(s for s in updated["students"] if s["roll_number"] == first_roll)
    assert changed["marks"][first_subj] == "ABS"
    print("test_update_student_abs_preservation: PASS")


def test_update_student_unknown_roll():
    """Editing a non-existent roll number appends an error."""
    state = _state_after_upload()
    original_error_count = len(state.get("errors", []))
    updated = wa.update_student(state, "NONEXISTENT_ROLL", {"marks": {}})
    assert len(updated.get("errors", [])) > original_error_count
    print("test_update_student_unknown_roll: PASS")


def test_update_student_no_session():
    """update_student on a blank state returns an error."""
    state = wa.initial_state()
    updated = wa.update_student(state, "ANY", {"marks": {}})
    assert len(updated["errors"]) > 0
    print("test_update_student_no_session: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 4 — confirm_review
# ═════════════════════════════════════════════════════════════════════════════

def test_confirm_review_success():
    """Confirmed review transitions to STAGE_DRY_RUN."""
    state = _state_after_upload()
    updated = wa.confirm_review(state, "Dr. Test", exam_id=2, max_marks=30.0)
    assert updated["stage"] == STAGE_DRY_RUN
    assert updated["exam_id"] == 2
    assert updated["max_marks"] == 30.0
    assert updated["_workflow"] is not None
    print("test_confirm_review_success: PASS")


def test_confirm_review_stores_exam_id():
    """exam_id and max_marks are stored in state after confirmation."""
    state = _state_after_upload()
    updated = wa.confirm_review(state, "Dr. Test", exam_id=7, max_marks=50.0)
    assert updated["exam_id"] == 7
    assert updated["max_marks"] == 50.0
    print("test_confirm_review_stores_exam_id: PASS")


def test_confirm_review_invalid_exam_id():
    """Non-integer exam_id returns an error."""
    state = _state_after_upload()
    updated = wa.confirm_review(state, "Dr. Test", exam_id=None, max_marks=30.0)
    assert updated["stage"] != STAGE_DRY_RUN
    assert len(updated["errors"]) > 0
    print("test_confirm_review_invalid_exam_id: PASS")


def test_confirm_review_no_session():
    """confirm_review on blank state returns error."""
    state = wa.initial_state()
    updated = wa.confirm_review(state, "Dr. Test", exam_id=2, max_marks=30.0)
    assert len(updated["errors"]) > 0
    print("test_confirm_review_no_session: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 5 — run_dry_run
# ═════════════════════════════════════════════════════════════════════════════

def test_run_dry_run_success():
    """Passing dry-run transitions to STAGE_IMPORT_READY."""
    state = _state_after_confirm()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_dry_run())):
        updated = wa.run_dry_run(state)
    assert updated["dry_run_done"] is True
    assert updated["dry_run_passed"] is True
    assert updated["stage"] == STAGE_IMPORT_READY
    assert updated["dry_run_summary"]["saved_records"] == 251
    assert updated["dry_run_summary"]["skipped_absent"] == 9
    print("test_run_dry_run_success: PASS")


def test_run_dry_run_failure():
    """Failing dry-run stays at STAGE_DRY_RUN."""
    state = _state_after_confirm()
    backend = {
        "total_records": 260, "saved_records": 200, "skipped_absent": 9,
        "failed_records": 51, "saved": [], "absent": [], "errors": [
            {"record": {"roll_number": "0112AL251001", "subject_code": "BT-101"},
             "reason": "Student not found."}
        ], "dry_run": True, "message": "Dry run complete.",
    }
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        updated = wa.run_dry_run(state)
    assert updated["dry_run_passed"] is False
    assert updated["stage"] == STAGE_DRY_RUN
    print("test_run_dry_run_failure: PASS")


def test_run_dry_run_connection_error():
    """Connection error during dry-run stays at STAGE_DRY_RUN."""
    state = _state_after_confirm()
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("Connection refused")):
        updated = wa.run_dry_run(state)
    assert updated["dry_run_passed"] is False
    assert updated["stage"] == STAGE_DRY_RUN
    print("test_run_dry_run_connection_error: PASS")


def test_run_dry_run_timeout():
    """Timeout during dry-run stays at STAGE_DRY_RUN (not UNCERTAIN)."""
    state = _state_after_confirm()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        updated = wa.run_dry_run(state)
    assert updated["dry_run_passed"] is False
    assert updated["stage"] == STAGE_DRY_RUN   # NOT UNCERTAIN (dry-run is safe)
    print("test_run_dry_run_timeout: PASS")


def test_run_dry_run_no_workflow():
    """run_dry_run on blank state returns error."""
    state = wa.initial_state()
    updated = wa.run_dry_run(state)
    assert len(updated["errors"]) > 0
    print("test_run_dry_run_no_workflow: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 6 — execute_import
# ═════════════════════════════════════════════════════════════════════════════

def test_execute_import_success():
    """Successful import transitions to STAGE_DONE."""
    state = _state_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_import())):
        updated = wa.execute_import(state, confirmed_by="Dr. Test")
    assert updated["stage"] == STAGE_DONE
    assert updated["import_done"] is True
    assert updated["import_summary"]["saved_records"] == 251
    assert updated["import_summary"]["skipped_absent"] == 9
    print("test_execute_import_success: PASS")


def test_execute_import_abs_in_payload():
    """ABS marks are transmitted as the string 'ABS' in the import payload."""
    state = _state_after_dry_run()
    captured = []

    def mock_open(req, timeout=10.0):
        body = json.loads(req.data.decode("utf-8"))
        captured.extend(body["records"])
        return _mock_response(200, _ok_import())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wa.execute_import(state, confirmed_by="Dr. Test")

    abs_records = [r for r in captured if r.get("marks") == "ABS"]
    assert len(abs_records) > 0, "No ABS records in import payload"
    print(f"test_execute_import_abs_in_payload: PASS ({len(abs_records)} ABS)")


def test_execute_import_sends_dry_run_false():
    """Actual import URL contains dry_run=false."""
    state = _state_after_dry_run()
    captured_url = {}

    def mock_open(req, timeout=10.0):
        captured_url["url"] = req.full_url
        return _mock_response(200, _ok_import())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wa.execute_import(state, confirmed_by="Dr. Test")

    assert "dry_run=false" in captured_url["url"]
    print("test_execute_import_sends_dry_run_false: PASS")


def test_execute_import_timeout_sets_uncertain():
    """Timeout during import transitions to STAGE_UNCERTAIN."""
    state = _state_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        updated = wa.execute_import(state, confirmed_by="Dr. Test")
    assert updated["stage"] == STAGE_UNCERTAIN
    print("test_execute_import_timeout_sets_uncertain: PASS")


def test_execute_import_connection_error_sets_uncertain():
    """Connection error during import transitions to STAGE_UNCERTAIN."""
    state = _state_after_dry_run()
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("Connection refused")):
        updated = wa.execute_import(state, confirmed_by="Dr. Test")
    assert updated["stage"] == STAGE_UNCERTAIN
    print("test_execute_import_connection_error_sets_uncertain: PASS")


def test_execute_import_duplicate_blocked():
    """Second execute_import after SUCCESS stays at STAGE_DONE with error."""
    state = _state_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_import())):
        state = wa.execute_import(state, confirmed_by="Dr. Test")
    assert state["stage"] == STAGE_DONE

    # Try again — should be blocked
    updated = wa.execute_import(state, confirmed_by="Dr. Test")
    assert updated["stage"] == STAGE_DONE
    assert len(updated["errors"]) > 0
    assert any("already completed" in e.lower() for e in updated["errors"])
    print("test_execute_import_duplicate_blocked: PASS")


def test_execute_import_partial_failures_preserved():
    """Partial import failures are preserved in error_reasons."""
    state = _state_after_dry_run()
    partial = {
        "total_records": 260, "saved_records": 250, "skipped_absent": 9,
        "failed_records": 1, "saved": [], "absent": [], "errors": [
            {"record": {"roll_number": "0112AL251078", "subject_code": "BT-105"},
             "reason": "UNIQUE constraint failed."}
        ], "dry_run": False,
    }
    with patch("urllib.request.urlopen", return_value=_mock_response(200, partial)):
        updated = wa.execute_import(state, confirmed_by="Dr. Test")

    assert updated["import_summary"]["failed_records"] == 1
    assert any("0112AL251078" in r for r in updated["import_summary"]["error_reasons"])
    print("test_execute_import_partial_failures_preserved: PASS")


def test_execute_import_no_workflow():
    """execute_import on blank state returns error."""
    state = wa.initial_state()
    updated = wa.execute_import(state, confirmed_by="Dr. Test")
    assert len(updated["errors"]) > 0
    print("test_execute_import_no_workflow: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 7 — acknowledge_uncertain
# ═════════════════════════════════════════════════════════════════════════════

def test_acknowledge_uncertain_clears_state():
    """Acknowledging uncertain state resets to STAGE_DRY_RUN."""
    state = _state_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        state = wa.execute_import(state, confirmed_by="Dr. Test")
    assert state["stage"] == STAGE_UNCERTAIN

    updated = wa.acknowledge_uncertain(state, acknowledged_by="Dr. Test",
                                       notes="DB checked: 245 records saved.")
    assert updated["stage"] == STAGE_DRY_RUN
    assert updated["dry_run_done"] is False
    assert updated["dry_run_passed"] is False
    print("test_acknowledge_uncertain_clears_state: PASS")


def test_acknowledge_uncertain_no_workflow():
    """acknowledge_uncertain on blank state returns error."""
    state = wa.initial_state()
    updated = wa.acknowledge_uncertain(state, acknowledged_by="Dr. Test")
    assert len(updated["errors"]) > 0
    print("test_acknowledge_uncertain_no_workflow: PASS")


def test_acknowledge_then_resubmit():
    """Full uncertain → acknowledge → fresh dry-run → import cycle."""
    state = _state_after_dry_run()

    # Timeout on import
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        state = wa.execute_import(state, confirmed_by="Dr. Test")
    assert state["stage"] == STAGE_UNCERTAIN

    # Acknowledge
    state = wa.acknowledge_uncertain(state, "Dr. Test", "DB verified.")
    assert state["stage"] == STAGE_DRY_RUN

    # Fresh dry-run
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_dry_run())):
        state = wa.run_dry_run(state)
    assert state["dry_run_passed"]

    # Re-import
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _ok_import())):
        state = wa.execute_import(state, confirmed_by="Dr. Test")
    assert state["stage"] == STAGE_DONE
    print("test_acknowledge_then_resubmit: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 8 — reset_workflow
# ═════════════════════════════════════════════════════════════════════════════

def test_reset_workflow_returns_initial():
    """reset_workflow returns a blank initial state regardless of current stage."""
    state = _state_after_dry_run()
    assert state["stage"] == STAGE_IMPORT_READY

    reset = wa.reset_workflow(state)
    assert reset["stage"] == STAGE_UPLOAD
    assert reset["_session"] is None
    assert reset["_workflow"] is None
    print("test_reset_workflow_returns_initial: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 9 — Package exports
# ═════════════════════════════════════════════════════════════════════════════

def test_adapter_exported_from_package():
    """All workflow_adapter symbols are importable from the pdf_processing package."""
    from pdf_processing import (
        process_uploaded_bytes,
        update_student,
        confirm_review,
        run_dry_run,
        execute_import,
        acknowledge_uncertain,
        reset_workflow,
        initial_state,
        STAGE_UPLOAD, STAGE_REVIEW, STAGE_DRY_RUN,
        STAGE_IMPORT_READY, STAGE_DONE, STAGE_UNCERTAIN,
    )
    assert process_uploaded_bytes is not None
    print("test_adapter_exported_from_package: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Group 1
        test_initial_state_structure,
        # Group 2
        test_process_pdf_bytes_success,
        test_process_pdf_metadata_extracted,
        test_process_pdf_abs_in_students,
        test_process_pdf_invalid_bytes,
        # Group 3
        test_update_student_mark,
        test_update_student_abs_preservation,
        test_update_student_unknown_roll,
        test_update_student_no_session,
        # Group 4
        test_confirm_review_success,
        test_confirm_review_stores_exam_id,
        test_confirm_review_invalid_exam_id,
        test_confirm_review_no_session,
        # Group 5
        test_run_dry_run_success,
        test_run_dry_run_failure,
        test_run_dry_run_connection_error,
        test_run_dry_run_timeout,
        test_run_dry_run_no_workflow,
        # Group 6
        test_execute_import_success,
        test_execute_import_abs_in_payload,
        test_execute_import_sends_dry_run_false,
        test_execute_import_timeout_sets_uncertain,
        test_execute_import_connection_error_sets_uncertain,
        test_execute_import_duplicate_blocked,
        test_execute_import_partial_failures_preserved,
        test_execute_import_no_workflow,
        # Group 7
        test_acknowledge_uncertain_clears_state,
        test_acknowledge_uncertain_no_workflow,
        test_acknowledge_then_resubmit,
        # Group 8
        test_reset_workflow_returns_initial,
        # Group 9
        test_adapter_exported_from_package,
    ]

    print("=" * 68)
    print("Stage 3, Step 5 — Workflow Adapter Tests")
    print("=" * 68)

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            import traceback
            print(f"FAIL: {t.__name__}: {exc}")
            traceback.print_exc()
            failed += 1

    print("=" * 68)
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED!")
    else:
        print(f"{passed} passed, {failed} FAILED.")
    print("=" * 68)
