import re
from typing import Dict, List, Any, Optional


def normalize_extracted_data(metadata: Dict[str, Any], students: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert extracted and validated marksheet data into the standardized internal Structure A.

    Structure A represents the canonical document-centric representation defined in
    PDF_INPUT_SPECIFICATION.md.

    Normalization Rules:
    1. Roll Number:
       - Strips leading and trailing whitespace.
       - Converts to uppercase.
       - Preserves the exact alphanumeric string otherwise without altering characters.
    2. Student Name:
       - Strips surrounding whitespace.
       - Collapses multiple consecutive spaces into a single space.
       - Converts to uppercase.
       - Preserves the original name words (no spelling corrections or guessing).
    3. Marks:
       - Numeric marks remain numeric (integers preserved as int).
       - Absent marker "ABS" remains exactly the string "ABS" (never coerced to 0, None, or empty).
    4. Subjects:
       - Preserves exact subject code ordering from metadata.
       - Strips whitespace and standardizes casing.
       - Does not invent subject codes.
    5. Metadata & Non-Inference:
       - Preserves institution, course, semester, branch, exam_name, and exam_session.
       - Preserves maximum_marks map keyed by subject code.
       - Academic year: remains None if not explicitly supplied. NEVER inferred from exam_session.
       - Does NOT silently invent or default missing course, branch, semester, or marks.

    :param metadata: Dictionary of exam metadata from extract_metadata().
    :param students: List of student records from parse_student_rows / clean_student_records.
    :return: A standardized Structure A dictionary: {'metadata': ..., 'subjects': ..., 'students': ...}.
    """
    # ── 1. Normalize Subjects ────────────────────────────────────────────────
    raw_subjects = metadata.get("subjects", [])
    normalized_subjects: List[str] = [
        str(subj).strip().upper() for subj in raw_subjects if str(subj).strip()
    ]

    # ── 2. Normalize Maximum Marks ───────────────────────────────────────────
    raw_max_marks = metadata.get("maximum_marks", {})
    normalized_max_marks: Dict[str, int] = {}
    for subj_code, max_val in raw_max_marks.items():
        clean_code = str(subj_code).strip().upper()
        try:
            normalized_max_marks[clean_code] = int(max_val)
        except (ValueError, TypeError):
            try:
                normalized_max_marks[clean_code] = int(float(max_val))
            except (ValueError, TypeError):
                normalized_max_marks[clean_code] = max_val

    # ── 3. Normalize Exam Metadata ───────────────────────────────────────────
    # Non-inference: academic_year is NEVER inferred from exam_session (e.g. 'JULY 2026')
    academic_year = metadata.get("academic_year")

    normalized_metadata = {
        "institution_name": (
            re.sub(r"\s+", " ", str(metadata["institution_name"]).strip())
            if metadata.get("institution_name")
            else None
        ),
        "course": (
            re.sub(r"\s+", " ", str(metadata["course"]).strip().upper())
            if metadata.get("course")
            else None
        ),
        "semester": (
            str(metadata["semester"]).strip().upper()
            if metadata.get("semester")
            else None
        ),
        "branch": (
            re.sub(r"\s+", " ", str(metadata["branch"]).strip().upper())
            if metadata.get("branch")
            else None
        ),
        "exam_name": (
            re.sub(r"\s+", " ", str(metadata["exam_name"]).strip())
            if metadata.get("exam_name")
            else None
        ),
        "exam_session": (
            re.sub(r"\s+", " ", str(metadata["exam_session"]).strip().upper())
            if metadata.get("exam_session")
            else None
        ),
        "maximum_marks": normalized_max_marks,
        "academic_year": academic_year,
    }

    # ── 4. Normalize Student Records ─────────────────────────────────────────
    normalized_students: List[Dict[str, Any]] = []

    for student in students:
        # Serial Number: parse as integer if present
        raw_serial = student.get("serial_number")
        serial_number: Optional[int] = None
        if raw_serial is not None:
            try:
                serial_number = int(raw_serial)
            except (ValueError, TypeError):
                serial_number = None

        # Roll Number: stripped, uppercase, preserve original characters
        raw_roll = student.get("roll_number", "")
        clean_roll = str(raw_roll).strip().upper()

        # Student Name: strip, collapse repeated spaces, uppercase
        raw_name = student.get("student_name") or student.get("name", "")
        clean_name = re.sub(r"\s+", " ", str(raw_name).strip()).upper()

        # Marks: numeric or "ABS" preserved as exact string
        raw_marks = student.get("marks", {})
        clean_marks: Dict[str, Any] = {}

        # Preserve declared subject order if subjects list is available
        target_keys = (
            normalized_subjects
            if normalized_subjects
            else list(raw_marks.keys())
        )

        for subj in target_keys:
            if subj in raw_marks:
                val = raw_marks[subj]
                clean_subj = str(subj).strip().upper()
                if str(val).strip().upper() == "ABS":
                    clean_marks[clean_subj] = "ABS"
                else:
                    try:
                        clean_marks[clean_subj] = int(val)
                    except (ValueError, TypeError):
                        try:
                            clean_marks[clean_subj] = float(val)
                        except (ValueError, TypeError):
                            clean_marks[clean_subj] = val

        normalized_student = {
            "serial_number": serial_number,
            "roll_number": clean_roll,
            "student_name": clean_name,
            "marks": clean_marks,
        }

        normalized_students.append(normalized_student)

    # ── 5. Assemble and Return Structure A ───────────────────────────────────
    return {
        "metadata": normalized_metadata,
        "subjects": normalized_subjects,
        "students": normalized_students,
    }
