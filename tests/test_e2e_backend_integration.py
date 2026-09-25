"""
tests/test_e2e_backend_integration.py

Comprehensive End-to-End Integration Testing for the StudentInsight
PDF Processing Pipeline and Backend Database Import.

Workflow tested end-to-end:
    PDF Upload
    -> Text Extraction (pdfplumber)
    -> Metadata Extraction (Header & Exam details)
    -> Student Parsing (52 students, 5 subjects)
    -> Cleaning & Validation
    -> Normalization (Structure A)
    -> Teacher Review & Confirmation
    -> Backend Mapping (Structure B: 260 relational records)
    -> Dry-Run Validation (POST /marks/import?dry_run=true)
    -> Teacher Confirmation Gate
    -> Actual Import (POST /marks/import?dry_run=false)
    -> Database Verification (get_marks_by_exam & SQL inspection)

Safety & Isolation:
    - Runs against an isolated temporary SQLite database.
    - Does not modify any production or persistent database records.
    - Verifies zero DB mutations during dry-run.
    - Verifies unaffected state of other exams in database.
"""

import os
import sys
import json
import sqlite3
import tempfile
import urllib.error
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Core PDF pipeline imports
from pdf_processing.processor import process_pdf
from pdf_processing.review import create_review_session
from pdf_processing.mapper import map_to_backend_payload
from pdf_processing.backend_client import submit_marks_import, dry_run_validation
from pdf_processing.import_workflow import (
    TeacherImportWorkflow,
    ImportWorkflowError,
    DuplicateImportError,
    UncertainImportError,
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_UNCERTAIN,
)

# Backend database & services imports
import backend.database.database as backend_db
import backend.services.marks_import_service as backend_import_service
import backend.services.marks_service as backend_marks_service


SAMPLE_PDF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "pdf_processing", "samples", "sample_marks.pdf"
)

DESIGNATED_TEST_EXAM_ID = 101
BASELINE_OTHER_EXAM_ID = 999


# ── HTTP Mock that executes real backend import service against SQLite ─────────

def _make_backend_http_dispatcher():
    """
    Returns a mock urlopen handler that dispatches HTTP POST requests to
    the actual backend `marks_import_service.process_marks_import()` function.
    This routes the serialized network requests to the real backend SQLite database.
    """
    def _mock_urlopen(req, timeout=10.0):
        # Verify HTTP request structure
        assert req.get_method() == "POST"
        assert req.headers.get("Content-type") == "application/json"
        assert "/marks/import" in req.full_url

        # Check dry_run query param
        is_dry_run = "dry_run=true" in req.full_url.lower()

        # Deserialize JSON payload sent across the network
        body = json.loads(req.data.decode("utf-8"))
        exam_id = body.get("exam_id")
        max_marks = body.get("max_marks", 100.0)
        records = body.get("records", [])

        # Call real backend import service
        result_summary = backend_import_service.process_marks_import(
            imported_records=records,
            exam_id=exam_id,
            max_marks=max_marks,
            dry_run=is_dry_run,
        )

        if is_dry_run:
            result_summary["dry_run"] = True
            result_summary["message"] = "Dry run complete. No data was saved to the database."

        # Wrap in mock HTTP response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(result_summary).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp

    return _mock_urlopen


# ── Database Setup & Teardown Fixture ─────────────────────────────────────────

