def clean_student_records(students):
    """
    Clean a list of student dictionaries produced by parse_student_rows().

    What this function does:
        - Strips leading/trailing whitespace from enrollment numbers and names.
        - Converts student names to uppercase.
        - Leaves all marks completely unchanged.

    What this function does NOT do:
        - Does not convert "ABS" to 0 or any other value.
        - Does not validate marks.
        - Does not calculate totals or percentages.

    :param students: List of dicts returned by parse_student_rows().
    :return:         A new list of cleaned student dicts.
    """

    cleaned_students = []  # will hold the cleaned records

    for student in students:

        # Strip whitespace from enrollment number
        clean_enrollment = student["enrollment_no"].strip()

        # Strip whitespace and convert name to uppercase
        clean_name = student["name"].strip().upper()

        # Keep the marks dict exactly as-is (ABS stays "ABS", numbers stay numbers)
        clean_marks = student["marks"]

        # Build the cleaned student record
        cleaned_student = {
            "enrollment_no": clean_enrollment,
            "name": clean_name,
            "marks": clean_marks
        }

        cleaned_students.append(cleaned_student)

    return cleaned_students
