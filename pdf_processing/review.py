import copy
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from pdf_processing.validator import validate_student_records
from pdf_processing.normalizer import normalize_extracted_data


class TeacherReviewSession:
    """
    Manages the review-and-confirm lifecycle between PDF extraction and backend import.

    Guarantees:
    1. Isolation: Edits are applied only to working draft records; original extracted data
       is preserved untouched for institutional auditability.
    2. Continuous Validation: Every edit re-validates student records and updates errors/warnings.
    3. Gatekeeper: Explicit teacher confirmation is required before records are marked ready for import.
       Confirmation is strictly blocked while critical validation errors remain.
    4. ABS Preservation: Absent marks remain exactly "ABS" throughout editing and confirmation.
    """

    def __init__(self, pipeline_result: Dict[str, Any]):
        """
        Initialize a review session from a process_pdf() result dictionary or Structure A object.

        :param pipeline_result: Dictionary returned by process_pdf() or containing 'structure_a'.
        """
        # Store an immutable snapshot of the original extracted data
        self._original_extracted_data = copy.deepcopy(pipeline_result)

        # Resolve Structure A working draft
        if "structure_a" in pipeline_result and pipeline_result["structure_a"]:
            source_structure_a = pipeline_result["structure_a"]
        elif "metadata" in pipeline_result and "students" in pipeline_result:
            source_structure_a = pipeline_result
        else:
            raise ValueError(
                "Invalid pipeline result: must contain 'structure_a' or 'metadata' and 'students'."
            )

        self._draft: Dict[str, Any] = copy.deepcopy(source_structure_a)

        # Review and confirmation state
        self.is_confirmed: bool = False
        self.ready_for_import: bool = False
        self.confirmed_by: Optional[str] = None
        self.confirmed_at: Optional[str] = None
        self.teacher_notes: Optional[str] = None

        # Re-run validation to establish initial error and warning state
        self._revalidate()

    # ── Internal Revalidation ─────────────────────────────────────────────────
    def _revalidate(self) -> None:
        """Internal helper to validate the working draft and update error/warning state."""
        metadata = self._draft.get("metadata", {})
        subjects = self._draft.get("subjects", [])
        max_marks = metadata.get("maximum_marks", {})
        students = self._draft.get("students", [])

        # Run validator on draft student records
        self._validation_report = validate_student_records(students, subjects, max_marks)

        # Consolidate errors
        self._errors: List[str] = []

        # Check required metadata
        required_meta = ["course", "semester", "branch", "exam_name", "exam_session"]
        for field in required_meta:
            if not metadata.get(field):
                self._errors.append(f"ERR_MISSING_EXAM_METADATA: Required field '{field}' is missing.")

        if not subjects:
            self._errors.append("ERR_SUBJECT_HEADERS_NOT_FOUND: No subjects defined for exam.")

        # Collect student-level errors
        for res in self._validation_report.get("results", []):
            if not res.get("is_valid", True):
                for err in res.get("errors", []):
                    self._errors.append(
                        f"Student {res.get('roll_number', '?')} (Row {res.get('index', '?')}): {err}"
                    )

        # Consolidate warnings
        self._warnings: List[str] = []

        # Academic year warning
        if not metadata.get("academic_year"):
            self._warnings.append(
                "WARN_ACADEMIC_YEAR_ABSENT: Academic year is not set; teacher confirmation required."
            )

        # Absent students warning
        abs_count = sum(
            1 for s in students if any(v == "ABS" for v in s.get("marks", {}).values())
        )
        if abs_count > 0:
            self._warnings.append(
                f"WARN_ABSENT_STUDENTS_DETECTED: {abs_count} student(s) contain 'ABS' mark entries; attendance verification recommended."
            )

    # ── Review-Ready Preview ─────────────────────────────────────────────────
    def get_preview(self) -> Dict[str, Any]:
        """
        Generate a review-ready preview payload for the teacher interface.

        Contains metadata, subjects, student records, validation summary, errors, and warnings.
        """
        metadata = self._draft.get("metadata", {})
        subjects = self._draft.get("subjects", [])
        students = self._draft.get("students", [])

        return {
            "status": "CONFIRMED" if self.is_confirmed else "PENDING_REVIEW",
            "is_confirmed": self.is_confirmed,
            "ready_for_import": self.ready_for_import,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "teacher_notes": self.teacher_notes,
            "metadata": copy.deepcopy(metadata),
            "subjects": copy.deepcopy(subjects),
            "students": copy.deepcopy(students),
            "validation_summary": {
                "total": len(students),
                "valid": self._validation_report["summary"]["valid"],
                "invalid": self._validation_report["summary"]["invalid"],
            },
            "warnings": list(self._warnings),
            "errors": list(self._errors),
            "has_critical_errors": len(self._errors) > 0,
            "original_data_preserved": True,
        }

    # ── Editing Working Records ───────────────────────────────────────────────
    def update_metadata(self, updates: Dict[str, Any]) -> None:
        """
        Update exam-level metadata fields in the working draft.

        Example: session.update_metadata({'academic_year': '2025-2026'})
        Does NOT alter original extracted data.
        """
        if self.is_confirmed:
            raise RuntimeError("Cannot modify metadata after review has been confirmed.")

        for key, value in updates.items():
            self._draft["metadata"][key] = value

        # Re-normalize metadata and revalidate
        normalized = normalize_extracted_data(self._draft["metadata"], self._draft["students"])
        self._draft["metadata"] = normalized["metadata"]
        self._revalidate()

    def update_student(
        self, identifier: Union[int, str], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Edit a student record in the working draft without mutating original extracted data.

        :param identifier: Student roll_number (str) or serial_number (int).
        :param updates: Dictionary of field updates, e.g.:
                        {'student_name': 'NEW NAME', 'marks': {'BT-101': 25, 'BT-103': 'ABS'}}
        :return: Updated student record dictionary.
        """
        if self.is_confirmed:
            raise RuntimeError("Cannot modify student records after review has been confirmed.")

        target_student = None
        for student in self._draft["students"]:
            if (
                isinstance(identifier, str)
                and student.get("roll_number", "").upper() == identifier.strip().upper()
            ) or (
                isinstance(identifier, int)
                and student.get("serial_number") == identifier
            ):
                target_student = student
                break

        if not target_student:
            raise KeyError(f"Student with identifier '{identifier}' not found in review session.")

        # Apply updates
        if "roll_number" in updates:
            target_student["roll_number"] = str(updates["roll_number"]).strip().upper()

        if "student_name" in updates:
            target_student["student_name"] = str(updates["student_name"]).strip().upper()
            target_student["name"] = target_student["student_name"]

        if "marks" in updates and isinstance(updates["marks"], dict):
            for subj, mark_val in updates["marks"].items():
                clean_subj = str(subj).strip().upper()
                if str(mark_val).strip().upper() == "ABS":
                    target_student["marks"][clean_subj] = "ABS"
                else:
                    try:
                        target_student["marks"][clean_subj] = int(mark_val)
                    except (ValueError, TypeError):
                        target_student["marks"][clean_subj] = mark_val

        # Re-normalize students and re-validate
        normalized = normalize_extracted_data(self._draft["metadata"], self._draft["students"])
        self._draft["students"] = normalized["students"]
        self._revalidate()

        return copy.deepcopy(target_student)

    # ── Teacher Confirmation Gate ─────────────────────────────────────────────
    def confirm(
        self,
        confirmed_by: str,
        academic_year: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Confirm the review session, gating readiness for backend import.

        Blocks confirmation if critical validation errors remain.

        :param confirmed_by: Name or ID of the teacher/admin confirming the records.
        :param academic_year: Optional explicit academic year (e.g. '2025-2026').
        :param notes: Optional notes or audit comments.
        :return: Result dictionary: {'success': bool, 'ready_for_import': bool, ...}.
        """
        if not confirmed_by or not str(confirmed_by).strip():
            raise ValueError("confirmed_by (teacher ID or name) is required for confirmation.")

        # Update academic year if supplied during confirmation
        if academic_year:
            self.update_metadata({"academic_year": str(academic_year).strip()})

        # Check for critical blocking errors
        if len(self._errors) > 0 or self._validation_report["summary"]["invalid"] > 0:
            return {
                "success": False,
                "ready_for_import": False,
                "reason": (
                    "Confirmation blocked: Critical validation errors remain. "
                    "Please correct all errors before confirming."
                ),
                "errors": list(self._errors),
                "warnings": list(self._warnings),
            }

        # Transition to confirmed state
        self.is_confirmed = True
        self.ready_for_import = True
        self.confirmed_by = str(confirmed_by).strip()
        self.confirmed_at = datetime.now(timezone.utc).isoformat()
        self.teacher_notes = notes

        return {
            "success": True,
            "ready_for_import": True,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "status": "CONFIRMED",
            "confirmed_data": self.get_confirmed_data(),
        }

    # ── Data Retrieval ────────────────────────────────────────────────────────
    def get_confirmed_data(self) -> Optional[Dict[str, Any]]:
        """
        Return the finalized Structure A document ready for import.

        Returns None if the session has not yet been confirmed by the teacher.
        """
        if not self.ready_for_import or not self.is_confirmed:
            return None

        confirmed_payload = copy.deepcopy(self._draft)
        confirmed_payload["verification_audit"] = {
            "is_confirmed": True,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "teacher_notes": self.teacher_notes,
        }
        return confirmed_payload

    def get_original_data(self) -> Dict[str, Any]:
        """Return an immutable copy of the original extracted data prior to any edits."""
        return copy.deepcopy(self._original_extracted_data)

    def to_backend_payload(
        self, exam_id: Optional[int] = None, max_marks: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Convert confirmed review data into Structure B payload for POST /marks/import.

        Enforces security and workflow gate:
        Raises RuntimeError if the review session has not yet been confirmed by the teacher.
        """
        if not self.is_confirmed or not self.ready_for_import:
            raise RuntimeError(
                "Cannot generate backend payload: Review session has not been confirmed by the teacher. "
                "Explicit teacher confirmation is required before exporting for import."
            )
        from pdf_processing.mapper import map_to_backend_payload

        confirmed = self.get_confirmed_data()
        return map_to_backend_payload(confirmed, exam_id=exam_id, max_marks=max_marks)



def create_review_session(pipeline_result: Dict[str, Any]) -> TeacherReviewSession:
    """
    Factory helper to initialize a TeacherReviewSession from process_pdf() output.

    :param pipeline_result: Output dictionary from process_pdf().
    :return: A new TeacherReviewSession instance.
    """
    return TeacherReviewSession(pipeline_result)