class E2EDatabaseEnvironment:
    """Manages an isolated SQLite test database seeded for sample_marks.pdf."""

    def __init__(self):
        self.tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp_file.name
        self.tmp_file.close()

    def __enter__(self):
        backend_db.DB_PATH = self.db_path
        backend_db.create_tables()
        self._seed_test_database()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)
        except OSError:
            pass

    def _seed_test_database(self):
        """Seed department, class, subjects, students, and baseline other exam."""
        conn = backend_db.get_connection()
        cursor = conn.cursor()

        # 1. Department & Class
        cursor.execute("INSERT INTO departments (name) VALUES ('AI & ML');")
        dept_id = cursor.lastrowid

        cursor.execute("INSERT INTO classes (class_name, department_id) VALUES ('AIML-II', ?);", (dept_id,))
        self.class_id = cursor.lastrowid

        # 2. Designated Test Exam (MST-2)
        cursor.execute(
            "INSERT INTO exams (exam_id, exam_name, class_id, exam_date) VALUES (?, 'MST-2', ?, '2026-07-15');",
            (DESIGNATED_TEST_EXAM_ID, self.class_id),
        )

        # 3. Baseline Other Exam (to test isolation)
        cursor.execute(
            "INSERT INTO exams (exam_id, exam_name, class_id, exam_date) VALUES (?, 'Midterm Baseline', ?, '2026-05-10');",
            (BASELINE_OTHER_EXAM_ID, self.class_id),
        )

        # 4. Subjects (all 5 subjects detected from sample_marks.pdf)
        subjects = [
            ("Programming in Python", "BT-101"),
            ("Mathematics-II", "BT-202"),
            ("Database Management Systems", "BT-103"),
            ("Data Structures & Algorithms", "BT-104"),
            ("Digital Electronics", "BT-105"),
        ]
        self.subject_ids = {}
        for sname, scode in subjects:
            cursor.execute(
                "INSERT INTO subjects (subject_name, subject_code, class_id) VALUES (?, ?, ?);",
                (sname, scode, self.class_id),
            )
            self.subject_ids[scode] = cursor.lastrowid

        # 5. Extract students from PDF to populate exact matching student directory
        pipeline_res = process_pdf(SAMPLE_PDF_PATH)
        students = pipeline_res["structure_a"]["students"]

        self.student_ids = {}
        for s in students:
            roll = s["roll_number"]
            name = s["student_name"]
            cursor.execute(
                "INSERT INTO students (roll_number, name, class_id) VALUES (?, ?, ?);",
                (roll, name, self.class_id),
            )
            self.student_ids[roll] = cursor.lastrowid

        # 6. Pre-populate 5 marks in the baseline other exam (exam_id=999)
        first_student_id = next(iter(self.student_ids.values()))
        self.baseline_other_exam_marks = []
        for scode, sub_id in self.subject_ids.items():
            cursor.execute(
                "INSERT INTO marks (student_id, subject_id, exam_id, marks_obtained, max_marks) VALUES (?, ?, ?, 25.0, 30.0);",
                (first_student_id, sub_id, BASELINE_OTHER_EXAM_ID),
            )
            self.baseline_other_exam_marks.append({
                "student_id": first_student_id,
                "subject_id": sub_id,
                "exam_id": BASELINE_OTHER_EXAM_ID,
                "marks_obtained": 25.0,
                "max_marks": 30.0,
            })

        conn.commit()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# 1. Extraction and Mapping Verification
# ═════════════════════════════════════════════════════════════════════════════

def step_1_extraction_and_mapping(env: E2EDatabaseEnvironment):
    """
    Verify:
    - 52 students are extracted.
    - 5 subjects are detected.
    - 260 subject records are produced when all students have 5 subject entries.
    - All 9 ABS entries are preserved in the outgoing payload.
    - Student roll numbers and subject codes match the backend.
    """
    print("\n--- TEST 1: Extraction and Mapping Verification ---")
    pipeline_res = process_pdf(SAMPLE_PDF_PATH)
    assert pipeline_res["success"] is True

    # 1. Students count
    students = pipeline_res["structure_a"]["students"]
    assert len(students) == 52, f"Expected 52 students, got {len(students)}"

    # 2. Subjects detected
    subjects = pipeline_res["structure_a"]["subjects"]
    assert len(subjects) == 5, f"Expected 5 subjects, got {len(subjects)}"
    expected_subjects = ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"]
    assert subjects == expected_subjects

    # 3. Create confirmed review session and map to backend payload
    session = create_review_session(pipeline_res)
    confirm_res = session.confirm(confirmed_by="Prof. Bansal", academic_year="2025-2026")
    assert confirm_res["success"] is True

    payload = session.to_backend_payload(exam_id=DESIGNATED_TEST_EXAM_ID, max_marks=30.0)
    records = payload["records"]

    # 4. Total records: 52 students x 5 subjects = 260 records
    assert len(records) == 260, f"Expected 260 records, got {len(records)}"

    # 5. ABS entries preserved exactly as string "ABS"
    abs_records = [r for r in records if r["marks"] == "ABS"]
    assert len(abs_records) == 9, f"Expected exactly 9 ABS records, got {len(abs_records)}"
    for r in abs_records:
        assert isinstance(r["marks"], str)
        assert r["marks"] == "ABS"

    # 6. Verify student roll numbers and subject codes match backend DB directory
    conn = backend_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT roll_number FROM students;")
    db_rolls = {row[0] for row in cursor.fetchall()}
    cursor.execute("SELECT subject_code FROM subjects WHERE class_id = ?;", (env.class_id,))
    db_subjects = {row[0] for row in cursor.fetchall()}
    conn.close()

    payload_rolls = {r["roll_number"] for r in records}
    payload_subjects = {r["subject_code"] for r in records}

    assert payload_rolls.issubset(db_rolls), "Some payload roll numbers not found in backend DB!"
    assert payload_subjects.issubset(db_subjects), "Some payload subject codes not found in backend DB!"

    print(f"Extraction & Mapping: PASS (52 students, 5 subjects, 260 records, 9 ABS entries)")
    return pipeline_res, session


