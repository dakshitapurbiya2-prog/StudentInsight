def validate_student_records(students, subjects, max_marks):
    """
    Validate a list of cleaned student records.

    Checks performed for every student:
        - roll_number is present (not empty).
        - name is present (not empty).
        - All expected subjects exist in the marks dict.
        - Each mark is either an integer or the string "ABS".
        - Numeric marks are between 0 and the subject's maximum marks.

    Also checks across all students:
        - No two students share the same roll number (duplicate detection).

    Does NOT modify student data in any way.

    :param students:  List of cleaned student dicts from clean_student_records().
    :param subjects:  List of expected subject codes, e.g. ["BT-101", "BT-202", ...].
    :param max_marks: Dict mapping subject code -> maximum allowed mark, e.g. {"BT-101": 30}.
    :return: A dict with two keys:
                "summary"  -> overall counts (total, valid, invalid)
                "results"  -> list of per-student result dicts
    """

    results = []               # one result dict per student
    seen_roll_numbers = {}     # used to detect duplicate roll numbers

    for index, student in enumerate(students):

        errors = []            # list of error messages for this student

        # ── 1. Check roll number ─────────────────────────────────────────────
        roll_number = student.get("roll_number", "").strip()
        if not roll_number:
            errors.append("Missing roll number.")

        # ── 2. Check student name ────────────────────────────────────────────
        name = (student.get("student_name") or student.get("name") or "").strip()
        if not name:
            errors.append("Missing student name.")

        # ── 3. Duplicate roll number detection ───────────────────────────────
        if roll_number:
            if roll_number in seen_roll_numbers:
                # Record which earlier row also has this number
                earlier_index = seen_roll_numbers[roll_number]
                errors.append(
                    f"Duplicate roll number. "
                    f"Already seen at row index {earlier_index}."
                )
            else:
                # First time we see this roll number — remember its position
                seen_roll_numbers[roll_number] = index

        # ── 4. Check marks ───────────────────────────────────────────────────
        marks = student.get("marks", {})

        for subject in subjects:

            # Check that the subject key exists at all
            if subject not in marks:
                errors.append(f"Missing marks for subject '{subject}'.")
                continue  # nothing more to check for this subject

            mark = marks[subject]

            # "ABS" is a valid absent status — accept it as-is
            if mark == "ABS":
                continue  # valid, no error

            # Mark must be an integer (not a float, not a string)
            if not isinstance(mark, int):
                errors.append(
                    f"Invalid mark for '{subject}': {repr(mark)}. "
                    f"Expected an integer or 'ABS'."
                )
                continue  # skip range check when type is already wrong

            # Mark must be between 0 and the subject's maximum
            subject_max = max_marks.get(subject, 0)
            if mark < 0 or mark > subject_max:
                errors.append(
                    f"Mark out of range for '{subject}': {mark}. "
                    f"Allowed range is 0 to {subject_max}."
                )

        # ── 5. Build this student's result ───────────────────────────────────
        is_valid = len(errors) == 0

        results.append({
            "index":         index,
            "serial_number": student.get("serial_number"),
            "roll_number":   roll_number or "(missing)",
            "student_name":  name or "(missing)",
            "name":          name or "(missing)",
            "is_valid":      is_valid,
            "errors":        errors
        })

    # ── 6. Build the overall summary ─────────────────────────────────────────
    total   = len(results)
    valid   = sum(1 for r in results if r["is_valid"])
    invalid = total - valid

    return {
        "summary": {
            "total":   total,
            "valid":   valid,
            "invalid": invalid
        },
        "results": results
    }
