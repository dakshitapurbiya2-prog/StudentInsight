"""
app/frontend/dashboards/pdf_upload_tab.py

Streamlit Tab 3 — Real PDF Import Workflow for the Teacher Dashboard.

Replaces the mock-data placeholder in teacher_dashboard.py.

Integration boundary:
    This module calls pdf_processing.workflow_adapter (pure Python, no Streamlit)
    and manages all Streamlit UI state in st.session_state["pdf_wf"].

Session state key: "pdf_wf"
    Contains the adapter state dict (see workflow_adapter.py for schema).

No other session_state keys are created or modified by this module.

Requirements satisfied:
    ✓ ABS preserved exactly — adapter never coerces it
    ✓ No auto-save during upload or preview
    ✓ Critical errors block confirmation
    ✓ Dry-run required before actual import
    ✓ Actual import requires explicit second confirmation checkbox
    ✓ Duplicate submission blocked (DuplicateImportError)
    ✓ Uncertain state shown with clear warning and acknowledgement form
    ✓ All backend error reasons displayed to the teacher
    ✓ Loading spinners on every network call
    ✓ Backend contract unchanged
"""

import streamlit as st
import pandas as pd
import os

import pdf_processing.workflow_adapter as wf_adapter
from pdf_processing.workflow_adapter import (
    STAGE_UPLOAD,
    STAGE_REVIEW,
    STAGE_DRY_RUN,
    STAGE_IMPORT_READY,
    STAGE_DONE,
    STAGE_UNCERTAIN,
)

# ── Session key ───────────────────────────────────────────────────────────────
_WF_KEY = "pdf_wf"
_BACKEND_URL = os.environ.get("STUDENTINSIGHT_BACKEND_URL", "http://localhost:8000")


def _state() -> dict:
    """Return (or initialise) the workflow state from session_state."""
    if _WF_KEY not in st.session_state:
        st.session_state[_WF_KEY] = wf_adapter.initial_state()
    return st.session_state[_WF_KEY]


def _set_state(new_state: dict) -> None:
    st.session_state[_WF_KEY] = new_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _show_errors(errors: list) -> None:
    for err in errors:
        st.error(f"🚫 {err}")


def _show_warnings(warnings: list) -> None:
    for w in warnings:
        st.warning(f"⚠️ {w}")


def _students_to_df(students: list, subjects: list) -> pd.DataFrame:
    """Convert student dicts to a wide DataFrame for display/editing."""
    rows = []
    for s in students:
        row = {
            "Roll Number": s.get("roll_number", ""),
            "Student Name": s.get("student_name", s.get("name", "")),
        }
        for subj in subjects:
            mark = s.get("marks", {}).get(subj, "")
            row[subj] = mark
        rows.append(row)
    return pd.DataFrame(rows)


def _render_metadata(metadata: dict) -> None:
    """Display extracted exam metadata in a compact grid."""
    cols = st.columns(3)
    fields = [
        ("Institution", "institution_name"),
        ("Course", "course"),
        ("Semester", "semester"),
        ("Branch", "branch"),
        ("Exam", "exam_name"),
        ("Session", "exam_session"),
    ]
    for i, (label, key) in enumerate(fields):
        cols[i % 3].markdown(f"**{label}:** {metadata.get(key, '—')}")


def _render_dry_run_summary(summary: dict) -> None:
    """Display dry-run results with counts and per-record errors."""
    if not summary:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Records", summary.get("total_records", 0))
    c2.metric("Would Save", summary.get("saved_records", 0))
    c3.metric("Absent (ABS)", summary.get("skipped_absent", 0))
    c4.metric("Would Fail", summary.get("failed_records", 0))

    if summary.get("error_reasons"):
        st.markdown("**Records that would fail:**")
        for reason in summary["error_reasons"]:
            st.error(f"🚫 {reason}")

    if summary.get("absent"):
        with st.expander(f"Absent records ({len(summary['absent'])})"):
            for a in summary["absent"]:
                st.info(
                    f"Roll: {a.get('roll_number', '?')} | "
                    f"Subject: {a.get('subject', a.get('subject_code', '?'))} | "
                    f"{a.get('reason', 'Absent')}"
                )


