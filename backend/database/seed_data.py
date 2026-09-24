import sqlite3
import os
import random

# Define path for data folder and database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "studentinsight.db")


def seed_database():
    """
    Inserts sample data into the StudentInsight database.
    This script is idempotent (safe to run multiple times without creating duplicate records).
    """
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}. Please run database.py first.")
        return

    print("Connecting to database to insert sample data...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # -------------------------------------------------------------
    # 1. Insert Department
    # -------------------------------------------------------------
    dept_name = "AI & ML"
    cursor.execute("INSERT OR IGNORE INTO departments (name) VALUES (?);", (dept_name,))
    cursor.execute("SELECT department_id FROM departments WHERE name = ?;", (dept_name,))
    dept_id = cursor.fetchone()[0]
    print(f"[+] Department verified: {dept_name} (ID: {dept_id})")

    # -------------------------------------------------------------
    # 2. Insert Classes
    # -------------------------------------------------------------
    class_names = ["AIML-A", "AIML-B"]
    class_ids = {}

    for cname in class_names:
        cursor.execute(
            "SELECT class_id FROM classes WHERE class_name = ? AND department_id = ?;",
            (cname, dept_id)
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO classes (class_name, department_id) VALUES (?, ?);",
                (cname, dept_id)
            )
            class_id = cursor.lastrowid
        else:
            class_id = row[0]
        class_ids[cname] = class_id

    print(f"[+] Classes verified: {list(class_ids.keys())}")

    # -------------------------------------------------------------
    # 3. Insert Teachers
    # -------------------------------------------------------------
    teachers_data = [
        ("Mr. Sharma", "sharma@college.edu"),
        ("Ms. Patil", "patil@college.edu"),
        ("Mr. Verma", "verma@college.edu")
    ]
    teacher_ids = {}

    for name, email in teachers_data:
        cursor.execute("INSERT OR IGNORE INTO teachers (name, email) VALUES (?, ?);", (name, email))
        cursor.execute("SELECT teacher_id FROM teachers WHERE email = ?;", (email,))
        t_id = cursor.fetchone()[0]
        teacher_ids[name] = t_id

    print(f"[+] Teachers verified: {list(teacher_ids.keys())}")

    # -------------------------------------------------------------
    # 4. Insert Students
    # -------------------------------------------------------------
    students_data = [
        # (roll_number, name, class_name)
        ("101", "Rahul", "AIML-A"),
        ("102", "Priya", "AIML-A"),
        ("103", "Arjun", "AIML-A"),
        ("104", "Sneha", "AIML-A"),
        ("105", "Aman", "AIML-A"),
        ("201", "Riya", "AIML-B"),
        ("202", "Karan", "AIML-B"),
        ("203", "Neha", "AIML-B")
    ]
    student_ids = {}

    for roll, sname, cname in students_data:
        cid = class_ids[cname]
        cursor.execute("INSERT OR IGNORE INTO students (roll_number, name, class_id) VALUES (?, ?, ?);", (roll, sname, cid))
        cursor.execute("SELECT student_id FROM students WHERE roll_number = ?;", (roll,))
        sid = cursor.fetchone()[0]
        student_ids[roll] = (sid, sname, cid)

    print(f"[+] Total Students verified: {len(student_ids)}")

    # -------------------------------------------------------------
    # 5. Insert Subjects (for both AIML-A and AIML-B)
    # -------------------------------------------------------------
    subjects_list = [
        ("Python", "Mr. Sharma"),
        ("Mathematics", "Ms. Patil"),
        ("DBMS", "Mr. Verma"),
        ("Machine Learning", "Mr. Sharma")
    ]
    
    # Store subject IDs as mapping: (class_id, subject_name) -> subject_id
    subject_ids = {}

    for cname, cid in class_ids.items():
        for sub_name, teacher_name in subjects_list:
            tid = teacher_ids[teacher_name]
            cursor.execute(
                "SELECT subject_id FROM subjects WHERE subject_name = ? AND class_id = ?;",
                (sub_name, cid)
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO subjects (subject_name, class_id, teacher_id) VALUES (?, ?, ?);",
                    (sub_name, cid, tid)
                )
                sub_id = cursor.lastrowid
            else:
                sub_id = row[0]
            subject_ids[(cid, sub_name)] = sub_id

    print(f"[+] Subjects verified across all classes.")

    # -------------------------------------------------------------
    # 6. Insert Exams
    # -------------------------------------------------------------
    exams_list = [
        ("Unit Test 1", "2026-08-10"),
        ("Midterm", "2026-09-15"),
        ("Unit Test 2", "2026-10-20")
    ]
    
    # Store exam IDs as mapping: (class_id, exam_name) -> exam_id
    exam_ids = {}

    for cname, cid in class_ids.items():
        for ename, edate in exams_list:
            cursor.execute(
                "SELECT exam_id FROM exams WHERE exam_name = ? AND class_id = ?;",
                (ename, cid)
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "INSERT INTO exams (exam_name, class_id, exam_date) VALUES (?, ?, ?);",
                    (ename, cid, edate)
                )
                eid = cursor.lastrowid
            else:
                eid = row[0]
            exam_ids[(cid, ename)] = eid

    print(f"[+] Exams verified across all classes.")

    # -------------------------------------------------------------
    # 7. Insert Marks for all students, subjects, and exams
    # -------------------------------------------------------------
    # Set a seed so random marks generated are consistent across runs
    random.seed(42)

    marks_inserted_count = 0

    for roll, (sid, sname, cid) in student_ids.items():
        for sub_name, _ in subjects_list:
            sub_id = subject_ids[(cid, sub_name)]
            for ename, _ in exams_list:
                eid = exam_ids[(cid, ename)]

                # Check if mark record already exists
                cursor.execute(
                    """
                    SELECT mark_id FROM marks 
                    WHERE student_id = ? AND subject_id = ? AND exam_id = ?;
                    """,
                    (sid, sub_id, eid)
                )
                if not cursor.fetchone():
                    # Generate realistic sample mark between 60.0 and 98.0 out of 100.0
                    marks_obtained = round(random.uniform(62.0, 96.0), 1)
                    max_marks = 100.0

                    cursor.execute(
                        """
                        INSERT INTO marks (student_id, subject_id, exam_id, marks_obtained, max_marks)
                        VALUES (?, ?, ?, ?, ?);
                        """,
                        (sid, sub_id, eid, marks_obtained, max_marks)
                    )
                    marks_inserted_count += 1

    # Commit all database operations
    conn.commit()
    conn.close()

    print("=" * 60)
    print("SUCCESS: Sample data inserted into StudentInsight database successfully!")
    print(f"Total new marks records added: {marks_inserted_count}")
    print("=" * 60)


if __name__ == "__main__":
    seed_database()
