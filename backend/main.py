import sys
import os
from fastapi import FastAPI

# Ensure project root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from backend.api.students import router as students_router
from backend.api.teachers import router as teachers_router
from backend.api.subjects import router as subjects_router
from backend.api.exams import router as exams_router
from backend.api.marks import router as marks_router
from backend.api.analytics import router as analytics_router
from backend.api.director_analytics import router as director_analytics_router

app = FastAPI(
    title="StudentInsight API",
    description="College Academic Performance Analytics System REST API",
    version="1.0.0"
)

# Register API Routers
app.include_router(students_router)
app.include_router(teachers_router)
app.include_router(subjects_router)
app.include_router(exams_router)
app.include_router(marks_router)
app.include_router(analytics_router)
app.include_router(director_analytics_router)


@app.get("/", tags=["Root"])
def root():
    """
    Root API endpoint providing welcome message and interactive documentation links.
    """
    return {
        "project": "StudentInsight",
        "status": "Online",
        "description": "College Academic Performance Analytics REST API",
        "documentation": "/docs",
        "alternative_docs": "/redoc"
    }