def _render_import_summary(summary: dict) -> None:
    """Display actual import results with counts and per-record details."""
    if not summary:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", summary.get("total_records", 0))
    c2.metric("Saved", summary.get("saved_records", 0))
    c3.metric("Absent (ABS)", summary.get("skipped_absent", 0))
    c4.metric("Failed", summary.get("failed_records", 0))

    if summary.get("error_reasons"):
        st.markdown("**Records that failed:**")
        for reason in summary["error_reasons"]:
            st.error(f"🚫 {reason}")


# ── Stage renderers ───────────────────────────────────────────────────────────

def _render_upload_stage(teacher_name: str) -> None:
    """Stage 1 — PDF Upload."""
    st.info("Upload a marksheet PDF to begin. No data is saved until you explicitly confirm.")

    uploaded = st.file_uploader("Choose a PDF file", type=["pdf"], key="pdf_uploader")
    if uploaded is not None:
        with st.spinner("Extracting marks from PDF…"):
            new_state = wf_adapter.process_uploaded_bytes(
                pdf_bytes=uploaded.read(),
                filename=uploaded.name,
            )
        _set_state(new_state)

        if new_state.get("pipeline_ok"):
            st.success(f"✅ Extracted {len(new_state['students'])} students, "
                       f"{len(new_state['subjects'])} subjects.")
        else:
            _show_errors(new_state.get("errors", ["Unknown extraction error."]))

        st.rerun()


def _render_review_stage(teacher_name: str) -> None:
    """Stage 2 — Teacher reviews extracted data and optionally edits records."""
    state = _state()

    st.markdown("#### 📋 Extracted Exam Metadata")
    _render_metadata(state.get("metadata", {}))

    st.divider()

    # Errors and warnings
    if state.get("errors"):
        st.markdown("**❌ Validation Errors (must fix before confirming):**")
        _show_errors(state["errors"])
    if state.get("warnings"):
        _show_warnings(state["warnings"])

    st.markdown(f"#### 📊 Extracted Records — {len(state['students'])} students, "
                f"{len(state['subjects'])} subjects")

    # Display-only table (editing via inline form below)
    df = _students_to_df(state["students"], state["subjects"])
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Inline edit form
    with st.expander("✏️ Edit a student record"):
        edit_roll = st.text_input("Roll Number to edit", key="edit_roll")
        if edit_roll:
            # Find the student
            target = next(
                (s for s in state["students"]
                 if s.get("roll_number", "").upper() == edit_roll.strip().upper()),
                None
            )
            if target:
                st.markdown(f"**Student:** {target.get('student_name', '')}")
                new_marks = {}
                mark_cols = st.columns(len(state["subjects"]))
                for i, subj in enumerate(state["subjects"]):
                    current = target.get("marks", {}).get(subj, "")
                    new_val = mark_cols[i].text_input(
                        subj, value=str(current), key=f"edit_{edit_roll}_{subj}"
                    )
                    if new_val.strip().upper() == "ABS":
                        new_marks[subj] = "ABS"
                    else:
                        try:
                            new_marks[subj] = int(new_val)
                        except ValueError:
                            new_marks[subj] = new_val

                if st.button("Apply Edits", key="apply_edits"):
                    updated = wf_adapter.update_student(
                        state, edit_roll.strip().upper(), {"marks": new_marks}
                    )
                    _set_state(updated)
                    st.success("Edits applied.")
                    st.rerun()
            else:
                st.warning(f"Roll number '{edit_roll}' not found.")

    st.divider()
    st.markdown("#### ✅ Confirm Review")
    st.caption("Provide the exam details before confirming. No data is saved yet.")

    col_exam, col_marks, col_year = st.columns(3)
    exam_id_input = col_exam.number_input(
        "Exam ID *", min_value=1, step=1, value=1, key="exam_id_input"
    )
    max_marks_input = col_marks.number_input(
        "Max Marks *", min_value=1.0, step=0.5, value=30.0, key="max_marks_input"
    )
    academic_year_input = col_year.text_input(
        "Academic Year (optional)", placeholder="e.g. 2025-2026", key="academic_year_input"
    )

    has_errors = bool(state.get("errors"))
    if has_errors:
        st.error("Fix the validation errors above before confirming.")

    if st.button("Confirm Review & Proceed to Validation",
                 disabled=has_errors, type="primary", key="confirm_review_btn"):
        updated = wf_adapter.confirm_review(
            state=state,
            confirmed_by=teacher_name,
            exam_id=int(exam_id_input),
            max_marks=float(max_marks_input),
            academic_year=academic_year_input or None,
        )
        _set_state(updated)
        if updated.get("stage") == STAGE_DRY_RUN:
            st.success("Review confirmed. Running dry-run validation…")
        else:
            _show_errors(updated.get("errors", []))
        st.rerun()

    if st.button("↩ Upload a different PDF", key="reset_from_review"):
        _set_state(wf_adapter.reset_workflow(state))
        st.rerun()