# ═════════════════════════════════════════════════════════════════════════════
# 2. Dry-Run Validation Verification
# ═════════════════════════════════════════════════════════════════════════════

def step_2_dry_run_validation(session: create_review_session, env: E2EDatabaseEnvironment):
    """
    Verify:
    - Confirm the backend validates the request.
    - Verify that no database records are inserted during dry-run.
    """
    print("\n--- TEST 2: Dry-Run Validation Verification ---")
    workflow = TeacherImportWorkflow(session)

    # Count marks before dry run
    conn = backend_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM marks WHERE exam_id = ?;", (DESIGNATED_TEST_EXAM_ID,))
    marks_before = cursor.fetchone()[0]
    assert marks_before == 0, "Test exam should have 0 marks before test"
    conn.close()

    # Execute dry-run with mock dispatcher sending to real backend SQLite service
    backend_dispatcher = _make_backend_http_dispatcher()
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        dry_run_res = workflow.run_dry_run(exam_id=DESIGNATED_TEST_EXAM_ID, max_marks=30.0)

    # 1. Backend validation response assertions
    assert dry_run_res["dry_run"] is True
    assert dry_run_res["dry_run_passed"] is True
    assert dry_run_res["total_records"] == 260
    assert dry_run_res["saved_records"] == 251  # 260 total - 9 ABS = 251 would save
    assert dry_run_res["skipped_absent"] == 9
    assert dry_run_res["failed_records"] == 0
    assert len(dry_run_res["errors"]) == 0
    assert len(dry_run_res["absent"]) == 9

    # 2. Database verification: ZERO records must be inserted into marks table during dry-run!
    conn = backend_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM marks WHERE exam_id = ?;", (DESIGNATED_TEST_EXAM_ID,))
    marks_after = cursor.fetchone()[0]
    assert marks_after == 0, f"DRY-RUN VIOLATION: Found {marks_after} marks inserted during dry-run!"

    # Verify baseline other exam is untouched
    cursor.execute("SELECT COUNT(*) FROM marks WHERE exam_id = ?;", (BASELINE_OTHER_EXAM_ID,))
    other_exam_count = cursor.fetchone()[0]
    assert other_exam_count == len(env.baseline_other_exam_marks)
    conn.close()

    print(f"Dry-Run Validation: PASS (Validated: 251 would save, 9 ABS skipped, 0 DB rows inserted)")
    return workflow


# ═════════════════════════════════════════════════════════════════════════════
# 3. Actual Import Execution
# ═════════════════════════════════════════════════════════════════════════════

