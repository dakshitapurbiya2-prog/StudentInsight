from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional

from backend.services import auth_service
from backend.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication & Access Control"])


# Pydantic Schemas for Request & Response Validation
class UserRegisterRequest(BaseModel):
    username: str
    password: str
    role: str  # Must be 'STUDENT', 'TEACHER', or 'HEAD'
    email: Optional[str] = None
    student_id: Optional[int] = None
    teacher_id: Optional[int] = None


class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str
    student_id: Optional[int] = None
    teacher_id: Optional[int] = None


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    email: Optional[str] = None
    role: str
    student_id: Optional[int] = None
    teacher_id: Optional[int] = None
    created_at: Optional[str] = None


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user_endpoint(user_data: UserRegisterRequest):
    """
    Register a new user account with hashed password storage.
    Allowed roles: STUDENT, TEACHER, HEAD.
    """
    user_id = auth_service.register_user(
        username=user_data.username,
        password=user_data.password,
        role=user_data.role,
        email=user_data.email,
        student_id=user_data.student_id,
        teacher_id=user_data.teacher_id
    )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User registration failed. Username or email may already be registered, or role is invalid."
        )

    return {
        "message": f"User '{user_data.username}' successfully registered with role '{user_data.role.upper()}'.",
        "user_id": user_id
    }


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login_endpoint(login_data: UserLoginRequest):
    """
    Authenticate user with username and password, returning a signed JWT Bearer Access Token.
    """
    user = auth_service.authenticate_user(login_data.username, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT token containing user identity and role claim
    token_data = {
        "sub": user["username"],
        "user_id": user["user_id"],
        "role": user["role"],
        "student_id": user["student_id"],
        "teacher_id": user["teacher_id"]
    }
    access_token = auth_service.create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "student_id": user["student_id"],
        "teacher_id": user["teacher_id"]
    }


@router.get("/me", response_model=UserProfileResponse, status_code=status.HTTP_200_OK)
def get_current_user_profile_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Retrieve current logged-in user profile and permissions from JWT token.
    """
    return current_user
