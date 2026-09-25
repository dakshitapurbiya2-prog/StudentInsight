"""
tests/test_pdf_upload_tab.py

Unit tests for the teacher frontend Tab 3 component:
app.frontend.dashboards.pdf_upload_tab.render_pdf_upload_tab

Uses mocked streamlit and pandas modules so the tests run cleanly in the
backend/PDF processing Python environment without requiring frontend package
installations.

Tests cover all UI stages:
1. UPLOAD: file uploaded triggers extraction and rerun
2. REVIEW: renders metadata, table, edit flow, and review confirmation
3. DRY_RUN: triggers dry-run validation, renders metrics and errors
4. IMPORT_READY: confirmation checkbox gates import button, triggers actual import
5. DONE: renders success/partial metrics and reset button
6. UNCERTAIN: renders timeout warning, requires notes, and allows acknowledgement
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Mock streamlit and pandas in sys.modules ─────────────────────────────────
mock_st = MagicMock()
mock_st.session_state = {}
def _make_column():
    col = MagicMock()
    col.text_input.side_effect = lambda *a, **k: mock_st.text_input(*a, **k)
    col.number_input.side_effect = lambda *a, **k: mock_st.number_input(*a, **k)
    col.button.side_effect = lambda *a, **k: mock_st.button(*a, **k)
    col.markdown.side_effect = lambda *a, **k: mock_st.markdown(*a, **k)
    col.metric.side_effect = lambda *a, **k: mock_st.metric(*a, **k)
    col.checkbox.side_effect = lambda *a, **k: mock_st.checkbox(*a, **k)
    return col

mock_st.columns.side_effect = lambda n: [_make_column() for _ in range(n if isinstance(n, int) else len(n))]
mock_st.tabs.side_effect = lambda names: [MagicMock() for _ in names]

# Context manager helpers
class _MockContext:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

mock_st.spinner.side_effect = lambda *args, **kwargs: _MockContext()
mock_st.expander.side_effect = lambda *args, **kwargs: _MockContext()

mock_pd = MagicMock()
mock_pd.DataFrame = MagicMock(return_value=MagicMock())

sys.modules["streamlit"] = mock_st
sys.modules["pandas"] = mock_pd

# Now import the tab module
import app.frontend.dashboards.pdf_upload_tab as put
from pdf_processing.workflow_adapter import (
    STAGE_UPLOAD,
    STAGE_REVIEW,
    STAGE_DRY_RUN,
    STAGE_IMPORT_READY,
    STAGE_DONE,
    STAGE_UNCERTAIN,
    initial_state,
)


def _reset_st():
    mock_st.reset_mock()
    mock_st.session_state.clear()


def test_tab_render_upload_stage_empty():
    """1. Upload stage without file uploaded prompts user to choose file."""
    _reset_st()
    mock_st.file_uploader.return_value = None

    put.render_pdf_upload_tab(teacher_name="Dr. Test")

    mock_st.subheader.assert_any_call("📄 Upload & Import Mark Sheet")
    mock_st.info.assert_called()
    assert mock_st.session_state["pdf_wf"]["stage"] == STAGE_UPLOAD
    print("test_tab_render_upload_stage_empty: PASS")


def test_tab_render_upload_stage_with_file():
    """2. Uploading a valid PDF triggers extraction and transitions to REVIEW."""
    _reset_st()
    mock_file = MagicMock()
    mock_file.name = "sample.pdf"
    mock_file.read.return_value = b"%PDF-1.4 dummy"
    mock_st.file_uploader.return_value = mock_file

    with patch("pdf_processing.workflow_adapter.process_uploaded_bytes") as mock_extract:
        mock_extract.return_value = {
            "stage": STAGE_REVIEW,
            "pipeline_ok": True,
            "metadata": {"course": "B.TECH", "semester": "II"},
            "subjects": ["BT-101", "BT-102"],
            "students": [
                {"roll_number": "0112AL251001", "student_name": "TEST", "marks": {"BT-101": 28, "BT-102": 25}}
            ],
            "errors": [],
            "warnings": [],
        }
        put.render_pdf_upload_tab(teacher_name="Dr. Test")

        mock_extract.assert_called_once_with(pdf_bytes=b"%PDF-1.4 dummy", filename="sample.pdf")
        mock_st.rerun.assert_called_once()
        assert mock_st.session_state["pdf_wf"]["stage"] == STAGE_REVIEW

    print("test_tab_render_upload_stage_with_file: PASS")


def test_tab_render_review_stage():
    """3. Review stage renders metadata, students dataframe, and confirmation form."""
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_REVIEW,
        "pipeline_ok": True,
        "metadata": {
            "institution_name": "BIST BHOPAL",
            "course": "B.TECH",
            "semester": "II",
            "branch": "AIML",
            "exam_name": "MST-2",
            "exam_session": "JULY 2026",
        },
        "subjects": ["BT-101", "BT-102"],
        "students": [
            {"roll_number": "0112AL251001", "student_name": "STUDENT 1", "marks": {"BT-101": 28, "BT-102": "ABS"}}
        ],
        "errors": [],
        "warnings": ["Sample warning"],
    }

    mock_st.text_input.return_value = ""
    mock_st.number_input.side_effect = [2, 30.0]  # exam_id=2, max_marks=30.0
    mock_st.button.return_value = False

    put.render_pdf_upload_tab(teacher_name="Dr. Test")

    mock_st.dataframe.assert_called_once()
    mock_st.warning.assert_called_with("⚠️ Sample warning")
    print("test_tab_render_review_stage: PASS")


def test_tab_render_review_stage_confirm_action():
    """4. Clicking Confirm Review in REVIEW stage invokes confirm_review adapter."""
    _reset_st()
    initial_wf_state = {
        "stage": STAGE_REVIEW,
        "pipeline_ok": True,
        "metadata": {"course": "B.TECH"},
        "subjects": ["BT-101"],
        "students": [{"roll_number": "R1", "student_name": "S1", "marks": {"BT-101": 20}}],
        "errors": [],
        "warnings": [],
    }
    mock_st.session_state["pdf_wf"] = initial_wf_state

    def text_input_side_effect(label, **kwargs):
        if kwargs.get("key") == "academic_year_input":
            return "2025-2026"
        return ""
    mock_st.text_input.side_effect = text_input_side_effect

    def number_input_side_effect(label, **kwargs):
        if kwargs.get("key") == "exam_id_input":
            return 3
        if kwargs.get("key") == "max_marks_input":
            return 40.0
        return 1
    mock_st.number_input.side_effect = number_input_side_effect

    # Button handler: return True for 'confirm_review_btn'
    def btn_side_effect(label, **kwargs):
        return kwargs.get("key") == "confirm_review_btn"

    mock_st.button.side_effect = btn_side_effect

    from unittest.mock import ANY
    with patch("pdf_processing.workflow_adapter.confirm_review") as mock_confirm:
        mock_confirm.return_value = {
            "stage": STAGE_DRY_RUN,
            "exam_id": 3,
            "max_marks": 40.0,
            "errors": [],
        }
        put.render_pdf_upload_tab(teacher_name="Dr. Test")
        mock_confirm.assert_called_once_with(
            state=ANY,
            confirmed_by="Dr. Test",
            exam_id=3,
            max_marks=40.0,
            academic_year="2025-2026",
        )
        mock_st.rerun.assert_called()

    print("test_tab_render_review_stage_confirm_action: PASS")


def test_tab_render_dry_run_stage():
    """5. DRY_RUN stage allows running dry-run and displays backend validation summary."""
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_DRY_RUN,
        "exam_id": 2,
        "max_marks": 30.0,
        "dry_run_done": False,
        "dry_run_passed": False,
        "dry_run_summary": None,
    }

    def btn_side_effect(label, **kwargs):
        return kwargs.get("key") == "run_dry_run_btn"

    mock_st.button.side_effect = btn_side_effect

    with patch("pdf_processing.workflow_adapter.run_dry_run") as mock_dry:
        mock_dry.return_value = {
            "stage": STAGE_IMPORT_READY,
            "dry_run_done": True,
            "dry_run_passed": True,
            "dry_run_summary": {
                "total_records": 260,
                "saved_records": 251,
                "skipped_absent": 9,
                "failed_records": 0,
                "errors": [],
                "error_reasons": [],
            },
        }
        put.render_pdf_upload_tab(teacher_name="Dr. Test")
        mock_dry.assert_called_once()
        mock_st.rerun.assert_called()

    print("test_tab_render_dry_run_stage: PASS")


def test_tab_render_import_ready_stage_checkbox_gating():
    """6. IMPORT_READY requires explicit checkbox before Import button can execute."""
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_IMPORT_READY,
        "exam_id": 2,
        "max_marks": 30.0,
        "dry_run_summary": {
            "total_records": 260,
            "saved_records": 251,
            "skipped_absent": 9,
            "failed_records": 0,
        },
    }

    # Scenario A: Checkbox unchecked -> Import button is disabled
    mock_st.checkbox.return_value = False
    mock_st.button.return_value = False
    put.render_pdf_upload_tab(teacher_name="Dr. Test")

    # Find the execute_import_btn call
    execute_calls = [
        call for call in mock_st.button.call_args_list
        if call.kwargs.get("key") == "execute_import_btn"
    ]
    assert len(execute_calls) == 1
    assert execute_calls[0].kwargs.get("disabled") is True

    # Scenario B: Checkbox checked -> Import button enabled and executes
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_IMPORT_READY,
        "exam_id": 2,
        "max_marks": 30.0,
        "dry_run_summary": {
            "total_records": 260,
            "saved_records": 251,
            "skipped_absent": 9,
            "failed_records": 0,
        },
    }
    mock_st.checkbox.return_value = True

    def btn_side_effect(label, **kwargs):
        return kwargs.get("key") == "execute_import_btn"

    mock_st.button.side_effect = btn_side_effect

    from unittest.mock import ANY
    with patch("pdf_processing.workflow_adapter.execute_import") as mock_import:
        mock_import.return_value = {
            "stage": STAGE_DONE,
            "import_done": True,
            "import_summary": {
                "success": True,
                "saved_records": 251,
                "skipped_absent": 9,
                "failed_records": 0,
                "confirmed_by": "Dr. Test",
            },
        }
        put.render_pdf_upload_tab(teacher_name="Dr. Test")
        mock_import.assert_called_once_with(
            state=ANY,
            confirmed_by="Dr. Test",
            base_url="http://localhost:8000",
        )
        mock_st.rerun.assert_called()

    print("test_tab_render_import_ready_stage_checkbox_gating: PASS")


def test_tab_render_done_stage():
    """7. DONE stage displays final import counts and audit info."""
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_DONE,
        "import_summary": {
            "success": True,
            "total_records": 260,
            "saved_records": 251,
            "skipped_absent": 9,
            "failed_records": 0,
            "confirmed_by": "Dr. Test",
            "attempted_at": "2026-09-25T12:00:00Z",
        },
    }
    mock_st.button.return_value = False

    put.render_pdf_upload_tab(teacher_name="Dr. Test")

    mock_st.success.assert_any_call("🎉 Import complete! All records were saved successfully.")
    mock_st.metric.assert_any_call("Saved", 251)
    mock_st.metric.assert_any_call("Absent (ABS)", 9)
    print("test_tab_render_done_stage: PASS")


def test_tab_render_uncertain_stage():
    """8. UNCERTAIN stage renders timeout warning and acknowledgement form."""
    _reset_st()
    mock_st.session_state["pdf_wf"] = {
        "stage": STAGE_UNCERTAIN,
    }

    mock_st.text_area.return_value = "Verified 245 records saved in DB."

    def btn_side_effect(label, **kwargs):
        return kwargs.get("key") == "acknowledge_btn"

    mock_st.button.side_effect = btn_side_effect

    from unittest.mock import ANY
    with patch("pdf_processing.workflow_adapter.acknowledge_uncertain") as mock_ack:
        mock_ack.return_value = {
            "stage": STAGE_DRY_RUN,
            "dry_run_done": False,
            "dry_run_passed": False,
        }
        put.render_pdf_upload_tab(teacher_name="Dr. Test")
        mock_ack.assert_called_once_with(
            state=ANY,
            acknowledged_by="Dr. Test",
            notes="Verified 245 records saved in DB.",
        )
        mock_st.rerun.assert_called()

    print("test_tab_render_uncertain_stage: PASS")


if __name__ == "__main__":
    print("=" * 68)
    print("Stage 3, Step 5 — Teacher Tab 3 UI Tests")
    print("=" * 68)

    test_tab_render_upload_stage_empty()
    test_tab_render_upload_stage_with_file()
    test_tab_render_review_stage()
    test_tab_render_review_stage_confirm_action()
    test_tab_render_dry_run_stage()
    test_tab_render_import_ready_stage_checkbox_gating()
    test_tab_render_done_stage()
    test_tab_render_uncertain_stage()

    print("=" * 68)
    print("ALL 8 TEACHER TAB UI TESTS PASSED!")
    print("=" * 68)
