import sys
import os
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
import jwt

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.database.database import get_connection

# JWT Configuration
SECRET_KEY = "studentinsight-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 Hours validity


# ------------------------------------------------------------------
# Password Hashing & Verification (PBKDF2-HMAC-SHA256)
# ------------------------------------------------------------------
def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with a 16-byte random salt.
    Returns string in format: salt_hex$hash_hex
    """
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}${hashed.hex()}"


def verify_password(plain_password: str, stored_password_hash: str) -> bool:
    """
    Verifies a plain-text password against a stored salt$hash string.
    Uses hmac.compare_digest to prevent timing-attack vulnerabilities.
    """
    try:
        salt_hex, hash_hex = stored_password_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        computed_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(computed_hash, expected_hash)
    except Exception:
        return False


# ------------------------------------------------------------------
# JWT Token Generation & Verification
# ------------------------------------------------------------------
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Generates a signed JWT Bearer Access Token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decodes and validates a signed JWT Bearer Access Token.
    Returns token payload dict on success, or None on failure/expiration.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


# ------------------------------------------------------------------
# User Database Operations
# ------------------------------------------------------------------
def register_user(username: str, password: str, role: str, email: str = None, student_id: int = None, teacher_id: int = None):
    """
    Registers a new user account with hashed password and role ('STUDENT', 'TEACHER', 'HEAD').
    Returns new user_id on success, or None on failure.
    """
    valid_roles = ["STUDENT", "TEACHER", "HEAD"]
    role = role.upper().strip()
    if role not in valid_roles:
        print(f"Error: Invalid role '{role}'. Must be one of {valid_roles}")
        return None

    hashed_pw = hash_password(password)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (username, email, hashed_password, role, student_id, teacher_id)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (username.strip(), email.strip() if email else None, hashed_pw, role, student_id, teacher_id)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.Error as e:
        print(f"Error registering user '{username}': {e}")
        return None
    finally:
        conn.close()


def get_user_by_username(username: str):
    """
    Retrieves user account record by username.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, username, email, hashed_password, role, student_id, teacher_id, created_at
        FROM users
        WHERE username = ?;
        """,
        (username.strip(),)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "username": row[1],
        "email": row[2],
        "hashed_password": row[3],
        "role": row[4],
        "student_id": row[5],
        "teacher_id": row[6],
        "created_at": row[7]
    }


def get_user_by_id(user_id: int):
    """
    Retrieves user account record by user_id.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, username, email, role, student_id, teacher_id, created_at
        FROM users
        WHERE user_id = ?;
        """,
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "username": row[1],
        "email": row[2],
        "role": row[3],
        "student_id": row[4],
        "teacher_id": row[5],
        "created_at": row[6]
    }


def authenticate_user(username: str, password: str):
    """
    Authenticates a user with username and password.
    Returns user dict on success, or None on authentication failure.
    """
    user = get_user_by_username(username)
    if not user:
        return None

    if not verify_password(password, user["hashed_password"]):
        return None

    # Omit hashed_password from returned user object for security
    user_data = user.copy()
    del user_data["hashed_password"]
    return user_data
