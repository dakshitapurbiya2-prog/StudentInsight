import re
import json
import csv
from typing import Dict, List, Any, Optional
from pdf_processing.extractor import extract_text_from_pdf


def parse_marksheet_text(text: str, passing_percentage: float = 33.0) -> Dict[str, Any]:
    """
    Parse raw extracted marksheet text into structured data.

    :param text: Raw text extracted from a PDF marksheet.
    :param passing_percentage: Minimum percentage required to pass (default 33.0%).
    :return: A dictionary containing metadata, subjects, max_marks, student records, and class statistics.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    metadata = {
        "institution": "",
        "semester": "",
        "branch": "",
        "exam_name": ""
    }

    subjects: List[str] = []
    max_marks: Dict[str, float] = {}
    students: List[Dict[str, Any]] = []

    # 1. Parse Metadata & Header Information
    subject_line_idx = -1
    max_marks_line_idx = -1

    for idx, line in enumerate(lines[:12]):
        line_upper = line.upper()
        if "INSTITUTE" in line_upper or "COLLEGE" in line_upper or "UNIVERSITY" in line_upper:
            if not metadata["institution"]:
                metadata["institution"] = line
        elif "SEMESTER" in line_upper or "SEM" in line_upper:
            if not metadata["semester"]:
                metadata["semester"] = line
        elif "BRANCH" in line_upper:
            branch_match = re.search(r"BRANCH[-:\s]+(.*)", line, re.IGNORECASE)
            metadata["branch"] = branch_match.group(1).strip() if branch_match else line
        elif any(k in line_upper for k in ["MST", "MID-SEM", "EXAM", "MARKS", "TEST"]) and not metadata["exam_name"]:
            metadata["exam_name"] = line

        # Check for subjects header line (e.g. contains codes like BT-101 or similar patterns)
        found_subjects = re.findall(r"\b[A-Z]{2,4}-\d{3,4}\b", line)
        if found_subjects and not subjects:
            subjects = found_subjects
            subject_line_idx = idx

        if "MAXIMUM MARKS" in line_upper:
            max_marks_line_idx = idx

    # If subjects weren't identified by regex, fallback to line after 'Enrollment No'
    if not subjects:
        for idx, line in enumerate(lines[:12]):
            parts = line.split()
            potential_subjects = [p for p in parts if "-" in p and any(char.isdigit() for char in p)]
            if len(potential_subjects) >= 2:
                subjects = potential_subjects
                subject_line_idx = idx
                break

    # 2. Parse Maximum Marks
    if max_marks_line_idx != -1 and max_marks_line_idx + 1 < len(lines):
        next_line = lines[max_marks_line_idx + 1]
        max_marks_values = [float(val) for val in next_line.split() if val.replace(".", "", 1).isdigit()]
        if len(max_marks_values) == len(subjects):
            for subj, m_val in zip(subjects, max_marks_values):
                max_marks[subj] = m_val

    # Default max marks if not found or mismatch
    for subj in subjects:
        if subj not in max_marks:
            max_marks[subj] = 30.0  # default from sample data

    num_subjects = len(subjects)
    absent_flags = {"ABS", "AB", "A", "NA", "-", "ABSENT"}

    # 3. Parse Student Records
    start_parsing = False
    for line in lines:
        parts = line.split()
        if not parts:
            continue

        # Look for rows starting with S.No (digit) followed by Enrollment No (alphanumeric length >= 6)
        if len(parts) >= 2 + num_subjects and parts[0].isdigit() and len(parts[1]) >= 6:
            try:
                s_no = int(parts[0])
            except ValueError:
                continue

            enrollment_no = parts[1]
            mark_tokens = parts[-num_subjects:]
            name_parts = parts[2:-num_subjects]
            student_name = " ".join(name_parts)

            subject_marks: Dict[str, Optional[float]] = {}
            subject_status: Dict[str, str] = {}
            total_obtained = 0.0
            total_max = 0.0
            attended_subjects_count = 0

            for subj, token in zip(subjects, mark_tokens):
                clean_token = token.strip().upper()
                if clean_token in absent_flags:
                    subject_marks[subj] = None
                    subject_status[subj] = "ABSENT"
                else:
                    try:
                        m_val = float(clean_token)
                        subject_marks[subj] = m_val
                        subject_status[subj] = "PRESENT"
                        total_obtained += m_val
                        attended_subjects_count += 1
                    except ValueError:
                        subject_marks[subj] = None
                        subject_status[subj] = "UNKNOWN"

                total_max += max_marks.get(subj, 30.0)

            # Performance stats
            if attended_subjects_count == 0:
                overall_status = "ABSENT"
                percentage = 0.0
            else:
                percentage = round((total_obtained / total_max) * 100, 2) if total_max > 0 else 0.0
                overall_status = "PASS" if percentage >= passing_percentage else "FAIL"

            students.append({
                "s_no": s_no,
                "roll_number": enrollment_no,
                "name": student_name,
                "marks": subject_marks,
                "subject_status": subject_status,
                "total_obtained": total_obtained,
                "total_max": total_max,
                "percentage": percentage,
                "status": overall_status
            })

    # 4. Compute Aggregate Statistics
    total_students = len(students)
    passed_students = sum(1 for s in students if s["status"] == "PASS")
    failed_students = sum(1 for s in students if s["status"] == "FAIL")
    all_absent_students = sum(1 for s in students if s["status"] == "ABSENT")

    subject_stats: Dict[str, Dict[str, Any]] = {}
    for subj in subjects:
        valid_marks = [s["marks"][subj] for s in students if s["marks"].get(subj) is not None]
        absent_count = total_students - len(valid_marks)
        if valid_marks:
            avg_mark = round(sum(valid_marks) / len(valid_marks), 2)
            highest_mark = max(valid_marks)
            lowest_mark = min(valid_marks)
        else:
            avg_mark, highest_mark, lowest_mark = 0.0, 0.0, 0.0

        subject_stats[subj] = {
            "max_marks": max_marks.get(subj, 30.0),
            "appeared": len(valid_marks),
            "absent": absent_count,
            "average": avg_mark,
            "highest": highest_mark,
            "lowest": lowest_mark
        }

    class_average = (
        round(sum(s["percentage"] for s in students if s["status"] != "ABSENT") / max(1, (total_students - all_absent_students)), 2)
        if total_students > all_absent_students else 0.0
    )

    return {
        "metadata": metadata,
        "subjects": subjects,
        "max_marks": max_marks,
        "total_students": total_students,
        "summary": {
            "total_students": total_students,
            "passed": passed_students,
            "failed": failed_students,
            "all_absent": all_absent_students,
            "pass_rate_percentage": round((passed_students / total_students) * 100, 2) if total_students > 0 else 0.0,
            "class_average_percentage": class_average
        },
        "subject_statistics": subject_stats,
        "students": students
    }


def parse_marksheet_pdf(pdf_path: str, passing_percentage: float = 33.0) -> Dict[str, Any]:
    """
    Extract and parse marksheet PDF directly into structured data.

    :param pdf_path: Path to the PDF file.
    :param passing_percentage: Minimum percentage required to pass.
    :return: Parsed structured dictionary.
    """
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text:
        return {"error": f"Failed to extract text from '{pdf_path}'", "students": []}
    return parse_marksheet_text(raw_text, passing_percentage=passing_percentage)


def to_import_records(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert parsed marksheet data into normalized records suitable for backend import.
    Compatible with backend/services/marks_import_service.py process_marks_import.

    :param parsed_data: Dictionary returned by parse_marksheet_text or parse_marksheet_pdf.
    :return: List of record dictionaries: [{'roll_number': ..., 'student_name': ..., 'subject': ..., 'marks': ...}]
    """
    import_records = []
    students = parsed_data.get("students", [])

    for student in students:
        roll_number = student.get("roll_number")
        student_name = student.get("name")
        marks_dict = student.get("marks", {})

        for subject, marks in marks_dict.items():
            # If absent, marks is None, which can be skipped or recorded as 0 based on policy
            if marks is not None:
                import_records.append({
                    "roll_number": roll_number,
                    "student_name": student_name,
                    "subject": subject,
                    "marks": marks
                })

    return import_records


def export_to_json(parsed_data: Dict[str, Any], output_path: Optional[str] = None, indent: int = 2) -> str:
    """
    Serialize parsed data to JSON string, and optionally write to a file.
    """
    json_str = json.dumps(parsed_data, indent=indent)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
    return json_str


def export_to_csv(parsed_data: Dict[str, Any], output_path: str) -> None:
    """
    Export parsed student records to a tabular CSV file.
    """
    students = parsed_data.get("students", [])
    subjects = parsed_data.get("subjects", [])

    if not students:
        return

    headers = ["S.No", "Enrollment No", "Name"] + subjects + ["Total Obtained", "Total Max", "Percentage", "Status"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for s in students:
            row = [s["s_no"], s["roll_number"], s["name"]]
            for subj in subjects:
                val = s["marks"].get(subj)
                row.append(val if val is not None else "ABS")
            row.extend([s["total_obtained"], s["total_max"], s["percentage"], s["status"]])
            writer.writerow(row)