def step_3_actual_import(workflow: TeacherImportWorkflow, env: E2EDatabaseEnvironment):
    """
    Verify:
    - Use a designated test exam.
    - Require explicit confirmation before submitting the actual import.
    - Record the backend's actual response.
    - Verify inserted and skipped records.
    """
    print("\n--- TEST 3: Actual Import Execution ---")

    # Gate verification: omitting import_confirmation must fail
    try:
        workflow.confirm_and_import(confirmed_by="Prof. Bansal", import_confirmation=False)
        assert False, "Should have blocked import when import_confirmation=False"
    except ImportWorkflowError as err:
        assert "explicit import confirmation" in str(err).lower()

    # Execute actual import with explicit confirmation
    backend_dispatcher = _make_backend_http_dispatcher()
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        import_res = workflow.confirm_and_import(
            confirmed_by="Prof. Bansal",
            import_confirmation=True,
        )

    # Verify backend's response summary
    assert import_res["dry_run"] is False
    assert import_res["import_status"] == STATUS_SUCCESS
    assert import_res["success"] is True
    assert import_res["total_records"] == 260
    assert import_res["saved_records"] == 251
    assert import_res["skipped_absent"] == 9
    assert import_res["failed_records"] == 0
    assert len(import_res["errors"]) == 0
    assert import_res["confirmed_by"] == "Prof. Bansal"
    assert "attempted_at" in import_res

    print(f"Actual Import: PASS (Status: SUCCESS, Inserted: 251, Skipped ABS: 9, Failed: 0)")
    return import_res


# ═════════════════════════════════════════════════════════════════════════════
# 4. Database Verification
# ═════════════════════════════════════════════════════════════════════════════

