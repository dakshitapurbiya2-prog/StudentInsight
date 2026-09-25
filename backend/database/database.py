import sqlite3
import os

# Define path for data folder and database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "studentinsight.db")


def get_connection():
    """
    Creates and returns a connection to the SQLite database.
    Also enables foreign key support in SQLite.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_tables():
    """
    Creates all 8 tables in the StudentInsight database if they do not exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Departments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    """)

    # 2. Classes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        class_id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        department_id INTEGER NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (department_id)
    );
    """)

    # 3. Students Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_number TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        FOREIGN KEY (class_id) REFERENCES classes (class_id)
    );
    """)

    # 4. Teachers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE
    );
    """)

    # 5. Subjects Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_name TEXT NOT NULL,
        subject_code TEXT,
        class_id INTEGER NOT NULL,
        teacher_id INTEGER,
        FOREIGN KEY (class_id) REFERENCES classes (class_id),
        FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id)
    );
    """)

    # 6. Exams Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_name TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        exam_date TEXT,
        FOREIGN KEY (class_id) REFERENCES classes (class_id)
    );
    """)

    # 7. Marks Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS marks (
        mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        marks_obtained REAL NOT NULL,
        max_marks REAL NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (student_id),
        FOREIGN KEY (subject_id) REFERENCES subjects (subject_id),
        FOREIGN KEY (exam_id) REFERENCES exams (exam_id)
    );
    """)

    # 8. Users Table (Authentication & RBAC)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT UNIQUE,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('STUDENT', 'TEACHER', 'HEAD')),
        student_id INTEGER,
        teacher_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students (student_id),
        FOREIGN KEY (teacher_id) REFERENCES teachers (teacher_id)
    );
    """)

    # Check and perform migration for existing databases missing subject_code
    cursor.execute("PRAGMA table_info(subjects);")
    columns = [col[1] for col in cursor.fetchall()]
    if "subject_code" not in columns:
        cursor.execute("ALTER TABLE subjects ADD COLUMN subject_code TEXT;")
        print("[+] Migrated database: Added subject_code column to subjects table.")

    conn.commit()
    conn.close()
    print("Database and all 8 tables created successfully!")


if __name__ == "__main__":
    create_tables()
