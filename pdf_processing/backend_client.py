import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_BACKEND_URL = os.environ.get(
    "STUDENTINSIGHT_BACKEND_URL",
    os.environ.get("BACKEND_BASE_URL", "http://localhost:8000"),
)


class BackendAPIError(Exception):
    """Custom exception raised when backend communication fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


def submit_marks_import(
    payload: Dict[str, Any],
    base_url: Optional[str] = None,
    dry_run: bool = True,
    timeout: float = 10.0,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit a prepared Structure B marksheet payload to the backend import endpoint:
    `POST /marks/import?dry_run=<bool>`.

    Features & Safety:
    - Default `dry_run=True` ensures non-destructive dry-run validation by default.
    - Requires explicit `exam_id` (rejects None).
    - Preserves `"ABS"` string tokens.
    - Handles connection errors, timeouts, HTTP errors, and non-JSON responses gracefully.

    :param payload: Structure B dictionary: {'exam_id': int, 'max_marks': float, 'records': [...]}.
    :param base_url: Base URL of backend service (defaults to http://localhost:8000).
    :param dry_run: If True, performs dry-run validation without database writes. Default: True.
    :param timeout: HTTP request timeout in seconds. Default: 10.0.
    :param auth_token: Optional Bearer JWT token if authentication is enabled.
    :return: A standardized response dictionary with 'success', 'status_code', 'data', 'errors', etc.
    """
    # ── 1. Validate Payload Contract ─────────────────────────────────────────
    if not isinstance(payload, dict):
        return {
            "success": False,
            "status_code": None,
            "error_type": "ValidationError",
            "message": "Payload must be a dictionary conforming to Structure B.",
            "dry_run": dry_run,
        }

    if payload.get("exam_id") is None:
        return {
            "success": False,
            "status_code": None,
            "error_type": "ValidationError",
            "message": "exam_id is required in payload and cannot be None.",
            "dry_run": dry_run,
        }

    if "records" not in payload or not isinstance(payload["records"], list):
        return {
            "success": False,
            "status_code": None,
            "error_type": "ValidationError",
            "message": "payload['records'] must be a list of mark items.",
            "dry_run": dry_run,
        }

    # ── 2. Construct Endpoint URL & Request ───────────────────────────────────
    resolved_base_url = (base_url or DEFAULT_BACKEND_URL).rstrip("/")
    query_param = "true" if dry_run else "false"
    endpoint_url = f"{resolved_base_url}/marks/import?dry_run={query_param}"

    # Serialize JSON payload
    try:
        json_bytes = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError) as err:
        return {
            "success": False,
            "status_code": None,
            "error_type": "SerializationError",
            "message": f"Failed to serialize payload to JSON: {err}",
            "dry_run": dry_run,
        }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "StudentInsight-PDFProcessing/1.0",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token.strip()}"

    req = urllib.request.Request(
        url=endpoint_url,
        data=json_bytes,
        headers=headers,
        method="POST",
    )

    # ── 3. Execute HTTP Call with Exception Handling ─────────────────────────
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            raw_body = response.read().decode("utf-8")

            try:
                response_data = json.loads(raw_body)
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "status_code": status_code,
                    "error_type": "InvalidJSONResponse",
                    "message": "Backend response is not valid JSON.",
                    "raw_response": raw_body,
                    "dry_run": dry_run,
                }

            return {
                "success": True,
                "status_code": status_code,
                "dry_run": dry_run,
                "data": response_data,
                "total_records": response_data.get("total_records", len(payload["records"])),
                "saved_records": response_data.get("saved_records", 0),
                "skipped_absent": response_data.get("skipped_absent", 0),
                "failed_records": response_data.get("failed_records", 0),
                "errors": response_data.get("errors", []),
                "absent": response_data.get("absent", []),
            }

    except urllib.error.HTTPError as http_err:
        status_code = http_err.code
        try:
            error_body = http_err.read().decode("utf-8")
            error_data = json.loads(error_body)
        except Exception:
            error_data = error_body if "error_body" in locals() else str(http_err)

        return {
            "success": False,
            "status_code": status_code,
            "error_type": "HTTPError",
            "message": f"Backend returned HTTP {status_code}: {http_err.reason}",
            "details": error_data,
            "dry_run": dry_run,
        }

    except urllib.error.URLError as url_err:
        reason_str = str(url_err.reason)
        is_timeout = "timed out" in reason_str.lower()
        error_type = "TimeoutError" if is_timeout else "ConnectionError"

        return {
            "success": False,
            "status_code": None,
            "error_type": error_type,
            "message": f"Failed to communicate with backend ({error_type}): {reason_str}",
            "endpoint": endpoint_url,
            "dry_run": dry_run,
        }

    except TimeoutError:
        return {
            "success": False,
            "status_code": None,
            "error_type": "TimeoutError",
            "message": f"Request to backend timed out after {timeout} seconds.",
            "endpoint": endpoint_url,
            "dry_run": dry_run,
        }

    except Exception as err:
        return {
            "success": False,
            "status_code": None,
            "error_type": "UnexpectedError",
            "message": f"Unexpected error during backend API call: {err}",
            "dry_run": dry_run,
        }


def dry_run_validation(
    payload: Dict[str, Any],
    base_url: Optional[str] = None,
    timeout: float = 10.0,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper to submit a payload for dry-run validation (`dry_run=True`).

    Guarantees that no database writes will be executed by the backend.
    """
    return submit_marks_import(
        payload=payload,
        base_url=base_url,
        dry_run=True,
        timeout=timeout,
        auth_token=auth_token,
    )