def step_4_database_verification(session: create_review_session, env: E2EDatabaseEnvironment):
    """
    Use the existing backend's supported read mechanism (get_marks_by_exam)
    and SQL queries to confirm:
    - Imported marks match the teacher-confirmed payload.
    - ABS records are handled according to the backend contract (not saved).
    - No unexpected duplicate records were created.
    - Other exam records remain unchanged.
    """
    print("\n--- TEST 4: Database Verification ---")

    # 1. Use backend's official read method: backend_marks_service.get_marks_by_exam()
    stored_marks = backend_marks_service.get_marks_by_exam(DESIGNATED_TEST_EXAM_ID)
    assert len(stored_marks) == 251, f"Expected 251 stored marks in backend, got {len(stored_marks)}"

    # 2. Build index of stored marks: (student_id, subject_id) -> marks_obtained
    stored_marks_map = {
        (m["student_id"], m["subject_id"]): m["marks_obtained"]
        for m in stored_marks
    }

    # 3. Match against teacher-confirmed payload
    confirmed_data = session.get_confirmed_data()
    students = confirmed_data["students"]

    matched_count = 0
    abs_skipped_count = 0

    for s in students:
        roll = s["roll_number"]
        student_id = env.student_ids[roll]

        for scode, mark_val in s["marks"].items():
            subject_id = env.subject_ids[scode]
            key = (student_id, subject_id)

            if mark_val == "ABS":
                # ABS records must NOT exist in the marks table
                assert key not in stored_marks_map, f"ABS record {roll} / {scode} was unexpectedly saved to DB!"
                abs_skipped_count += 1
            else:
                expected_numeric = float(mark_val)
                assert key in stored_marks_map, f"Missing mark record for {roll} / {scode}"
                actual_stored = stored_marks_map[key]
                assert actual_stored == expected_numeric, (
                    f"Mismatch for {roll} / {scode}: expected {expected_numeric}, got {actual_stored}"
                )
                matched_count += 1

    assert matched_count == 251
    assert abs_skipped_count == 9

    # 4. Check for duplicates in database
    conn = backend_db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT student_id, subject_id, COUNT(*)
        FROM marks
        WHERE exam_id = ?
        GROUP BY student_id, subject_id
        HAVING COUNT(*) > 1;
        """,
        (DESIGNATED_TEST_EXAM_ID,),
    )
    duplicates = cursor.fetchall()
    assert len(duplicates) == 0, f"Found duplicate marks in database: {duplicates}"

    # 5. Verify other exam records remain completely unchanged
    other_marks = backend_marks_service.get_marks_by_exam(BASELINE_OTHER_EXAM_ID)
    assert len(other_marks) == len(env.baseline_other_exam_marks)
    for expected in env.baseline_other_exam_marks:
        matching = [
            m for m in other_marks
            if m["student_id"] == expected["student_id"]
            and m["subject_id"] == expected["subject_id"]
            and m["marks_obtained"] == expected["marks_obtained"]
        ]
        assert len(matching) == 1, f"Baseline other exam mark was corrupted: {expected}"

    conn.close()
    print("Database Verification: PASS (251 marks verified, 9 ABS skipped, 0 duplicates, other exams intact)")


# ═════════════════════════════════════════════════════════════════════════════
# 5. Error Cases Verification
# ═════════════════════════════════════════════════════════════════════════════

def step_5_error_cases(env: E2EDatabaseEnvironment):
    """
    Test failure scenarios and edge cases:
    - Invalid exam ID
    - Unknown student
    - Unknown subject
    - Invalid marks
    - Missing metadata
    - Backend unavailable
    - Repeated import attempt
    - Partial import or uncertain response
    """
    print("\n--- TEST 5: Error Cases Verification ---")
    backend_dispatcher = _make_backend_http_dispatcher()

    # 5a. Invalid exam ID
    print("  Testing 5a: Invalid exam ID...")
    bad_exam_payload = {
        "exam_id": 88888,  # Does not exist in database
        "max_marks": 30.0,
        "records": [{"roll_number": "0112AL251001", "subject_code": "BT-101", "marks": 28}],
    }
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        res_bad_exam = submit_marks_import(bad_exam_payload, dry_run=True)
    assert res_bad_exam["success"] is True
    assert res_bad_exam["failed_records"] == 1
    assert "does not exist in the database" in res_bad_exam["errors"][0]["reason"]

    # 5b. Unknown student
    print("  Testing 5b: Unknown student...")
    unknown_student_payload = {
        "exam_id": DESIGNATED_TEST_EXAM_ID,
        "max_marks": 30.0,
        "records": [{"roll_number": "9999UNKNOWN", "subject_code": "BT-101", "marks": 25}],
    }
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        res_unknown_stu = submit_marks_import(unknown_student_payload, dry_run=True)
    assert res_unknown_stu["failed_records"] == 1
    assert "not found" in res_unknown_stu["errors"][0]["reason"].lower()

    # 5c. Unknown subject
    print("  Testing 5c: Unknown subject...")
    unknown_subj_payload = {
        "exam_id": DESIGNATED_TEST_EXAM_ID,
        "max_marks": 30.0,
        "records": [{"roll_number": "0112AL251001", "subject_code": "UNKNOWN-999", "marks": 25}],
    }
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        res_unknown_subj = submit_marks_import(unknown_subj_payload, dry_run=True)
    assert res_unknown_subj["failed_records"] == 1
    assert "not found" in res_unknown_subj["errors"][0]["reason"].lower()

    # 5d. Invalid marks (exceeding max marks and negative marks)
    print("  Testing 5d: Invalid marks (out of range)...")
    invalid_marks_payload = {
        "exam_id": DESIGNATED_TEST_EXAM_ID,
        "max_marks": 30.0,
        "records": [
            {"roll_number": "0112AL251001", "subject_code": "BT-101", "marks": 50},  # Exceeds 30
            {"roll_number": "0112AL251001", "subject_code": "BT-202", "marks": -5},  # Negative
        ],
    }
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        res_invalid_marks = submit_marks_import(invalid_marks_payload, dry_run=True)
    assert res_invalid_marks["failed_records"] == 2
    assert any("exceed" in e["reason"].lower() for e in res_invalid_marks["errors"])
    assert any("negative" in e["reason"].lower() for e in res_invalid_marks["errors"])

    # 5e. Missing metadata blocks review confirmation
    print("  Testing 5e: Missing metadata blocks confirmation...")
    pipeline_res = process_pdf(SAMPLE_PDF_PATH)
    corrupted_res = dict(pipeline_res)
    corrupted_meta = dict(pipeline_res["structure_a"]["metadata"])
    corrupted_meta["course"] = ""  # Strip mandatory course metadata
    corrupted_res["structure_a"] = dict(pipeline_res["structure_a"])
    corrupted_res["structure_a"]["metadata"] = corrupted_meta

    broken_session = create_review_session(corrupted_res)
    conf_attempt = broken_session.confirm(confirmed_by="Prof. Bansal")
    assert conf_attempt["success"] is False
    assert conf_attempt["ready_for_import"] is False
    assert any("ERR_MISSING_EXAM_METADATA" in e for e in conf_attempt["errors"])

    # 5f. Backend unavailable
    print("  Testing 5f: Backend unavailable (ConnectionError)...")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res_conn_err = submit_marks_import(bad_exam_payload, dry_run=True)
    assert res_conn_err["success"] is False
    assert res_conn_err["error_type"] == "ConnectionError"

    # 5g. Repeated import attempt
    print("  Testing 5g: Repeated import attempt blocked...")
    valid_session = create_review_session(pipeline_res)
    valid_session.confirm(confirmed_by="Prof. Bansal")
    wf = TeacherImportWorkflow(valid_session)
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        wf.run_dry_run(exam_id=DESIGNATED_TEST_EXAM_ID, max_marks=30.0)
        wf.confirm_and_import(confirmed_by="Prof. Bansal", import_confirmation=True)

    # Attempting to import again on the same workflow must raise DuplicateImportError
    try:
        wf.confirm_and_import(confirmed_by="Prof. Bansal", import_confirmation=True)
        assert False, "Repeated import attempt should raise DuplicateImportError"
    except DuplicateImportError as d_err:
        assert "already completed successfully" in str(d_err)

    # 5h. Partial import or uncertain response (timeout mid-import)
    print("  Testing 5h: Timeout during actual import sets UNCERTAIN status...")
    wf_timeout = TeacherImportWorkflow(valid_session)
    with patch("urllib.request.urlopen", side_effect=backend_dispatcher):
        wf_timeout.run_dry_run(exam_id=DESIGNATED_TEST_EXAM_ID, max_marks=30.0)

    # Simulate timeout on actual import
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        summary_timeout = wf_timeout.confirm_and_import(confirmed_by="Prof. Bansal", import_confirmation=True)

    assert wf_timeout.import_status == STATUS_UNCERTAIN
    assert summary_timeout["import_status"] == STATUS_UNCERTAIN
    assert summary_timeout["error_type"] == "TimeoutError"

    # Retry is blocked
    try:
        wf_timeout.confirm_and_import(confirmed_by="Prof. Bansal", import_confirmation=True)
        assert False, "Should block retry when status is UNCERTAIN"
    except UncertainImportError:
        pass

    # Acknowledging clears the lock
    wf_timeout.acknowledge_uncertain_import(acknowledged_by="Prof. Bansal", notes="Checked DB manually.")
    assert wf_timeout.import_status == STATUS_FAILED

    print("Error Cases: ALL 8 ERROR SCENARIOS PASSED!")


# ═════════════════════════════════════════════════════════════════════════════
# Main Test Orchestrator & Pytest Entrypoint
# ═════════════════════════════════════════════════════════════════════════════

def test_e2e_full_workflow():
    """Pytest entrypoint for running the end-to-end integration workflow."""
    run_all_e2e_integration_tests()


def run_all_e2e_integration_tests():
    print("=" * 70)
    print("STAGE 3, STEP 6: END-TO-END BACKEND INTEGRATION TESTS")
    print("=" * 70)

    with E2EDatabaseEnvironment() as env:
        # Step 1: Extraction & Mapping
        pipeline_res, session = step_1_extraction_and_mapping(env)

        # Step 2: Dry-run Validation
        workflow = step_2_dry_run_validation(session, env)

        # Step 3: Actual Import
        step_3_actual_import(workflow, env)

        # Step 4: Database Verification
        step_4_database_verification(session, env)

        # Step 5: Error Cases
        step_5_error_cases(env)

    print("=" * 70)
    print("ALL STAGE 3, STEP 6 END-TO-END INTEGRATION TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_e2e_integration_tests()

