"""
tests/test_import_workflow.py

Unit tests for pdf_processing.import_workflow.TeacherImportWorkflow.

Covers Stage 3 Steps 3 AND 4:
  - All five confirmation gates
  - Error-handling: connection failure, timeout (dry-run vs actual import)
  - Duplicate import protection (SUCCESS state blocks re-submission)
  - UNCERTAIN state protection (timeout during actual import blocks retry)
  - acknowledge_uncertain_import() escape hatch
  - Backend error reason extraction (invalid exam, student, subject, marks)
  - ABS preservation through actual import payload
  - Partial / mixed success responses
  - Import status lifecycle (NOT_STARTED → IN_PROGRESS → SUCCESS/FAILED/UNCERTAIN)
  - get_status() lifecycle snapshot

All HTTP calls are mocked via unittest.mock — no live backend is required.
No database writes occur in any test.
"""

import json
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.processor import process_pdf
from pdf_processing.review import create_review_session
from pdf_processing.import_workflow import (
    TeacherImportWorkflow,
    ImportWorkflowError,
    DuplicateImportError,
    UncertainImportError,
    STATUS_NOT_STARTED,
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_UNCERTAIN,
    _extract_error_reasons,
)

# ── Sample PDF ────────────────────────────────────────────────────────────────

SAMPLE_PDF = os.path.join(
    os.path.dirname(__file__), "..", "pdf_processing", "samples", "sample_marks.pdf"
)


# ── HTTP mock helpers ─────────────────────────────────────────────────────────

def _mock_response(status=200, json_data=None, raw_text=None):
    """Return a mock urllib response usable as a context manager."""
    mock = MagicMock()
    mock.status = status
    if json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
    elif raw_text is not None:
        body = raw_text.encode("utf-8")
    else:
        body = b""
    mock.read.return_value = body
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


def _dry_run_ok(total=260, saved=251, absent=9, failed=0, errors=None, absent_list=None):
    return {
        "total_records": total,
        "saved_records": saved,
        "skipped_absent": absent,
        "failed_records": failed,
        "saved": [],
        "absent": absent_list or [],
        "errors": errors or [],
        "dry_run": True,
        "message": "Dry run complete. No data was saved to the database.",
    }


def _import_ok(total=260, saved=251, absent=9, failed=0):
    return {
        "total_records": total,
        "saved_records": saved,
        "skipped_absent": absent,
        "failed_records": failed,
        "saved": [],
        "absent": [],
        "errors": [],
        "dry_run": False,
    }


# ── Session fixture ───────────────────────────────────────────────────────────

def _confirmed_session():
    """Build a confirmed TeacherReviewSession from the sample PDF."""
    result = process_pdf(SAMPLE_PDF)
    session = create_review_session(result)
    res = session.confirm(confirmed_by="Dr. Test", academic_year="2025-2026")
    assert res["success"] is True, f"Session confirm failed: {res}"
    return session


def _workflow():
    """Build a TeacherImportWorkflow from a confirmed session."""
    return TeacherImportWorkflow(_confirmed_session())


def _workflow_after_dry_run(extra_dry_kwargs=None):
    """Return a workflow that has already run a successful dry-run."""
    wf = _workflow()
    kwargs = dict(exam_id=2, max_marks=30.0)
    if extra_dry_kwargs:
        kwargs.update(extra_dry_kwargs)
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _dry_run_ok())):
        wf.run_dry_run(**kwargs)
    assert wf.dry_run_passed
    return wf


# ═════════════════════════════════════════════════════════════════════════════
# Group 1 — Construction & initial state
# ═════════════════════════════════════════════════════════════════════════════

def test_construction_requires_review_session():
    """Non-TeacherReviewSession raises TypeError."""
    try:
        TeacherImportWorkflow({"not": "a session"})
        assert False, "Expected TypeError"
    except TypeError as exc:
        assert "TeacherReviewSession" in str(exc)
    print("test_construction_requires_review_session: PASS")


