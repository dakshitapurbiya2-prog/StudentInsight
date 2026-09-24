from pdf_processing.extractor import extract_text_from_pdf
from pdf_processing.parser    import parse_student_rows
from pdf_processing.cleaner   import clean_student_records
from pdf_processing.validator import validate_student_records


def process_pdf(pdf_path, subjects, max_marks):
    """
    Run the complete PDF processing pipeline in one call.

    Steps (in order):
        1. Extract  — read raw text from the PDF file.
        2. Parse    — find student rows and build raw record dicts.
        3. Clean    — strip whitespace and normalise names to uppercase.
        4. Validate — check enrollment, names, subjects, marks, duplicates.

    :param pdf_path:  Path to the PDF file, e.g. "sample_data/college_marks.pdf".
    :param subjects:  List of subject codes in PDF column order,
                      e.g. ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"].
    :param max_marks: Dict mapping subject code -> maximum allowed mark,
                      e.g. {"BT-101": 30, ...}.
    :return: A dict with the keys described below.
    """

    # ── STEP 1: Extract ──────────────────────────────────────────────────────
    # Read the PDF and get back a plain text string.
    raw_text = extract_text_from_pdf(pdf_path)

    # If extraction failed, return early with a clear error message.
    if not raw_text:
        return {
            "success":    False,
            "error":      f"Could not extract text from '{pdf_path}'.",
            "students":   [],
            "validation": None,
        }

    # ── STEP 2: Parse ────────────────────────────────────────────────────────
    # Turn the raw text into a list of student dicts
    # (enrollment_no, name, marks).
    parsed_students = parse_student_rows(raw_text, subjects)

    # ── STEP 3: Clean ────────────────────────────────────────────────────────
    # Strip whitespace and uppercase every student name.
    # Marks are left completely unchanged.
    cleaned_students = clean_student_records(parsed_students)

    # ── STEP 4: Validate ─────────────────────────────────────────────────────
    # Check each record for missing fields, wrong mark types,
    # out-of-range values, and duplicate enrollment numbers.
    validation = validate_student_records(cleaned_students, subjects, max_marks)

    # overall_valid is True only when every single record passed validation
    overall_valid = validation["summary"]["invalid"] == 0

    # ── BUILD AND RETURN RESULT ───────────────────────────────────────────────
    return {
        "success":    overall_valid,
        "students":   cleaned_students,
        "validation": validation,
    }
