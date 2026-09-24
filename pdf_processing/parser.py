import re


def parse_student_rows(text, subjects):
    """
    Parse raw PDF text and return a list of student records.

    Each record contains:
        - enrollment_no : the student's enrollment number
        - name          : the student's full name
        - marks         : a dict mapping each subject code to its mark
                          (integer, or the string "ABS" if the student was absent)

    :param text:     Raw text string extracted from the PDF.
    :param subjects: List of subject codes in the order they appear in the PDF,
                     e.g. ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"].
    :return:         List of dicts, one per student row found in the text.
    """

    students = []          # will hold one dict per student
    num_subjects = len(subjects)

    # Split the full text into individual lines for easy processing
    lines = text.split("\n")

    for line in lines:
        # Remove extra whitespace from the line
        line = line.strip()
        if not line:
            continue  # skip empty lines

        # Split the line into individual tokens (words / numbers)
        parts = line.split()

        # --- Identify a student row ---
        # A student row looks like:
        #   1  0112AL251001  AASTHA  SAHU  28  23  29  23  15
        #
        # Minimum parts needed:
        #   1 (serial no.) + 1 (enrollment) + 1 (at least one name word) + num_subjects
        min_parts = 1 + 1 + 1 + num_subjects
        if len(parts) < min_parts:
            continue  # not enough tokens — skip this line

        # The first token must be a plain integer (serial number like 1, 2, 3 …)
        if not parts[0].isdigit():
            continue

        # The second token must look like an enrollment number.
        # Enrollment numbers are alphanumeric and at least 6 characters long.
        enrollment_no = parts[1]
        if len(enrollment_no) < 6 or not enrollment_no.isalnum():
            continue

        # The last `num_subjects` tokens are the marks
        mark_tokens = parts[-num_subjects:]

        # Everything between enrollment_no and the marks is the student name
        name_parts = parts[2:-num_subjects]
        name = " ".join(name_parts)

        # --- Build the marks dictionary ---
        marks = {}
        for subject, token in zip(subjects, mark_tokens):
            token_upper = token.upper()

            # Keep "ABS" as a string — do NOT convert to 0
            if token_upper == "ABS":
                marks[subject] = "ABS"
            else:
                # Try to convert the mark to an integer
                try:
                    marks[subject] = int(token)
                except ValueError:
                    # If conversion fails for any reason, store as-is
                    marks[subject] = token

        # --- Assemble the student record ---
        student = {
            "enrollment_no": enrollment_no,
            "name": name,
            "marks": marks
        }

        students.append(student)

    return students