def _render_dry_run_stage(teacher_name: str) -> None:
    """Stage 3 — Dry-run validation."""
    state = _state()

    st.markdown("#### 🔍 Backend Dry-Run Validation")
    st.info(
        f"Exam ID: **{state.get('exam_id')}** | "
        f"Max Marks: **{state.get('max_marks')}** | "
        "No data is saved during dry-run."
    )

    if not state.get("dry_run_done"):
        if st.button("▶ Run Dry-Run Validation", type="primary", key="run_dry_run_btn"):
            with st.spinner("Contacting backend for dry-run…"):
                updated = wf_adapter.run_dry_run(
                    state=state, base_url=_BACKEND_URL
                )
            _set_state(updated)
            st.rerun()
    else:
        summary = state.get("dry_run_summary", {})
        if state.get("dry_run_passed"):
            st.success("✅ Dry-run passed — no records would fail.")
        else:
            st.error("❌ Dry-run reported validation errors. Fix and re-upload.")

        _render_dry_run_summary(summary)

        if not state.get("dry_run_passed"):
            if st.button("↩ Re-upload PDF", key="retry_upload_from_dry"):
                _set_state(wf_adapter.reset_workflow(state))
                st.rerun()

    # Back button
    if st.button("↩ Back to Review", key="back_to_review"):
        state["stage"] = STAGE_REVIEW
        state["dry_run_done"] = False
        state["dry_run_passed"] = False
        state["dry_run_summary"] = None
        _set_state(state)
        st.rerun()


def _render_import_ready_stage(teacher_name: str) -> None:
    """Stage 4 — Dry-run passed, awaiting explicit import confirmation."""
    state = _state()

    st.success("✅ Dry-run passed. Review the summary and confirm the actual import.")

    summary = state.get("dry_run_summary", {})
    _render_dry_run_summary(summary)

    st.divider()
    st.markdown("#### ⚠️ Final Import Confirmation")
    st.warning(
        "The next step will write marks to the database. "
        "This action cannot be automatically undone."
    )

    confirmed = st.checkbox(
        "I have verified the records above and authorise the database import.",
        key="final_import_confirm_checkbox"
    )

    col_import, col_back = st.columns(2)

    with col_import:
        if st.button("✅ Import Marks to Database",
                     disabled=not confirmed, type="primary", key="execute_import_btn"):
            with st.spinner("Importing marks…"):
                updated = wf_adapter.execute_import(
                    state=state,
                    confirmed_by=teacher_name,
                    base_url=_BACKEND_URL,
                )
            _set_state(updated)
            st.rerun()

    with col_back:
        if st.button("↩ Re-run Dry-Run", key="re_dry_run_btn"):
            state["stage"] = STAGE_DRY_RUN
            state["dry_run_done"] = False
            state["dry_run_passed"] = False
            state["dry_run_summary"] = None
            _set_state(state)
            st.rerun()