def test_initial_state():
    """Workflow starts with all flags at their zero values."""
    wf = _workflow()
    assert wf.dry_run_executed is False
    assert wf.dry_run_passed is False
    assert wf.dry_run_summary is None
    assert wf.import_status == STATUS_NOT_STARTED
    assert wf.import_executed is False
    assert wf.import_summary is None
    print("test_initial_state: PASS")


def test_get_status_initial():
    """get_status() reports review confirmed, everything else false/not-started."""
    wf = _workflow()
    s = wf.get_status()
    assert s["review_confirmed"] is True
    assert s["dry_run_executed"] is False
    assert s["import_status"] == STATUS_NOT_STARTED
    assert s["total_students"] == 52
    print("test_get_status_initial: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 2 — run_dry_run() gate enforcement
# ═════════════════════════════════════════════════════════════════════════════

def test_dry_run_blocked_unconfirmed_session():
    """run_dry_run raises if review session not confirmed."""
    result = process_pdf(SAMPLE_PDF)
    session = create_review_session(result)
    wf = TeacherImportWorkflow(session)
    try:
        wf.run_dry_run(exam_id=2)
        assert False
    except ImportWorkflowError as e:
        assert "not been confirmed" in str(e).lower()
    print("test_dry_run_blocked_unconfirmed_session: PASS")


def test_dry_run_blocked_none_exam_id():
    """run_dry_run raises when exam_id is None."""
    wf = _workflow()
    try:
        wf.run_dry_run(exam_id=None)
        assert False
    except ImportWorkflowError as e:
        assert "exam_id" in str(e).lower()
    print("test_dry_run_blocked_none_exam_id: PASS")


def test_dry_run_blocked_string_exam_id():
    """run_dry_run raises when exam_id is a string."""
    wf = _workflow()
    try:
        wf.run_dry_run(exam_id="auto")
        assert False
    except ImportWorkflowError as e:
        assert "exam_id" in str(e).lower()
    print("test_dry_run_blocked_string_exam_id: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 3 — run_dry_run() happy path
# ═════════════════════════════════════════════════════════════════════════════

def test_dry_run_success_flags():
    """Successful dry-run sets dry_run_executed and dry_run_passed."""
    wf = _workflow()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _dry_run_ok())):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_executed is True
    assert wf.dry_run_passed is True
    assert summary["dry_run"] is True
    assert summary["dry_run_passed"] is True
    assert summary["total_records"] == 260
    assert summary["saved_records"] == 251
    assert summary["skipped_absent"] == 9
    assert summary["failed_records"] == 0
    assert summary["errors"] == []
    assert summary["error_reasons"] == []
    print("test_dry_run_success_flags: PASS")


def test_dry_run_failure_backend_errors():
    """Backend-reported failed_records causes dry_run_passed=False."""
    wf = _workflow()
    backend = _dry_run_ok(
        saved=240, failed=11,
        errors=[
            {"record": {"roll_number": "0112AL251010", "subject_code": "BT-101"},
             "reason": "Student with roll number '0112AL251010' not found."},
        ]
    )
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert summary["failed_records"] == 11
    assert len(summary["errors"]) == 1
    # Error reasons must be preserved, not discarded
    assert len(summary["error_reasons"]) == 1
    assert "0112AL251010" in summary["error_reasons"][0]
    assert "not found" in summary["error_reasons"][0].lower()
    print("test_dry_run_failure_backend_errors: PASS")


