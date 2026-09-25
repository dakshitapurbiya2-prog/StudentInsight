"""
pdf_processing/workflow_adapter.py — Stateless adapter for the Teacher PDF Import Workflow.

This module is the sole integration boundary between the Streamlit frontend
and the pdf_processing pipeline.

Design:
    - No Streamlit dependency whatsoever.
    - Works entirely with plain Python dicts, lists, and strings.
    - The frontend stores the returned state dict in st.session_state and
      passes it back on each user action.
    - All mutable pipeline objects (TeacherReviewSession, TeacherImportWorkflow)
      are stored inside the state dict so Streamlit's rerun model works correctly.

Adapter state dict keys:
    stage         str   — current workflow stage (see STAGE_* constants)
    pipeline_ok   bool  — True when PDF was processed without fatal errors
    metadata      dict  — extracted exam metadata
    subjects      list  — list of subject codes in column order
    students      list  — list of student dicts (draft, editable)
    errors        list  — critical extraction/validation errors
    warnings      list  — non-critical warnings
    exam_id       int|None
    max_marks     float|None
    dry_run_done  bool
    dry_run_passed bool
    dry_run_summary dict|None
    import_done   bool
    import_summary dict|None
    _session      TeacherReviewSession|None   (internal, do not render)
    _workflow     TeacherImportWorkflow|None  (internal, do not render)
"""

import os
import tempfile
from typing import Any, Dict, List, Optional

from pdf_processing.processor import process_pdf
from pdf_processing.review import create_review_session, TeacherReviewSession
from pdf_processing.import_workflow import (
    TeacherImportWorkflow,
    ImportWorkflowError,
    DuplicateImportError,
    UncertainImportError,
)

# ── Stage constants ────────────────────────────────────────────────────────────
STAGE_UPLOAD = "UPLOAD"                  # No PDF uploaded yet
STAGE_REVIEW = "REVIEW"                  # Extracted; teacher reviewing/editing
STAGE_DRY_RUN = "DRY_RUN"               # Confirmed; dry-run done or pending
STAGE_IMPORT_READY = "IMPORT_READY"     # Dry-run passed; awaiting final confirm
STAGE_DONE = "DONE"                      # Import complete (success or failure)
STAGE_UNCERTAIN = "UNCERTAIN"            # Import ended in uncertain state


def initial_state() -> Dict[str, Any]:
    """Return a blank workflow state dict for a fresh session."""
    return {
        "stage": STAGE_UPLOAD,
        "pipeline_ok": False,
        "metadata": {},
        "subjects": [],
        "students": [],
        "errors": [],
        "warnings": [],
        "exam_id": None,
        "max_marks": None,
        "dry_run_done": False,
        "dry_run_passed": False,
        "dry_run_summary": None,
        "import_done": False,
        "import_summary": None,
        "_session": None,
        "_workflow": None,
    }


# ── Step 1: Process uploaded PDF bytes ────────────────────────────────────────

def process_uploaded_bytes(
    pdf_bytes: bytes,
    filename: str = "upload.pdf",
) -> Dict[str, Any]:
    """
    Run the full pdf_processing pipeline on raw PDF bytes.

    Writes to a temporary file (required by pdfplumber), processes it,
    and returns a fresh adapter state dict.

    :param pdf_bytes: Raw bytes from Streamlit file_uploader.
    :param filename: Original filename (used for display only).
    :returns: Adapter state dict at STAGE_REVIEW if successful,
              or STAGE_UPLOAD with errors if extraction failed.
    """
    state = initial_state()
    state["filename"] = filename

    # Write to a named temp file so pdfplumber can open it
    tmp_path = None
    try:
        suffix = ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        pipeline_result = process_pdf(tmp_path)

    except Exception as exc:
        state["errors"] = [f"PDF extraction failed: {exc}"]
        state["pipeline_ok"] = False
        state["stage"] = STAGE_UPLOAD
        return state

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # Check if text extraction or parsing failed completely
    if not pipeline_result.get("structure_a") and not pipeline_result.get("students"):
        state["errors"] = pipeline_result.get("errors", [pipeline_result.get("error", "Failed to extract marks from PDF.")])
        state["pipeline_ok"] = False
        state["stage"] = STAGE_UPLOAD
        return state

    # Build review session
    try:
        session = create_review_session(pipeline_result)
    except ValueError as exc:
        state["errors"] = [f"Could not create review session: {exc}"]
        state["pipeline_ok"] = False
        state["stage"] = STAGE_UPLOAD
        return state

    preview = session.get_preview()

    state.update({
        "stage": STAGE_REVIEW,
        "pipeline_ok": True,
        "metadata": preview.get("metadata", {}),
        "subjects": preview.get("subjects", []),
        "students": preview.get("students", []),
        "errors": preview.get("errors", []),
        "warnings": preview.get("warnings", []),
        "_session": session,
        "_workflow": None,
    })
    return state


# ── Step 2: Edit a student record ─────────────────────────────────────────────

