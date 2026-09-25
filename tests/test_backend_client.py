"""
Unit and Integration Tests for pdf_processing.backend_client.

Uses mocked HTTP responses (unittest.mock) to test all backend communication scenarios
without modifying production or test databases.
"""
import os
import sys
import json
import io
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_processing.processor import process_pdf
from pdf_processing.review import create_review_session
from pdf_processing.backend_client import submit_marks_import, dry_run_validation


def _make_mock_response(status=200, json_data=None, raw_text=None):
    """Helper to construct a mock urllib HTTP response object."""
    mock_resp = MagicMock()
    mock_resp.status = status
    if json_data is not None:
        body_bytes = json.dumps(json_data).encode("utf-8")
    elif raw_text is not None:
        body_bytes = raw_text.encode("utf-8")
    else:
        body_bytes = b""
    mock_resp.read.return_value = body_bytes
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_successful_dry_run_validation():
    """1. Test successful dry-run validation with mocked HTTP 200 response."""
    mock_backend_response = {
        "total_records": 260,
        "saved_records": 251,
        "skipped_absent": 9,
        "failed_records": 0,
        "saved": [{"mark_id": -1, "roll_number": "0112AL251001", "marks_obtained": 28.0}],
        "absent": [{"roll_number": "0112AL251015", "subject": "BT-103", "reason": "Student was absent (ABS)."}],
        "errors": [],
        "dry_run": True,
        "message": "Dry run complete. No data was saved to the database.",
    }

    dummy_payload = {
        "exam_id": 2,
        "max_marks": 30.0,
        "records": [
            {"roll_number": "0112AL251001", "subject_code": "BT-101", "marks": 28},
            {"roll_number": "0112AL251015", "subject_code": "BT-103", "marks": "ABS"},
        ],
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _make_mock_response(200, mock_backend_response)

        res = dry_run_validation(dummy_payload, base_url="http://localhost:8000")

        # Verify function output
        assert res["success"] is True
        assert res["status_code"] == 200
        assert res["dry_run"] is True
        assert res["total_records"] == 260
        assert res["saved_records"] == 251
        assert res["skipped_absent"] == 9
        assert len(res["absent"]) == 1
        assert len(res["errors"]) == 0

        # Verify correct endpoint URL and parameters called
        called_req = mock_urlopen.call_args[0][0]
        assert called_req.full_url == "http://localhost:8000/marks/import?dry_run=true"
        assert called_req.get_method() == "POST"
        assert called_req.headers["Content-type"] == "application/json"
        assert called_req.headers["Accept"] == "application/json"

    print("test_successful_dry_run_validation: PASS")


def test_abs_preservation_in_request_payload():
    """2. Verify that ABS is transmitted as literal string 'ABS' in the HTTP body."""
    dummy_payload = {
        "exam_id": 2,
        "max_marks": 30.0,
        "records": [
            {"roll_number": "0112AL251015", "subject_code": "BT-103", "marks": "ABS"}
        ],
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _make_mock_response(200, {"saved_records": 0, "skipped_absent": 1})

        dry_run_validation(dummy_payload)

        called_req = mock_urlopen.call_args[0][0]
        sent_body = json.loads(called_req.data.decode("utf-8"))
        assert sent_body["records"][0]["marks"] == "ABS"

    print("test_abs_preservation_in_request_payload: PASS")


def test_invalid_payload_validation():
    """3. Test rejection of invalid payload structures before making network calls."""
    # Missing exam_id
    bad_payload_1 = {"max_marks": 30.0, "records": []}
    res1 = dry_run_validation(bad_payload_1)
    assert res1["success"] is False
    assert res1["error_type"] == "ValidationError"
    assert "exam_id is required" in res1["message"]

    # Records is not a list
    bad_payload_2 = {"exam_id": 2, "max_marks": 30.0, "records": "NOT_A_LIST"}
    res2 = dry_run_validation(bad_payload_2)
    assert res2["success"] is False
    assert res2["error_type"] == "ValidationError"

    # Non-dictionary payload
    bad_payload_3 = "NOT_A_DICT"
    res3 = dry_run_validation(bad_payload_3)
    assert res3["success"] is False
    assert res3["error_type"] == "ValidationError"

    print("test_invalid_payload_validation: PASS")


def test_backend_unavailable_connection_error():
    """4. Test graceful handling when backend server is down / connection refused."""
    dummy_payload = {"exam_id": 2, "max_marks": 30.0, "records": []}

    url_error = urllib.error.URLError(reason="Connection refused")
    with patch("urllib.request.urlopen", side_effect=url_error):
        res = dry_run_validation(dummy_payload, base_url="http://localhost:8000")
        assert res["success"] is False
        assert res["status_code"] is None
        assert res["error_type"] == "ConnectionError"
        assert "Failed to communicate with backend" in res["message"]

    print("test_backend_unavailable_connection_error: PASS")


def test_backend_timeout_handling():
    """5. Test timeout handling when backend takes too long to respond."""
    dummy_payload = {"exam_id": 2, "max_marks": 30.0, "records": []}

    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        res = dry_run_validation(dummy_payload, timeout=2.0)
        assert res["success"] is False
        assert res["status_code"] is None
        assert res["error_type"] == "TimeoutError"
        assert "timed out" in res["message"].lower()

    print("test_backend_timeout_handling: PASS")


def test_backend_http_error_response():
    """6. Test handling of backend HTTP 400/422/500 errors."""
    dummy_payload = {"exam_id": 9999, "max_marks": 30.0, "records": []}

    error_json = {"detail": "Exam with ID 9999 does not exist in the database."}
    http_error = urllib.error.HTTPError(
        url="http://localhost:8000/marks/import?dry_run=true",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=io.BytesIO(json.dumps(error_json).encode("utf-8")),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        res = dry_run_validation(dummy_payload)
        assert res["success"] is False
        assert res["status_code"] == 400
        assert res["error_type"] == "HTTPError"
        assert res["details"] == error_json

    print("test_backend_http_error_response: PASS")


def test_invalid_json_response_handling():
    """7. Test handling when backend returns HTML (e.g. 502 Bad Gateway proxy page)."""
    dummy_payload = {"exam_id": 2, "max_marks": 30.0, "records": []}

    html_resp = _make_mock_response(status=200, raw_text="<html><body>502 Bad Gateway</body></html>")
    with patch("urllib.request.urlopen", return_value=html_resp):
        res = dry_run_validation(dummy_payload)
        assert res["success"] is False
        assert res["error_type"] == "InvalidJSONResponse"
        assert "not valid JSON" in res["message"]

    print("test_invalid_json_response_handling: PASS")


def test_e2e_pipeline_to_dry_run():
    """8. Test end-to-end integration: sample PDF -> review -> dry_run_validation."""
    pdf_path = "pdf_processing/samples/sample_marks.pdf"
    if not os.path.exists(pdf_path):
        pdf_path = "sample_data/college_marks.pdf"

    # Pipeline execution
    pipeline_res = process_pdf(pdf_path)
    session = create_review_session(pipeline_res)
    session.confirm(confirmed_by="Prof. Test", academic_year="2025-2026")

    payload = session.to_backend_payload(exam_id=2, max_marks=30.0)
    assert len(payload["records"]) == 260

    mock_resp_data = {
        "total_records": 260,
        "saved_records": 251,
        "skipped_absent": 9,
        "failed_records": 0,
        "dry_run": True,
        "saved": [{"roll_number": "0112AL251001", "subject_code": "BT-101", "marks_obtained": 28}],
        "absent": [{"roll_number": "0112AL251015", "subject": "BT-103", "reason": "Student was absent (ABS)."}],
        "errors": [],
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _make_mock_response(200, mock_resp_data)

        api_res = dry_run_validation(payload)
        assert api_res["success"] is True
        assert api_res["total_records"] == 260
        assert api_res["skipped_absent"] == 9
        assert api_res["saved_records"] == 251
        assert api_res["failed_records"] == 0

    print("test_e2e_pipeline_to_dry_run: PASS")


if __name__ == "__main__":
    test_successful_dry_run_validation()
    test_abs_preservation_in_request_payload()
    test_invalid_payload_validation()
    test_backend_unavailable_connection_error()
    test_backend_timeout_handling()
    test_backend_http_error_response()
    test_invalid_json_response_handling()
    test_e2e_pipeline_to_dry_run()
    print("\nALL BACKEND CLIENT TESTS PASSED!")