def _render_done_stage(teacher_name: str) -> None:
    """Stage 5 — Import complete (success or partial failure)."""
    state = _state()
    summary = state.get("import_summary", {})

    if summary.get("success") and summary.get("failed_records", 0) == 0:
        st.success("🎉 Import complete! All records were saved successfully.")
    elif summary.get("success"):
        st.warning("⚠️ Import completed with some failures. See details below.")
    else:
        st.error("❌ Import failed. See error details below.")

    _render_import_summary(summary)

    st.caption(f"Confirmed by: {summary.get('confirmed_by', '—')} | "
               f"At: {summary.get('attempted_at', '—')}")

    if st.button("↩ Upload Another PDF", key="upload_another_btn"):
        _set_state(wf_adapter.reset_workflow(state))
        st.rerun()


def _render_uncertain_stage(teacher_name: str) -> None:
    """Stage 6 — Import ended in UNCERTAIN state (timeout mid-import)."""
    state = _state()

    st.error("⚠️ Import Timeout — Database State is UNCERTAIN")
    st.markdown(
        """
        The import request timed out before the backend confirmed completion.
        **The backend may have already saved some records to the database.**

        **Do NOT retry automatically.** Manual verification is required.

        **Steps:**
        1. Open the database / backend admin interface.
        2. Check which records were saved for this exam.
        3. Record your findings in the notes field below.
        4. Click **Acknowledge** to unlock the re-submission workflow.
        """
    )

    notes = st.text_area(
        "Notes (what you found in the database)",
        placeholder="e.g. Verified: 245 of 260 records saved before timeout.",
        key="uncertain_notes",
    )

    if st.button("Acknowledge & Reset for Re-submission", key="acknowledge_btn"):
        if not notes.strip():
            st.warning("Please enter notes about the database state before acknowledging.")
        else:
            updated = wf_adapter.acknowledge_uncertain(
                state=state,
                acknowledged_by=teacher_name,
                notes=notes.strip(),
            )
            _set_state(updated)
            st.success("Acknowledged. You may now run a fresh dry-run validation.")
            st.rerun()

    if st.button("↩ Re-upload PDF (start fresh)", key="reset_from_uncertain"):
        _set_state(wf_adapter.reset_workflow(state))
        st.rerun()


# ── Main entry point ─────────────────────────────────────────────────────────

def render_pdf_upload_tab(teacher_name: str = "Teacher") -> None:
    """
    Render the complete PDF Import Workflow tab.

    Call this from teacher_dashboard.py inside ``with tab3:``.

    :param teacher_name: The logged-in teacher's display name (for audit trail).
    """
    st.subheader("📄 Upload & Import Mark Sheet")

    state = _state()
    stage = state.get("stage", STAGE_UPLOAD)

    # Progress indicator
    stages = [STAGE_UPLOAD, STAGE_REVIEW, STAGE_DRY_RUN, STAGE_IMPORT_READY, STAGE_DONE]
    stage_labels = ["Upload", "Review", "Validate", "Confirm", "Done"]
    if stage in stages:
        idx = stages.index(stage)
        progress = idx / (len(stages) - 1)
        st.progress(progress, text=f"Step {idx + 1} of {len(stages)}: {stage_labels[idx]}")

    st.divider()

    # Route to the correct stage renderer
    if stage == STAGE_UPLOAD:
        _render_upload_stage(teacher_name)
    elif stage == STAGE_REVIEW:
        _render_review_stage(teacher_name)
    elif stage == STAGE_DRY_RUN:
        _render_dry_run_stage(teacher_name)
    elif stage == STAGE_IMPORT_READY:
        _render_import_ready_stage(teacher_name)
    elif stage == STAGE_DONE:
        _render_done_stage(teacher_name)
    elif stage == STAGE_UNCERTAIN:
        _render_uncertain_stage(teacher_name)
    else:
        st.error(f"Unknown workflow stage: {stage}")
        if st.button("Reset", key="unknown_stage_reset"):
            _set_state(wf_adapter.reset_workflow(state))
            st.rerun()