def update_student(
    state: Dict[str, Any],
    identifier: Any,          # roll_number str OR serial_number int
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply teacher edits to one student record in the review draft.

    :param state: Current adapter state dict.
    :param identifier: Roll number (str) or serial number (int).
    :param updates: Fields to update, e.g. {'marks': {'BT-101': 25}}.
    :returns: Updated state dict.
    """
    session: Optional[TeacherReviewSession] = state.get("_session")
    if session is None:
        state["errors"] = ["No active review session. Please re-upload the PDF."]
        return state

    try:
        session.update_student(identifier, updates)
    except (KeyError, RuntimeError) as exc:
        state["errors"] = list(state.get("errors", [])) + [f"Edit failed: {exc}"]
        return state

    # Refresh state from session
    preview = session.get_preview()
    state.update({
        "students": preview.get("students", []),
        "errors": preview.get("errors", []),
        "warnings": preview.get("warnings", []),
    })
    return state


# ── Step 3: Confirm review ────────────────────────────────────────────────────

def confirm_review(
    state: Dict[str, Any],
    confirmed_by: str,
    exam_id: int,
    max_marks: float,
    academic_year: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Teacher confirms the review, supplies exam_id and max_marks, and
    transitions the workflow to DRY_RUN stage.

    :param confirmed_by: Teacher name or ID.
    :param exam_id: Explicit database exam ID.
    :param max_marks: Maximum marks allowed per subject.
    :param academic_year: Optional academic year string.
    :returns: Updated state dict.
    """
    session: Optional[TeacherReviewSession] = state.get("_session")
    if session is None:
        state["errors"] = ["No active review session."]
        return state

    if not exam_id or not isinstance(exam_id, int):
        state["errors"] = ["A valid numeric Exam ID is required before confirming."]
        return state

    result = session.confirm(
        confirmed_by=confirmed_by,
        academic_year=academic_year,
    )

    if not result.get("success"):
        state["errors"] = result.get("errors", ["Confirmation failed."])
        return state

    # Build import workflow
    workflow = TeacherImportWorkflow(session)

    state.update({
        "stage": STAGE_DRY_RUN,
        "exam_id": exam_id,
        "max_marks": float(max_marks),
        "errors": [],
        "_workflow": workflow,
    })
    return state


# ── Step 4: Run dry-run ───────────────────────────────────────────────────────

def run_dry_run(
    state: Dict[str, Any],
    base_url: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Submit the confirmed payload for backend dry-run validation.

    :returns: Updated state dict. stage → IMPORT_READY if dry-run passed.
    """
    workflow: Optional[TeacherImportWorkflow] = state.get("_workflow")
    if workflow is None:
        state["errors"] = ["No active import workflow. Please confirm review first."]
        return state

    try:
        summary = workflow.run_dry_run(
            exam_id=state["exam_id"],
            max_marks=state.get("max_marks"),
            base_url=base_url,
            timeout=timeout,
        )
    except ImportWorkflowError as exc:
        state["errors"] = [str(exc)]
        return state

    state.update({
        "dry_run_done": True,
        "dry_run_passed": summary.get("dry_run_passed", False),
        "dry_run_summary": summary,
        "stage": STAGE_IMPORT_READY if summary.get("dry_run_passed") else STAGE_DRY_RUN,
    })
    return state


# ── Step 5: Execute actual import ─────────────────────────────────────────────

def execute_import(
    state: Dict[str, Any],
    confirmed_by: str,
    base_url: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Execute the actual database import after all safety gates pass.

    :returns: Updated state dict. stage → DONE or UNCERTAIN.
    """
    workflow: Optional[TeacherImportWorkflow] = state.get("_workflow")
    if workflow is None:
        state["errors"] = ["No active import workflow."]
        return state

    try:
        summary = workflow.confirm_and_import(
            confirmed_by=confirmed_by,
            import_confirmation=True,
            base_url=base_url,
            timeout=timeout,
        )
    except DuplicateImportError as exc:
        state["errors"] = [str(exc)]
        state["stage"] = STAGE_DONE
        return state
    except UncertainImportError as exc:
        state["errors"] = [str(exc)]
        state["stage"] = STAGE_UNCERTAIN
        return state
    except ImportWorkflowError as exc:
        state["errors"] = [str(exc)]
        return state

    from pdf_processing.import_workflow import STATUS_UNCERTAIN
    new_stage = (
        STAGE_UNCERTAIN
        if workflow.import_status == STATUS_UNCERTAIN
        else STAGE_DONE
    )

    state.update({
        "import_done": True,
        "import_summary": summary,
        "stage": new_stage,
        "errors": summary.get("error_reasons", []),
    })
    return state


# ── Step 6: Acknowledge uncertain state ───────────────────────────────────────

def acknowledge_uncertain(
    state: Dict[str, Any],
    acknowledged_by: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Acknowledge an UNCERTAIN import state after manual DB verification.
    Resets the workflow for a fresh dry-run cycle.

    :returns: Updated state dict. stage → DRY_RUN.
    """
    workflow: Optional[TeacherImportWorkflow] = state.get("_workflow")
    if workflow is None:
        state["errors"] = ["No active import workflow."]
        return state

    try:
        workflow.acknowledge_uncertain_import(acknowledged_by=acknowledged_by, notes=notes)
    except ImportWorkflowError as exc:
        state["errors"] = [str(exc)]
        return state

    state.update({
        "stage": STAGE_DRY_RUN,
        "dry_run_done": False,
        "dry_run_passed": False,
        "dry_run_summary": None,
        "errors": [],
    })
    return state


# ── Step 7: Reset ─────────────────────────────────────────────────────────────

def reset_workflow(state: Dict[str, Any]) -> Dict[str, Any]:
    """Discard current workflow and return to the upload stage."""
    return initial_state()
