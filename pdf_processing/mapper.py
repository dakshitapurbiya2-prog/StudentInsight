from typing import Dict, List, Any, Optional


def map_to_backend_payload(
    confirmed_data: Dict[str, Any],
    exam_id: Optional[int] = None,
    max_marks: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Convert confirmed Structure A marksheet data into the Structure B payload
    expected by the backend endpoint `POST /marks/import`.

    Pivots wide-format student rows (1 row = N subjects) into normalized
    relational records (1 record = 1 student x 1 subject).

    Transformation Rules:
    1. For each student, iterates through each subject mark in `student["marks"]`.
    2. Emits a flattened record:
       {
           "roll_number": student["roll_number"],
           "subject_code": subject_code,
           "marks": mark  # integer or literal "ABS"
       }
    3. ABS Preservation: "ABS" is strictly preserved as the string "ABS" (never coerced to 0).
    4. Resolves `max_marks`: If not explicitly provided, uses the first maximum mark value
       found in `metadata["maximum_marks"]` as a float (e.g. 30.0).

    :param confirmed_data: Standardized Structure A dictionary containing 'metadata' and 'students'.
    :param exam_id: Target database exam ID integer (e.g. 2).
    :param max_marks: Optional float representing the exam max marks (e.g. 30.0).
    :return: Structure B dictionary with 'exam_id', 'max_marks', and 'records' list.
    """
    if not isinstance(confirmed_data, dict):
        raise TypeError("confirmed_data must be a dictionary representing Structure A.")

    students = confirmed_data.get("students", [])
    metadata = confirmed_data.get("metadata", {})
    declared_subjects = confirmed_data.get("subjects", [])

    # Resolve max_marks if not explicitly supplied
    resolved_max_marks: float = 100.0
    if max_marks is not None:
        resolved_max_marks = float(max_marks)
    else:
        meta_max_marks = metadata.get("maximum_marks", {})
        if meta_max_marks:
            # Derive from first subject's max marks if available
            first_val = next(iter(meta_max_marks.values()))
            try:
                resolved_max_marks = float(first_val)
            except (ValueError, TypeError):
                resolved_max_marks = 100.0

    # Build relational records (wide to long)
    records: List[Dict[str, Any]] = []

    for student in students:
        roll_number = student.get("roll_number", "").strip().upper()
        marks_dict = student.get("marks", {})

        # Order subjects consistently using declared subjects if available
        target_subjects = declared_subjects if declared_subjects else list(marks_dict.keys())

        for subj_code in target_subjects:
            if subj_code in marks_dict:
                mark_val = marks_dict[subj_code]

                # Preserve "ABS" as string, otherwise preserve integer/number
                if str(mark_val).strip().upper() == "ABS":
                    clean_mark = "ABS"
                else:
                    try:
                        clean_mark = int(mark_val)
                    except (ValueError, TypeError):
                        try:
                            clean_mark = float(mark_val)
                        except (ValueError, TypeError):
                            clean_mark = mark_val

                record = {
                    "roll_number": roll_number,
                    "subject_code": str(subj_code).strip().upper(),
                    "marks": clean_mark,
                }
                records.append(record)

    return {
        "exam_id": exam_id,
        "max_marks": resolved_max_marks,
        "records": records,
    }
