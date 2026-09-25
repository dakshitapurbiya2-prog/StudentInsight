import re


def extract_metadata(text):
    """
    Extract exam-level metadata and subject information from the header of a marksheet PDF.

    Extracts:
        - institution_name : e.g. "BANSAL INSTITUTE OF SCIENCE AND TECHNOLOGY, BHOPAL"
        - course           : e.g. "B.TECH"
        - semester         : e.g. "II"
        - branch           : e.g. "AIML"
        - exam_name        : e.g. "MST-2"
        - exam_session     : e.g. "JULY 2026"
        - maximum_marks    : e.g. {"BT-101": 30, "BT-202": 30, ...}
        - subjects         : e.g. ["BT-101", "BT-202", "BT-103", "BT-104", "BT-105"]
        - academic_year    : None (never guessed automatically from exam_session)
        - warnings         : list of warning strings for teacher review
        - errors           : list of error strings if mandatory fields are missing

    :param text: Raw text extracted from the PDF (or its first page).
    :return: A dictionary containing the extracted metadata, subjects, max_marks, warnings, and errors.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    institution_name = None
    course = None
    semester = None
    branch = None
    exam_name = None
    exam_session = None
    subjects = []
    max_marks = {}
    warnings = []
    errors = []

    # Inspect the first 15 lines where header metadata resides
    header_lines = lines[:15]

    for idx, line in enumerate(header_lines):
        line_upper = line.upper()

        # 1. Institution Name (e.g. BANSAL INSTITUTE OF SCIENCE AND TECHNOLOGY, BHOPAL)
        if not institution_name and any(kw in line_upper for kw in ["INSTITUTE", "COLLEGE", "UNIVERSITY", "SCHOOL", "ACADEMY"]):
            institution_name = line.strip()
            continue

        # 2. Course & Semester (e.g. B.TECH-II SEMESTER)
        if "SEMESTER" in line_upper or "SEM" in line_upper:
            # Extract course
            course_match = re.search(r"\b(B\.?\s*TECH|M\.?\s*TECH|B\.?\s*E\.?|B\.?\s*SC|BCA|MCA|DIPLOMA|MBA)\b", line_upper)
            if course_match:
                course = course_match.group(1).replace(" ", "")

            # Extract semester (Roman numeral or digit)
            sem_match = re.search(r"[-:\s]+([IVXLCDM]+|\d+)\s*(?:ST|ND|RD|TH)?\s*SEM", line_upper)
            if sem_match:
                semester = sem_match.group(1)
            elif not semester:
                sem_match_alt = re.search(r"\b([IVXLCDM]+|\d+)\s*(?:ST|ND|RD|TH)?\s*SEM", line_upper)
                if sem_match_alt:
                    semester = sem_match_alt.group(1)
            continue

        # 3. Branch (e.g. BRANCH-AIML)
        if "BRANCH" in line_upper and not branch:
            branch_match = re.search(r"BRANCH[-:\s]+(.*)", line, re.IGNORECASE)
            if branch_match:
                branch = branch_match.group(1).strip()
            continue

        # 4. Exam Name & Exam Session (e.g. MST-2 MARKS JULY 2026)
        if any(kw in line_upper for kw in ["MST", "MID-SEM", "MID SEM", "EXAM", "TEST"]) and not exam_name:
            if "MARKS" in line_upper:
                parts = re.split(r"\s+MARKS\s*", line, flags=re.IGNORECASE)
                exam_name = parts[0].strip()
                if len(parts) > 1 and parts[1].strip():
                    exam_session = parts[1].strip()
            else:
                exam_name = line.strip()

        # Date session fallback if not already captured with exam name
        if not exam_session:
            session_match = re.search(
                r"\b(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)\s+\d{4}\b",
                line,
                re.IGNORECASE,
            )
            if session_match:
                exam_session = session_match.group(0).strip().upper()

        # 5. Subject codes (e.g. BT-101 BT-202 BT-103 BT-104 BT-105)
        found_subjects = re.findall(r"\b[A-Z]{2,4}-\d{3,4}\b", line)
        if found_subjects and not subjects:
            seen = set()
            for subj in found_subjects:
                if subj in seen:
                    errors.append(f"ERR_DUPLICATE_SUBJECT_CODE: Subject code '{subj}' appears multiple times in header.")
                seen.add(subj)
            subjects = found_subjects

        # 6. Maximum Marks (e.g. row following MAXIMUM MARKS)
        if "MAXIMUM MARKS" in line_upper:
            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                raw_values = next_line.split()
                int_values = []
                for val in raw_values:
                    if val.isdigit():
                        int_values.append(int(val))
                    else:
                        try:
                            int_values.append(int(float(val)))
                        except ValueError:
                            pass
                if len(int_values) == len(subjects):
                    for subj, mark_val in zip(subjects, int_values):
                        max_marks[subj] = mark_val
                else:
                    warnings.append(
                        f"WARN_UNCONFIRMED_MAX_MARKS: Found {len(int_values)} maximum mark values for {len(subjects)} subjects; requires teacher confirmation."
                    )

    # Validate essential fields
    if not course:
        errors.append("ERR_MISSING_EXAM_METADATA: Course could not be determined from header.")
    if not semester:
        errors.append("ERR_MISSING_EXAM_METADATA: Semester could not be determined from header.")
    if not branch:
        errors.append("ERR_MISSING_EXAM_METADATA: Branch could not be determined from header.")
    if not exam_name:
        errors.append("ERR_MISSING_EXAM_METADATA: Exam name could not be determined from header.")
    if not exam_session:
        errors.append("ERR_MISSING_EXAM_METADATA: Exam session could not be determined from header.")
    if not subjects:
        errors.append("ERR_SUBJECT_HEADERS_NOT_FOUND: Subject column headers could not be found.")
    if not max_marks and subjects:
        warnings.append("WARN_UNCONFIRMED_MAX_MARKS: Maximum marks could not be automatically confirmed; requires teacher verification.")

    # Academic year must never be guessed from exam_session
    warnings.append("WARN_ACADEMIC_YEAR_ABSENT: Academic year is not specified in PDF; requires teacher confirmation.")

    return {
        "institution_name": institution_name,
        "course": course,
        "semester": semester,
        "branch": branch,
        "exam_name": exam_name,
        "exam_session": exam_session,
        "maximum_marks": max_marks,
        "subjects": subjects,
        "academic_year": None,
        "warnings": warnings,
        "errors": errors,
    }


def parse_student_rows(text, subjects):
    """
    Parse raw PDF text and return a list of student records.

    Each record contains:
        - serial_number : the row number on the marksheet (integer)
        - roll_number   : the student's roll / enrollment number
        - student_name  : the student's full name
        - name          : alias for student_name
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

        # --- Identify a candidate student row ---
        # A valid student row starts with a serial number digit and an alphanumeric
        # roll number of at least 6 characters (e.g. '1 0112AL251001 AASTHA SAHU 28 23 29 23 15').
        # Non-student lines (e.g. '30 30 30 30 30' or 'MAXIMUM MARKS') are filtered out.
        if len(parts) >= 2 and parts[0].isdigit() and len(parts[1]) >= 6 and parts[1].isalnum():
            try:
                serial_number = int(parts[0])
            except ValueError:
                serial_number = None

            roll_number = parts[1]

            # Case A: Standard row with full complement of marks
            if len(parts) >= 2 + num_subjects:
                mark_tokens = parts[-num_subjects:]
                name_parts = parts[2:-num_subjects]
                student_name = " ".join(name_parts)

                # --- Build the marks dictionary ---
                marks = {}
                for subject, token in zip(subjects, mark_tokens):
                    token_upper = token.upper()

                    # Keep "ABS" as a string — do NOT convert to 0 or None
                    if token_upper == "ABS":
                        marks[subject] = "ABS"
                    else:
                        # Try to convert numeric mark to an integer
                        try:
                            marks[subject] = int(token)
                        except ValueError:
                            try:
                                marks[subject] = int(float(token))
                            except ValueError:
                                # Malformed token preserved as-is for validator to catch
                                marks[subject] = token

            # Case B: Structurally incomplete candidate row (preserve for validator)
            else:
                student_name = " ".join(parts[2:]) if len(parts) > 2 else ""
                marks = {}
                # Populate whatever mark tokens are present
                for idx_m, token in enumerate(parts[2:]):
                    if idx_m < num_subjects:
                        token_upper = token.upper()
                        marks[subjects[idx_m]] = "ABS" if token_upper == "ABS" else token

            # --- Assemble the student record ---
            student = {
                "serial_number": serial_number,
                "roll_number": roll_number,
                "student_name": student_name,
                "name": student_name,
                "marks": marks
            }

            students.append(student)

    return students

