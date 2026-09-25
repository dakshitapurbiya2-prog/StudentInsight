from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import List

from backend.services import auth_service

# OAuth2 Scheme specifying token retrieval endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that extracts and verifies the JWT Bearer Token from HTTP headers.
    Returns the authenticated user dict or raises HTTP 401 Unauthorized.
    """
    payload = auth_service.decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Remove hashed password field before returning user object
    if "hashed_password" in user:
        del user["hashed_password"]

    return user


def require_roles(allowed_roles: List[str]):
    """
    FastAPI dependency factory enforcing Role-Based Access Control (RBAC).
    Usage: Depends(require_roles(["HEAD", "TEACHER"]))
    """
    def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = current_user.get("role", "")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required role(s): {', '.join(allowed_roles)}. Your role is '{user_role}'."
            )
        return current_user

    return role_checker


def verify_student_access(current_user: dict, target_student_id: int):
    """
    Enforces privacy boundary for students:
    - HEAD and TEACHER roles can access any student_id.
    - STUDENT role can ONLY access their own student_id.
    """
    user_role = current_user.get("role")
    if user_role == "STUDENT":
        user_student_id = current_user.get("student_id")
        if user_student_id != target_student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. You can only view your own academic records (Your Student ID: {user_student_id})."
            )