def test_dry_run_correct_url_and_record_count():
    """Dry-run sends dry_run=true in URL and 260 records."""
    wf = _workflow()
    captured = {}

    def mock_open(req, timeout=10.0):
        captured["url"] = req.full_url
        body = json.loads(req.data.decode("utf-8"))
        captured["count"] = len(body["records"])
        captured["exam_id"] = body["exam_id"]
        return _mock_response(200, _dry_run_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert "dry_run=true" in captured["url"]
    assert captured["count"] == 260
    assert captured["exam_id"] == 2
    print("test_dry_run_correct_url_and_record_count: PASS")


def test_dry_run_abs_preserved():
    """ABS marks appear as the string 'ABS' in the dry-run payload."""
    wf = _workflow()
    captured_records = []

    def mock_open(req, timeout=10.0):
        captured_records.extend(json.loads(req.data.decode("utf-8"))["records"])
        return _mock_response(200, _dry_run_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wf.run_dry_run(exam_id=2, max_marks=30.0)

    abs_records = [r for r in captured_records if r.get("marks") == "ABS"]
    assert len(abs_records) > 0, "Expected ≥1 ABS record in dry-run payload"
    print(f"test_dry_run_abs_preserved: PASS ({len(abs_records)} ABS records)")


# ═════════════════════════════════════════════════════════════════════════════
# Group 4 — Dry-run error handling (network failures)
# ═════════════════════════════════════════════════════════════════════════════

def test_dry_run_connection_error():
    """Connection error during dry-run → dry_run_passed=False, no uncertain state."""
    wf = _workflow()
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("Connection refused")):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_executed is True
    assert wf.dry_run_passed is False
    assert summary["dry_run_passed"] is False
    # Import status must NOT be UNCERTAIN — dry-run is safe
    assert wf.import_status == STATUS_NOT_STARTED
    print("test_dry_run_connection_error: PASS")


def test_dry_run_timeout():
    """Timeout during dry-run → dry_run_passed=False; import_status stays NOT_STARTED (safe)."""
    wf = _workflow()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    # Dry-run is always safe — import_status must NOT be UNCERTAIN
    assert wf.import_status == STATUS_NOT_STARTED
    assert summary["error_type"] == "TimeoutError"
    assert len(summary["message"]) > 0
    print("test_dry_run_timeout: PASS")


def test_dry_run_http_400_invalid_exam():
    """HTTP 400 (invalid exam_id) → dry_run_passed=False with clear reason."""
    wf = _workflow()
    error_body = json.dumps({"detail": "Exam with ID 9999 does not exist."}).encode()
    http_err = urllib.error.HTTPError(
        url="http://localhost:8000/marks/import?dry_run=true",
        code=400, msg="Bad Request", hdrs={},
        fp=__import__("io").BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        summary = wf.run_dry_run(exam_id=9999, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert summary["status_code"] == 400
    print("test_dry_run_http_400_invalid_exam: PASS")


def test_dry_run_invalid_json_response():
    """HTML proxy error page → dry_run_passed=False, error_type=InvalidJSONResponse."""
    wf = _workflow()
    html_mock = _mock_response(status=200, raw_text="<html><body>502 Bad Gateway</body></html>")
    with patch("urllib.request.urlopen", return_value=html_mock):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert summary["error_type"] == "InvalidJSONResponse"
    print("test_dry_run_invalid_json_response: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 5 — confirm_and_import() gate enforcement
# ═════════════════════════════════════════════════════════════════════════════

def test_import_blocked_unconfirmed_session():
    result = process_pdf(SAMPLE_PDF)
    session = create_review_session(result)
    wf = TeacherImportWorkflow(session)
    try:
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        assert False
    except ImportWorkflowError as e:
        assert "not been confirmed" in str(e).lower()
    print("test_import_blocked_unconfirmed_session: PASS")


def test_import_blocked_no_dry_run():
    wf = _workflow()
    try:
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        assert False
    except ImportWorkflowError as e:
        assert "dry-run" in str(e).lower()
    print("test_import_blocked_no_dry_run: PASS")


def test_import_blocked_dry_run_failed():
    """Import blocked when dry-run was run but failed."""
    wf = _workflow()
    backend = _dry_run_ok(saved=0, failed=5, errors=[
        {"record": {"roll_number": "ROLL1", "subject_code": "BT-101"},
         "reason": "Exam does not exist."}
    ])
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        wf.run_dry_run(exam_id=999, max_marks=30.0)

    assert wf.dry_run_passed is False
    try:
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        assert False
    except ImportWorkflowError as e:
        assert "did not pass" in str(e).lower()
        # Error reasons must be surfaced to the teacher
        assert "Exam does not exist" in str(e) or "failed record" in str(e).lower()
    print("test_import_blocked_dry_run_failed: PASS")


def test_import_blocked_confirmation_false():
    wf = _workflow_after_dry_run()
    try:
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=False)
        assert False
    except ImportWorkflowError as e:
        assert "import_confirmation" in str(e).lower() or "explicit" in str(e).lower()
    print("test_import_blocked_confirmation_false: PASS")


def test_import_blocked_confirmation_default():
    """Omitting import_confirmation (defaults to False) must also block."""
    wf = _workflow_after_dry_run()
    try:
        wf.confirm_and_import(confirmed_by="Dr. X")
        assert False
    except ImportWorkflowError:
        pass
    print("test_import_blocked_confirmation_default: PASS")


def test_import_blocked_empty_confirmed_by():
    wf = _workflow_after_dry_run()
    try:
        wf.confirm_and_import(confirmed_by="   ", import_confirmation=True)
        assert False
    except ImportWorkflowError as e:
        assert "confirmed_by" in str(e).lower()
    print("test_import_blocked_empty_confirmed_by: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 6 — confirm_and_import() happy path
# ═════════════════════════════════════════════════════════════════════════════

def test_successful_import():
    """Full happy path produces correct summary."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        summary = wf.confirm_and_import(confirmed_by="Dr. Smith", import_confirmation=True)

    assert wf.import_status == STATUS_SUCCESS
    assert wf.import_executed is True
    assert summary["import_status"] == STATUS_SUCCESS
    assert summary["success"] is True
    assert summary["dry_run"] is False
    assert summary["saved_records"] == 251
    assert summary["skipped_absent"] == 9
    assert summary["failed_records"] == 0
    assert summary["confirmed_by"] == "Dr. Smith"
    assert "attempted_at" in summary
    print("test_successful_import: PASS")


def test_import_sends_dry_run_false():
    """Actual import URL must contain dry_run=false, not dry_run=true."""
    wf = _workflow_after_dry_run()
    captured = {}

    def mock_open(req, timeout=10.0):
        captured["url"] = req.full_url
        return _mock_response(200, _import_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert "dry_run=false" in captured["url"]
    assert "dry_run=true" not in captured["url"]
    print("test_import_sends_dry_run_false: PASS")


def test_import_sends_260_records():
    """Actual import payload contains 260 records (52 students × 5 subjects)."""
    wf = _workflow_after_dry_run()
    captured = {}

    def mock_open(req, timeout=10.0):
        body = json.loads(req.data.decode("utf-8"))
        captured["count"] = len(body["records"])
        captured["exam_id"] = body["exam_id"]
        return _mock_response(200, _import_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert captured["count"] == 260
    assert captured["exam_id"] == 2
    print("test_import_sends_260_records: PASS")


def test_import_abs_preserved_in_payload():
    """ABS values are the literal string 'ABS' in the actual import payload."""
    wf = _workflow_after_dry_run()
    captured_records = []

    def mock_open(req, timeout=10.0):
        captured_records.extend(json.loads(req.data.decode("utf-8"))["records"])
        return _mock_response(200, _import_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    abs_records = [r for r in captured_records if r.get("marks") == "ABS"]
    assert len(abs_records) > 0, "No ABS records found in actual import payload"
    print(f"test_import_abs_preserved_in_payload: PASS ({len(abs_records)} ABS)")


# ═════════════════════════════════════════════════════════════════════════════
# Group 7 — Duplicate submission protection
# ═════════════════════════════════════════════════════════════════════════════

def test_duplicate_import_blocked_after_success():
    """A second confirm_and_import() after SUCCESS raises DuplicateImportError."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_SUCCESS

    try:
        # Simulate double-click / repeated submission
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        assert False, "Expected DuplicateImportError"
    except DuplicateImportError as e:
        assert "already completed" in str(e).lower()
    print("test_duplicate_import_blocked_after_success: PASS")


def test_duplicate_blocked_no_network_call():
    """DuplicateImportError is raised before making a network call."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    call_count = {"n": 0}

    def mock_open(req, timeout=10.0):
        call_count["n"] += 1
        return _mock_response(200, _import_ok())

    with patch("urllib.request.urlopen", side_effect=mock_open):
        try:
            wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        except DuplicateImportError:
            pass

    assert call_count["n"] == 0, "Network call was made despite duplicate protection"
    print("test_duplicate_blocked_no_network_call: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 8 — UNCERTAIN state (timeout during actual import)
# ═════════════════════════════════════════════════════════════════════════════

def test_timeout_during_import_sets_uncertain():
    """A TimeoutError during actual import sets import_status=UNCERTAIN."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_UNCERTAIN
    assert summary["import_status"] == STATUS_UNCERTAIN
    assert summary["error_type"] == "TimeoutError"
    # There must be a non-empty human-readable message
    assert len(summary["message"]) > 0
    print("test_timeout_during_import_sets_uncertain: PASS")


def test_connection_error_during_import_sets_uncertain():
    """A connection error during actual import sets import_status=UNCERTAIN."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen",
               side_effect=urllib.error.URLError("Connection refused")):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_UNCERTAIN
    assert summary["import_status"] == STATUS_UNCERTAIN
    print("test_connection_error_during_import_sets_uncertain: PASS")


def test_uncertain_blocks_retry():
    """A second confirm_and_import() while UNCERTAIN raises UncertainImportError."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_UNCERTAIN

    try:
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        assert False, "Expected UncertainImportError"
    except UncertainImportError as e:
        assert "uncertain" in str(e).lower()
        assert "acknowledge" in str(e).lower()
    print("test_uncertain_blocks_retry: PASS")


def test_uncertain_no_network_call_on_retry():
    """UncertainImportError is raised before a second network call is made."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    call_count = {"n": 0}

    def counting_open(req, timeout=10.0):
        call_count["n"] += 1
        return _mock_response(200, _import_ok())

    with patch("urllib.request.urlopen", side_effect=counting_open):
        try:
            wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)
        except UncertainImportError:
            pass

    assert call_count["n"] == 0
    print("test_uncertain_no_network_call_on_retry: PASS")


def test_acknowledge_uncertain_clears_lock():
    """acknowledge_uncertain_import() clears UNCERTAIN and resets for re-submission."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_UNCERTAIN

    wf.acknowledge_uncertain_import(
        acknowledged_by="Dr. X",
        notes="Verified DB manually: 245 records saved before timeout.",
    )

    # Status reset to FAILED; dry-run must be re-run before import
    assert wf.import_status == STATUS_FAILED
    assert wf.dry_run_executed is False
    assert wf.dry_run_passed is False
    assert len(wf._uncertainty_acknowledgements) == 1
    ack = wf._uncertainty_acknowledgements[0]
    assert ack["acknowledged_by"] == "Dr. X"
    assert "245 records" in ack["notes"]
    print("test_acknowledge_uncertain_clears_lock: PASS")


def test_acknowledge_then_resubmit():
    """After acknowledgement and a fresh dry-run, import can be re-submitted."""
    wf = _workflow_after_dry_run()

    # 1. Import times out
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    # 2. Teacher acknowledges
    wf.acknowledge_uncertain_import(acknowledged_by="Dr. X", notes="DB verified.")

    # 3. Fresh dry-run required
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _dry_run_ok())):
        wf.run_dry_run(exam_id=2, max_marks=30.0)

    # 4. Re-import succeeds
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_SUCCESS
    assert summary["success"] is True
    print("test_acknowledge_then_resubmit: PASS")


def test_acknowledge_requires_valid_name():
    """acknowledge_uncertain_import() rejects empty acknowledged_by."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    try:
        wf.acknowledge_uncertain_import(acknowledged_by="")
        assert False
    except ImportWorkflowError as e:
        assert "acknowledged_by" in str(e).lower()
    print("test_acknowledge_requires_valid_name: PASS")


def test_acknowledge_on_non_uncertain_raises():
    """acknowledge_uncertain_import() raises if status is not UNCERTAIN."""
    wf = _workflow()
    try:
        wf.acknowledge_uncertain_import(acknowledged_by="Dr. X")
        assert False
    except ImportWorkflowError as e:
        assert "uncertain" in str(e).lower()
    print("test_acknowledge_on_non_uncertain_raises: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 9 — Backend validation error scenarios
# ═════════════════════════════════════════════════════════════════════════════

def test_invalid_student_roll_number_in_dry_run():
    """Backend errors for unknown roll numbers surface in error_reasons."""
    wf = _workflow()
    backend = _dry_run_ok(
        saved=250, failed=10,
        errors=[
            {"record": {"roll_number": "INVALID001", "subject_code": "BT-101"},
             "reason": "Student with roll number 'INVALID001' not found."},
        ]
    )
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert any("INVALID001" in r for r in summary["error_reasons"])
    assert any("not found" in r.lower() for r in summary["error_reasons"])
    print("test_invalid_student_roll_number_in_dry_run: PASS")


def test_invalid_subject_code_in_dry_run():
    """Backend errors for unknown subject codes surface in error_reasons."""
    wf = _workflow()
    backend = _dry_run_ok(
        saved=250, failed=5,
        errors=[
            {"record": {"roll_number": "0112AL251001", "subject_code": "UNKNOWN-999"},
             "reason": "Subject 'UNKNOWN-999' not found for student's class."},
        ]
    )
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert any("UNKNOWN-999" in r for r in summary["error_reasons"])
    print("test_invalid_subject_code_in_dry_run: PASS")


def test_marks_exceed_max_in_dry_run():
    """Marks-out-of-range backend errors surface in error_reasons."""
    wf = _workflow()
    backend = _dry_run_ok(
        saved=258, failed=2,
        errors=[
            {"record": {"roll_number": "0112AL251001", "subject_code": "BT-101"},
             "reason": "Marks (45) exceed maximum allowed marks (30.0)."},
        ]
    )
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert wf.dry_run_passed is False
    assert any("exceed" in r.lower() for r in summary["error_reasons"])
    print("test_marks_exceed_max_in_dry_run: PASS")


def test_abs_in_backend_absent_response():
    """Backend's absent list is reflected correctly in the dry-run summary."""
    wf = _workflow()
    absent_list = [
        {"roll_number": "0112AL251015", "subject": "BT-103",
         "reason": "Student was absent (ABS). Record skipped."},
        {"roll_number": "0112AL251020", "subject": "BT-202",
         "reason": "Student was absent (ABS). Record skipped."},
    ]
    backend = _dry_run_ok(absent=2, absent_list=absent_list)
    with patch("urllib.request.urlopen", return_value=_mock_response(200, backend)):
        summary = wf.run_dry_run(exam_id=2, max_marks=30.0)

    assert summary["skipped_absent"] == 2
    assert len(summary["absent"]) == 2
    assert summary["absent"][0]["roll_number"] == "0112AL251015"
    print("test_abs_in_backend_absent_response: PASS")


def test_partial_import_failures_preserved():
    """Partial success: failed_records and error reasons are not discarded."""
    wf = _workflow_after_dry_run()
    partial = {
        "total_records": 260,
        "saved_records": 250,
        "skipped_absent": 9,
        "failed_records": 1,
        "saved": [],
        "absent": [],
        "errors": [
            {"record": {"roll_number": "0112AL251078", "subject_code": "BT-105"},
             "reason": "Database insertion error: UNIQUE constraint failed."},
        ],
        "dry_run": False,
    }
    with patch("urllib.request.urlopen", return_value=_mock_response(200, partial)):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    # A 200 response with records saved = SUCCESS (backend completed, partial failure is reported)
    assert summary["failed_records"] == 1
    assert len(summary["errors"]) == 1
    assert len(summary["error_reasons"]) == 1
    assert "0112AL251078" in summary["error_reasons"][0]
    assert "UNIQUE constraint" in summary["error_reasons"][0]
    print("test_partial_import_failures_preserved: PASS")


def test_http_400_during_import_is_failed_not_uncertain():
    """HTTP 400 during actual import → STATUS_FAILED (definitive), not UNCERTAIN."""
    wf = _workflow_after_dry_run()
    error_body = json.dumps({"detail": "Exam with ID 2 does not exist."}).encode()
    http_err = urllib.error.HTTPError(
        url="http://localhost:8000/marks/import?dry_run=false",
        code=400, msg="Bad Request", hdrs={},
        fp=__import__("io").BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_FAILED
    assert summary["import_status"] == STATUS_FAILED
    assert summary["status_code"] == 400
    print("test_http_400_during_import_is_failed_not_uncertain: PASS")


def test_http_400_allows_retry():
    """After a definitive HTTP 400 (FAILED), a fresh dry-run + import is allowed."""
    wf = _workflow_after_dry_run()
    error_body = json.dumps({"detail": "Bad exam."}).encode()
    http_err = urllib.error.HTTPError(
        url="http://localhost:8000/marks/import?dry_run=false",
        code=400, msg="Bad Request", hdrs={},
        fp=__import__("io").BytesIO(error_body),
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_FAILED

    # Re-do dry-run and re-import (exam_id corrected)
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _dry_run_ok())):
        wf.run_dry_run(exam_id=2, max_marks=30.0)

    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        summary = wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    assert wf.import_status == STATUS_SUCCESS
    assert summary["success"] is True
    print("test_http_400_allows_retry: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 10 — _extract_error_reasons helper
# ═════════════════════════════════════════════════════════════════════════════

def test_extract_error_reasons_with_record():
    """Reasons include roll_number and subject_code prefix when available."""
    errors = [
        {"record": {"roll_number": "ROLL1", "subject_code": "BT-101"},
         "reason": "Student not found."},
        {"record": None, "reason": "Exam does not exist."},
        {"record": {}, "reason": "Missing fields."},
    ]
    reasons = _extract_error_reasons(errors)
    assert len(reasons) == 3
    assert "ROLL1" in reasons[0]
    assert "BT-101" in reasons[0]
    assert "Student not found." in reasons[0]
    assert "Exam does not exist." in reasons[1]
    assert "Missing fields." in reasons[2]
    print("test_extract_error_reasons_with_record: PASS")


def test_extract_error_reasons_empty():
    assert _extract_error_reasons([]) == []
    print("test_extract_error_reasons_empty: PASS")


def test_extract_error_reasons_strings():
    """Handles bare strings in the errors list gracefully."""
    reasons = _extract_error_reasons(["Something went wrong", "Another error"])
    assert reasons == ["Something went wrong", "Another error"]
    print("test_extract_error_reasons_strings: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 11 — get_status() lifecycle
# ═════════════════════════════════════════════════════════════════════════════

def test_get_status_after_full_workflow():
    """get_status() reflects completed dry-run and completed import."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", return_value=_mock_response(200, _import_ok())):
        wf.confirm_and_import(confirmed_by="Dr. Smith", import_confirmation=True)

    s = wf.get_status()
    assert s["review_confirmed"] is True
    assert s["dry_run_executed"] is True
    assert s["dry_run_passed"] is True
    assert s["import_status"] == STATUS_SUCCESS
    assert s["import_executed"] is True
    assert s["import_summary"]["success"] is True
    print("test_get_status_after_full_workflow: PASS")


def test_get_status_after_uncertain():
    """get_status() correctly reflects UNCERTAIN state and acknowledgements."""
    wf = _workflow_after_dry_run()
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        wf.confirm_and_import(confirmed_by="Dr. X", import_confirmation=True)

    s = wf.get_status()
    assert s["import_status"] == STATUS_UNCERTAIN
    assert s["import_executed"] is True

    wf.acknowledge_uncertain_import(acknowledged_by="Dr. X", notes="Checked DB.")
    s2 = wf.get_status()
    assert s2["import_status"] == STATUS_FAILED
    assert len(s2["uncertainty_acknowledgements"]) == 1
    print("test_get_status_after_uncertain: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Group 12 — Package exports
# ═════════════════════════════════════════════════════════════════════════════

def test_package_exports():
    """All workflow symbols are importable from the pdf_processing package."""
    from pdf_processing import (
        TeacherImportWorkflow as TIW,
        ImportWorkflowError as IWE,
        DuplicateImportError as DIE,
        UncertainImportError as UIE,
    )
    assert TIW is not None
    assert IWE is not None
    assert DIE is not None
    assert UIE is not None
    print("test_package_exports: PASS")


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Group 1
        test_construction_requires_review_session,
        test_initial_state,
        test_get_status_initial,
        # Group 2
        test_dry_run_blocked_unconfirmed_session,
        test_dry_run_blocked_none_exam_id,
        test_dry_run_blocked_string_exam_id,
        # Group 3
        test_dry_run_success_flags,
        test_dry_run_failure_backend_errors,
        test_dry_run_correct_url_and_record_count,
        test_dry_run_abs_preserved,
        # Group 4
        test_dry_run_connection_error,
        test_dry_run_timeout,
        test_dry_run_http_400_invalid_exam,
        test_dry_run_invalid_json_response,
        # Group 5
        test_import_blocked_unconfirmed_session,
        test_import_blocked_no_dry_run,
        test_import_blocked_dry_run_failed,
        test_import_blocked_confirmation_false,
        test_import_blocked_confirmation_default,
        test_import_blocked_empty_confirmed_by,
        # Group 6
        test_successful_import,
        test_import_sends_dry_run_false,
        test_import_sends_260_records,
        test_import_abs_preserved_in_payload,
        # Group 7
        test_duplicate_import_blocked_after_success,
        test_duplicate_blocked_no_network_call,
        # Group 8
        test_timeout_during_import_sets_uncertain,
        test_connection_error_during_import_sets_uncertain,
        test_uncertain_blocks_retry,
        test_uncertain_no_network_call_on_retry,
        test_acknowledge_uncertain_clears_lock,
        test_acknowledge_then_resubmit,
        test_acknowledge_requires_valid_name,
        test_acknowledge_on_non_uncertain_raises,
        # Group 9
        test_invalid_student_roll_number_in_dry_run,
        test_invalid_subject_code_in_dry_run,
        test_marks_exceed_max_in_dry_run,
        test_abs_in_backend_absent_response,
        test_partial_import_failures_preserved,
        test_http_400_during_import_is_failed_not_uncertain,
        test_http_400_allows_retry,
        # Group 10
        test_extract_error_reasons_with_record,
        test_extract_error_reasons_empty,
        test_extract_error_reasons_strings,
        # Group 11
        test_get_status_after_full_workflow,
        test_get_status_after_uncertain,
        # Group 12
        test_package_exports,
    ]

    print("=" * 68)
    print("Stage 3, Step 4 — Error Handling & Duplicate Protection Tests")
    print("=" * 68)

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"FAIL: {t.__name__}: {exc}")
            failed += 1

    print("=" * 68)
    if failed == 0:
        print(f"ALL {passed} TESTS PASSED!")
    else:
        print(f"{passed} passed, {failed} FAILED.")
    print("=" * 68)
