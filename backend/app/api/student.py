"""Student-facing API endpoints."""

from fastapi import APIRouter, Depends
from app.models.api_models import SolveRequest, SolveResponse
from app.services.settings_repo import get_settings_repository, BaseSettingsRepository
from app.auth import optional_faculty_admin
from app.services.pipeline import process_formulation

router = APIRouter(prefix="/api", tags=["Student"])


@router.post("/solve", response_model=SolveResponse)
def solve_formulation(
    req: SolveRequest,
    repo: BaseSettingsRepository = Depends(get_settings_repository),
    is_faculty: bool = Depends(optional_faculty_admin),
) -> SolveResponse:
    """Submit a mathematical formulation to be validated and solved."""
    faculty_settings = repo.get_settings()
    # Student exam portal always includes generated Python PuLP code in solver results
    if not faculty_settings.show_pulp_code:
        faculty_settings = faculty_settings.model_copy(update={"show_pulp_code": True})
    return process_formulation(
        raw_submission=req.formulation,
        faculty_settings=faculty_settings,
        is_authorized_faculty=is_faculty,
    )


@router.get("/config/public")
def get_public_config(
    repo: BaseSettingsRepository = Depends(get_settings_repository),
):
    """Returns only public configuration safe for student view."""
    settings = repo.get_settings()
    return {
        "faculty_test_mode": settings.faculty_test_mode,
    }


@router.get("/health")
def api_health():
    return {"status": "ok", "app": "Optimization Solver"}
