import sqlite3
import os

# Define path for data folder and database file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "studentinsight.db")


def test_database_connection():
    """
    Connects to studentinsight.db, retrieves all user-created table names,
    and prints them to verify the database structure.
    """
    print(f"Connecting to database at: {DB_PATH}\n")

    # 1. Connect to the SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2. Query SQLite metadata table to get all user-created table names
    # (We exclude 'sqlite_sequence' which is an internal SQLite tracking table)
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name NOT LIKE 'sqlite_%';
    """)

    # 3. Fetch all table names returned by the query
    tables = cursor.fetchall()

    print("Found the following tables in StudentInsight database:")
    print("-" * 45)

    for index, table in enumerate(tables, start=1):
        table_name = table[0]
        print(f"{index}. {table_name}")

    print("-" * 45)

    # 4. Close the cursor and connection properly
    cursor.close()
    conn.close()
    print("Database connection closed successfully.")


if __name__ == "__main__":
    test_database_connection()
