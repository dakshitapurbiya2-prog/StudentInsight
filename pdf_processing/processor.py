from typing import Optional, List, Dict, Any
from pdf_processing.extractor import extract_text_from_pdf
from pdf_processing.parser import extract_metadata, parse_student_rows
from pdf_processing.cleaner import clean_student_records
from pdf_processing.validator import validate_student_records
from pdf_processing.normalizer import normalize_extracted_data


def process_pdf(
    pdf_path: str,
    subjects: Optional[List[str]] = None,
    max_marks: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Run the complete PDF processing pipeline in one call.

    Pipeline Steps (in order):
        1. Extract   — read raw text from the PDF file.
        2. Metadata  — extract or adopt exam metadata and subject codes.
        3. Parse     — find student rows and build raw record dicts.
        4. Clean     — strip whitespace and normalise names to uppercase.
        5. Validate  — check roll numbers, names, subjects, marks, duplicates.
        6. Normalize — assemble canonical internal Structure A representation.

    :param pdf_path:  Path to the PDF file, e.g. "sample_data/college_marks.pdf".
    :param subjects:  Optional list of subject codes in PDF column order.
                      If None, automatically extracted from PDF header.
    :param max_marks: Optional dict mapping subject code -> maximum allowed mark.
                      If None, automatically extracted from PDF header.
    :return: A dict containing:
             - 'success'    : bool, True if all records are valid and extraction succeeded
             - 'students'   : list of cleaned student records
             - 'validation' : validation report dictionary
             - 'metadata'   : extracted exam metadata dictionary
             - 'structure_a': standardized Structure A dictionary
    """

    # ── STEP 1: Extract Text ─────────────────────────────────────────────────
    raw_text = extract_text_from_pdf(pdf_path)

    if not raw_text:
        return {
            "success": False,
            "error": f"Could not extract text from '{pdf_path}'.",
            "errors": [f"ERR_NO_EXTRACTABLE_TEXT: Could not extract text from '{pdf_path}'."],
            "warnings": [],
            "students": [],
            "validation": None,
            "metadata": {},
            "structure_a": None,
        }

    # ── STEP 2: Extract & Resolve Metadata ───────────────────────────────────
    extracted_meta = extract_metadata(raw_text)

    # Use provided subjects or fall back to extracted ones
    resolved_subjects = (
        subjects if subjects is not None else extracted_meta.get("subjects", [])
    )

    # Use provided max_marks or fall back to extracted ones
    resolved_max_marks = (
        max_marks
        if max_marks is not None
        else extracted_meta.get("maximum_marks", {})
    )

    # Build active metadata dictionary for normalization
    metadata = {
        **extracted_meta,
        "subjects": resolved_subjects,
        "maximum_marks": resolved_max_marks,
    }

    # ── STEP 3: Parse Student Rows ───────────────────────────────────────────
    parsed_students = parse_student_rows(raw_text, resolved_subjects)

    # ── STEP 4: Clean Records ────────────────────────────────────────────────
    cleaned_students = clean_student_records(parsed_students)

    # ── STEP 5: Validate Records ─────────────────────────────────────────────
    validation = validate_student_records(
        cleaned_students, resolved_subjects, resolved_max_marks
    )

    # ── STEP 6: Normalize to Standardized Structure A ─────────────────────────
    structure_a = normalize_extracted_data(metadata, cleaned_students)

    # ── STEP 7: Consolidate Warnings & Errors ─────────────────────────────────
    all_warnings = list(extracted_meta.get("warnings", []))
    all_errors = list(extracted_meta.get("errors", []))

    # Detect absent students warning
    abs_students_count = sum(
        1 for s in cleaned_students if any(v == "ABS" for v in s.get("marks", {}).values())
    )
    if abs_students_count > 0:
        all_warnings.append(
            f"WARN_ABSENT_STUDENTS_DETECTED: {abs_students_count} student(s) contain 'ABS' mark entries; teacher review recommended."
        )

    # Collect row-level validation errors
    for row_res in validation.get("results", []):
        if not row_res.get("is_valid", True):
            for err in row_res.get("errors", []):
                all_errors.append(
                    f"Row {row_res.get('index', '?')} ({row_res.get('roll_number', '?')}): {err}"
                )

    # Success requires 0 invalid student records AND 0 fatal metadata errors
    overall_valid = (validation["summary"]["invalid"] == 0) and (len(all_errors) == 0)

    # ── BUILD AND RETURN RESULT ───────────────────────────────────────────────
    return {
        "success": overall_valid,
        "students": cleaned_students,
        "validation": validation,
        "metadata": metadata,
        "structure_a": structure_a,
        "warnings": all_warnings,
        "errors": all_errors,
    }

