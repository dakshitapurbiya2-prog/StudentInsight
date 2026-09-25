"""
import_workflow.py — Teacher-Confirmed Backend Import Workflow

Implements a two-stage, gated import workflow that connects the teacher
review session to the backend marks import API.

Workflow stages:
    1. PDF → Extraction → Normalization → TeacherReviewSession
    2. Teacher reviews, edits, and confirms the review session.
    3. run_dry_run()        — Submits payload as dry_run=True; inspects result.
    4. confirm_and_import() — Requires dry_run passed + explicit import confirmation.
                              Submits payload as dry_run=False.

Safety guarantees:
    - Actual DB writes NEVER occur without:
        a) review session confirmed (is_confirmed == True)
        b) dry-run previously executed and passed (dry_run_passed == True)
        c) explicit import_confirmation == True at call time
    - ABS values are preserved through the full chain.
    - No exam_id is ever guessed; caller must supply it explicitly.
    - All network calls are made via backend_client.submit_marks_import().

Duplicate / repeat submission protection:
    - Once confirm_and_import() succeeds (import_status == "SUCCESS"),
      every subsequent call raises ImportWorkflowError immediately without
      making a network call.
    - When an import ends in an UNCERTAIN state (timeout or network error
      mid-request), repeated automatic retries are intentionally blocked.
      The teacher must inspect the backend manually and call
      acknowledge_uncertain_import() to explicitly clear the lock before
      re-submitting.
    - Dry-run calls are always safe to repeat; they never block.

Backend duplicate protection note:
    The backend already performs a SELECT-then-upsert per record, so a
    successfully completed import can be re-submitted and will overwrite
    existing marks with the same values (idempotent at the record level).
    HOWEVER, because the backend commits one record at a time (no wrapping
    transaction), a mid-flight timeout leaves the database in an unknown
    partial state.  The workflow therefore blocks automatic retries after
    a timeout and requires explicit teacher acknowledgement.
    See BACKEND_CHANGES_REQUIRED.md for a recommended backend improvement.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pdf_processing.review import TeacherReviewSession
from pdf_processing.backend_client import submit_marks_import

# ── Import status constants ───────────────────────────────────────────────────

STATUS_NOT_STARTED = "NOT_STARTED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"        # Backend returned a definitive failure (4xx with body)
STATUS_UNCERTAIN = "UNCERTAIN"  # Network timeout / connection loss during actual import


class ImportWorkflowError(Exception):
    """Raised when an import workflow gate is violated."""


class DuplicateImportError(ImportWorkflowError):
    """Raised when a completed import is submitted again without acknowledgement."""


class UncertainImportError(ImportWorkflowError):
    """
    Raised when an import ended in an UNCERTAIN state (timeout mid-request)
    and the teacher has not explicitly acknowledged it.
    """


class TeacherImportWorkflow:
    """
    Orchestrates the two-stage, gated PDF → backend import workflow with
    full error handling and duplicate-submission protection.

    Usage::

        session = create_review_session(process_pdf(path))
        session.confirm(confirmed_by="Dr. Smith", academic_year="2025-2026")

        workflow = TeacherImportWorkflow(session)

        # Stage 1: Dry-run
        dry_result = workflow.run_dry_run(exam_id=2, max_marks=30.0)

        # Stage 2: Actual import (explicit double-confirmation required)
        import_result = workflow.confirm_and_import(
            confirmed_by="Dr. Smith",
            import_confirmation=True,
        )

        # If a timeout left state UNCERTAIN:
        workflow.acknowledge_uncertain_import(acknowledged_by="Dr. Smith",
                                              notes="Verified DB: 251 records saved.")
        import_result = workflow.confirm_and_import(
            confirmed_by="Dr. Smith",
            import_confirmation=True,
        )
    """

    def __init__(self, review_session: TeacherReviewSession):
        """
        :param review_session: A TeacherReviewSession instance.
        """
        if not isinstance(review_session, TeacherReviewSession):
            raise TypeError("review_session must be a TeacherReviewSession instance.")

        self._session: TeacherReviewSession = review_session

        # Workflow parameters (set by run_dry_run, overrideable in confirm_and_import)
        self._exam_id: Optional[int] = None
        self._max_marks: Optional[float] = None
        self._base_url: Optional[str] = None
        self._auth_token: Optional[str] = None

        # Dry-run state
        self.dry_run_executed: bool = False
        self.dry_run_passed: bool = False
        self.dry_run_summary: Optional[Dict[str, Any]] = None

        # Actual import state
        self.import_status: str = STATUS_NOT_STARTED
        self.import_executed: bool = False       # True after any actual import attempt
        self.import_summary: Optional[Dict[str, Any]] = None

        # Uncertainty acknowledgement log
        self._uncertainty_acknowledgements: list = []

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _require_review_confirmed(self) -> None:
        """Gate: review session must be confirmed before any backend call."""
        if not self._session.is_confirmed or not self._session.ready_for_import:
            raise ImportWorkflowError(
                "Cannot proceed: the teacher review session has not been confirmed. "
                "Call session.confirm(confirmed_by=...) before running the workflow."
            )

    def _build_payload(self, exam_id: int, max_marks: Optional[float]) -> Dict[str, Any]:
        """Build Structure B payload via the review session's mapper."""
        return self._session.to_backend_payload(exam_id=exam_id, max_marks=max_marks)

    def _classify_client_response(self, client_response: Dict[str, Any], dry_run: bool) -> str:
        """
        Classify a backend_client response into one of the STATUS_* constants.

        Rules:
        - Network/timeout errors during actual import → UNCERTAIN
        - Network/timeout errors during dry-run → FAILED (safe, no DB write attempted)
        - HTTP error (4xx/5xx with a parseable body) → FAILED
        - JSON parse error or unexpected error → UNCERTAIN (for import), FAILED (for dry-run)
        - success=True → SUCCESS
        - success=False with any other error_type → FAILED
        """
        if client_response.get("success", False):
            return STATUS_SUCCESS

        error_type = client_response.get("error_type", "")

        if not dry_run:
            # During actual import, network loss/timeout means we cannot know if
            # the backend started committing records before the connection dropped.
            uncertain_types = {"TimeoutError", "ConnectionError", "UnexpectedError",
                               "InvalidJSONResponse"}
            if error_type in uncertain_types:
                return STATUS_UNCERTAIN

        return STATUS_FAILED

    def _format_dry_run_summary(self, client_response: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a display-ready dry-run summary dict."""
        errors = client_response.get("errors", [])
        return {
            "dry_run": True,
            "success": client_response.get("success", False),
            "status_code": client_response.get("status_code"),
            "total_records": client_response.get("total_records", 0),
            "saved_records": client_response.get("saved_records", 0),
            "skipped_absent": client_response.get("skipped_absent", 0),
            "failed_records": client_response.get("failed_records", 0),
            "errors": errors,
            "absent": client_response.get("absent", []),
            "error_type": client_response.get("error_type"),
            "message": self._extract_message(client_response, dry_run=True),
            # Surface backend error reasons as a flat list for easy display
            "error_reasons": _extract_error_reasons(errors),
            "raw_client_response": client_response,
        }

    def _format_import_summary(
        self, client_response: Dict[str, Any], confirmed_by: str, import_status: str
    ) -> Dict[str, Any]:
        """Produce a display-ready actual-import summary dict."""
        errors = client_response.get("errors", [])
        return {
            "dry_run": False,
            "import_status": import_status,
            "success": client_response.get("success", False),
            "status_code": client_response.get("status_code"),
            "total_records": client_response.get("total_records", 0),
            "saved_records": client_response.get("saved_records", 0),
            "skipped_absent": client_response.get("skipped_absent", 0),
            "failed_records": client_response.get("failed_records", 0),
            "errors": errors,
            "absent": client_response.get("absent", []),
            "error_type": client_response.get("error_type"),
            "message": self._extract_message(client_response, dry_run=False),
            # Surface backend error reasons as a flat list for easy display
            "error_reasons": _extract_error_reasons(errors),
            "confirmed_by": confirmed_by,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "raw_client_response": client_response,
        }

    @staticmethod
    def _extract_message(client_response: Dict[str, Any], dry_run: bool) -> str:
        """
        Extract a human-readable status message from the client response.
        Preserves backend-provided messages verbatim when available.
        """
        # 1. Use backend message if present
        data = client_response.get("data") or {}
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])

        # 2. Use client-level message (connection/timeout errors)
        if client_response.get("message"):
            return str(client_response["message"])

        # 3. Synthesise from success flag
        if client_response.get("success", False):
            return (
                "Dry run complete. No data was saved to the database."
                if dry_run
                else "Import completed successfully."
            )

        error_type = client_response.get("error_type", "UnknownError")
        if error_type == "TimeoutError":
            return (
                "The request timed out. For an actual import, the database state is UNCERTAIN — "
                "the backend may have saved some records before the connection was lost. "
                "Do NOT retry automatically. Verify the database manually before re-submitting."
                if not dry_run
                else "The dry-run request timed out. No data was written. You may retry the dry-run."
            )
        if error_type == "ConnectionError":
            return (
                "Could not reach the backend server. "
                + ("The database state is UNCERTAIN." if not dry_run else "No data was written.")
            )
        return "Import failed." if not dry_run else "Dry run failed."

    # ── Stage 1: Dry-Run Validation ─────────────────────────────────────────

    def run_dry_run(
        self,
        exam_id: int,
        max_marks: Optional[float] = None,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Submit the confirmed review payload for dry-run validation.

        Sends ``POST /marks/import?dry_run=true`` and stores the result.
        No database writes are performed.  Safe to call multiple times.

        :param exam_id: Required exam ID (must be an explicit integer).
        :param max_marks: Maximum marks per subject (backend default used if None).
        :param base_url: Backend base URL override.
        :param auth_token: Optional Bearer token.
        :param timeout: HTTP timeout in seconds.
        :returns: Dry-run summary dict.
        :raises ImportWorkflowError: If session not confirmed, or exam_id invalid.
        """
        self._require_review_confirmed()

        if exam_id is None or not isinstance(exam_id, int):
            raise ImportWorkflowError(
                "exam_id must be an explicit integer. "
                "Do not guess or derive exam_id from the PDF."
            )

        # Persist parameters for later use in confirm_and_import
        self._exam_id = exam_id
        self._max_marks = max_marks
        self._base_url = base_url
        self._auth_token = auth_token

        payload = self._build_payload(exam_id=exam_id, max_marks=max_marks)

        client_response = submit_marks_import(
            payload=payload,
            base_url=base_url,
            dry_run=True,
            timeout=timeout,
            auth_token=auth_token,
        )

        self.dry_run_executed = True
        self.dry_run_summary = self._format_dry_run_summary(client_response)

        # Dry-run passes only when the network call succeeded AND the backend
        # reports zero failed_records and zero validation errors.
        network_ok = client_response.get("success", False)
        backend_failed = client_response.get("failed_records", 0)
        backend_errors = client_response.get("errors", [])

        self.dry_run_passed = (
            network_ok
            and int(backend_failed) == 0
            and len(backend_errors) == 0
        )

        self.dry_run_summary["dry_run_passed"] = self.dry_run_passed
        return self.dry_run_summary

    # ── Stage 2: Actual Import ──────────────────────────────────────────────

    def confirm_and_import(
        self,
        confirmed_by: str,
        import_confirmation: bool = False,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        exam_id: Optional[int] = None,
        max_marks: Optional[float] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """
        Execute the actual backend import after all safety gates are satisfied.

        Sends ``POST /marks/import?dry_run=false`` and writes to the database.

        Gates (ALL must pass in order):
            1. Review session confirmed.
            2. confirmed_by is non-empty.
            3. Dry-run was executed.
            4. Dry-run passed (zero backend failures).
            5. import_confirmation is explicitly True.
            6. No prior successful import (duplicate protection).
            7. No UNCERTAIN import awaiting acknowledgement.

        :param confirmed_by: Name/ID of the teacher authorising the DB write.
        :param import_confirmation: Must be explicitly True to proceed.
        :param base_url: Backend base URL override.
        :param auth_token: Optional Bearer token.
        :param exam_id: Override exam_id (uses dry-run exam_id if omitted).
        :param max_marks: Override max_marks (uses dry-run value if omitted).
        :param timeout: HTTP timeout in seconds.
        :returns: Import summary dict.
        :raises DuplicateImportError: If a successful import already completed.
        :raises UncertainImportError: If a previous import timed out and has not
                                      been acknowledged.
        :raises ImportWorkflowError: If any other safety gate is violated.
        """
        # Gate 1
        self._require_review_confirmed()

        # Gate 2
        if not confirmed_by or not str(confirmed_by).strip():
            raise ImportWorkflowError(
                "confirmed_by (teacher name or ID) is required to authorise the import."
            )

        # Gate 3
        if not self.dry_run_executed:
            raise ImportWorkflowError(
                "Cannot import: dry-run validation has not been executed. "
                "Call run_dry_run() before confirm_and_import()."
            )

        # Gate 4
        if not self.dry_run_passed:
            failed = (
                self.dry_run_summary.get("failed_records", "?")
                if self.dry_run_summary else "?"
            )
            errors = (
                self.dry_run_summary.get("errors", [])
                if self.dry_run_summary else []
            )
            reasons = _extract_error_reasons(errors)
            detail = "\n".join(f"  - {r}" for r in reasons[:5])
            if len(reasons) > 5:
                detail += f"\n  ... and {len(reasons) - 5} more."
            raise ImportWorkflowError(
                f"Cannot import: dry-run validation did not pass "
                f"({failed} failed record(s)). "
                f"Resolve the following errors before importing:\n{detail}"
            )

        # Gate 5
        if import_confirmation is not True:
            raise ImportWorkflowError(
                "Cannot import: explicit import confirmation is required. "
                "Set import_confirmation=True to authorise the database write."
            )

        # Gate 6 — Duplicate protection
        if self.import_status == STATUS_SUCCESS:
            raise DuplicateImportError(
                "This import has already completed successfully. "
                "Submitting again would re-import the same data. "
                "If you intend to update existing records, verify the current database "
                "state and use the backend upsert behaviour intentionally."
            )

        # Gate 7 — Uncertain import protection
        if self.import_status == STATUS_UNCERTAIN:
            raise UncertainImportError(
                "The previous import attempt ended in an UNCERTAIN state (timeout or "
                "connection loss). The backend may have saved some records already. "
                "Do NOT retry automatically. Manually verify the database state, then "
                "call acknowledge_uncertain_import() to clear this lock before re-submitting."
            )

        # Resolve parameters
        resolved_exam_id = exam_id if exam_id is not None else self._exam_id
        resolved_max_marks = max_marks if max_marks is not None else self._max_marks
        resolved_base_url = base_url or self._base_url
        resolved_auth_token = auth_token or self._auth_token

        if resolved_exam_id is None:
            raise ImportWorkflowError(
                "exam_id is required for actual import. "
                "Provide it via the exam_id parameter or run run_dry_run() first."
            )

        payload = self._build_payload(
            exam_id=resolved_exam_id, max_marks=resolved_max_marks
        )

        # Mark as in-progress before the network call so a crash mid-call is
        # detectable if the object is inspected afterwards.
        self.import_status = STATUS_IN_PROGRESS
        self.import_executed = True

        client_response = submit_marks_import(
            payload=payload,
            base_url=resolved_base_url,
            dry_run=False,
            timeout=timeout,
            auth_token=resolved_auth_token,
        )

        # Classify the outcome
        self.import_status = self._classify_client_response(
            client_response, dry_run=False
        )

        self.import_summary = self._format_import_summary(
            client_response=client_response,
            confirmed_by=str(confirmed_by).strip(),
            import_status=self.import_status,
        )

        return self.import_summary

    # ── Uncertainty Acknowledgement ─────────────────────────────────────────

    def acknowledge_uncertain_import(
        self,
        acknowledged_by: str,
        notes: str = "",
    ) -> None:
        """
        Explicitly acknowledge an UNCERTAIN import outcome and clear the
        re-submission lock.

        Call this ONLY after manually verifying the database state.  The
        acknowledgement is logged with a timestamp and the provided notes.

        :param acknowledged_by: Name/ID of the person who checked the DB.
        :param notes: Free-text description of what was found in the database.
        :raises ImportWorkflowError: If the current import status is not UNCERTAIN.
        """
        if self.import_status != STATUS_UNCERTAIN:
            raise ImportWorkflowError(
                f"Cannot acknowledge: current import status is '{self.import_status}', "
                f"not '{STATUS_UNCERTAIN}'. Acknowledgement is only required after "
                "a timeout or connection-loss during an actual import."
            )

        if not acknowledged_by or not str(acknowledged_by).strip():
            raise ImportWorkflowError(
                "acknowledged_by (name or ID) is required for the acknowledgement log."
            )

        entry = {
            "acknowledged_by": str(acknowledged_by).strip(),
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "previous_status": STATUS_UNCERTAIN,
            "notes": notes or "(no notes provided)",
        }
        self._uncertainty_acknowledgements.append(entry)

        # Reset to FAILED so the teacher can re-submit with a fresh dry-run cycle
        self.import_status = STATUS_FAILED
        self.dry_run_executed = False
        self.dry_run_passed = False
        self.dry_run_summary = None

    # ── Workflow State Inspection ────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """
        Return a snapshot of the current workflow state.

        Useful for displaying workflow progress in a teacher-facing UI.
        """
        preview = self._session.get_preview()
        return {
            "review_confirmed": self._session.is_confirmed,
            "ready_for_import": self._session.ready_for_import,
            "confirmed_by": self._session.confirmed_by,
            "confirmed_at": self._session.confirmed_at,
            "dry_run_executed": self.dry_run_executed,
            "dry_run_passed": self.dry_run_passed,
            "dry_run_summary": self.dry_run_summary,
            "import_status": self.import_status,
            "import_executed": self.import_executed,
            "import_summary": self.import_summary,
            "uncertainty_acknowledgements": list(self._uncertainty_acknowledgements),
            "review_errors": preview.get("errors", []),
            "review_warnings": preview.get("warnings", []),
            "total_students": len(self._session._draft.get("students", [])),
        }


# ── Module-level helpers ──────────────────────────────────────────────────────

def _extract_error_reasons(errors: list) -> list:
    """
    Flatten backend error list into a list of human-readable reason strings.

    Backend errors are dicts:  {"record": {...}, "reason": "..."}
    This function extracts the "reason" field for each entry, preserving
    the roll_number when available so the teacher knows which record failed.

    Reasons are never silently discarded.
    """
    reasons = []
    for err in errors:
        if isinstance(err, dict):
            reason = err.get("reason", "Unknown error")
            record = err.get("record")
            if record and isinstance(record, dict):
                roll = record.get("roll_number", "")
                subj = record.get("subject_code") or record.get("subject", "")
                prefix_parts = [p for p in [roll, subj] if p]
                prefix = f"[{', '.join(prefix_parts)}] " if prefix_parts else ""
                reasons.append(f"{prefix}{reason}")
            else:
                reasons.append(str(reason))
        else:
            reasons.append(str(err))
    return reasons
