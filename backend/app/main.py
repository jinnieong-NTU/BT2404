"""FastAPI Application Entry Point.

Optimization Solver - Restricted University Examination Application.
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.student import router as student_router
from app.api.faculty import router as faculty_router
from app.config import settings

app = FastAPI(
    title="Optimization Solver",
    description="Restricted University Examination Application for Mathematical Optimization",
    version="1.0.0",
    docs_url=None,  # Disabled in production for security
    redoc_url=None,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handler to prevent any information leakage (Section 67)
@app.exception_handler(Exception)
async def global_safe_exception_handler(request: Request, exc: Exception):
    # Log internally on server only, never expose traceback to student
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing the request."},
    )


# Health check for Google Cloud Run
@app.get("/healthz", tags=["Health"])
def health_check():
    return {"status": "ok", "app": "Optimization Solver"}


# Include API Routers
app.include_router(student_router)
app.include_router(faculty_router)

# Mount Frontend Static Assets
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
static_dir = os.path.join(frontend_dir, "static")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/faculty", include_in_schema=False)
@app.get("/faculty/", include_in_schema=False)
@app.get("/faculty.html", include_in_schema=False)
def get_faculty_page():
    """Serves the Faculty Control Interface."""
    faculty_file = os.path.join(frontend_dir, "faculty.html")
    if os.path.exists(faculty_file):
        return FileResponse(faculty_file)
    return JSONResponse(status_code=404, content={"detail": "Faculty interface file not found."})


@app.get("/", include_in_schema=False)
@app.get("/index", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def get_student_page():
    """Serves the Student Examination Interface."""
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse(status_code=404, content={"detail": "Student examination interface file not found."})
