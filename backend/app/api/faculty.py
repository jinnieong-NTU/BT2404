"""Protected Faculty-only API endpoints."""

from fastapi import APIRouter, Depends
from app.models.api_models import FacultySettingsModel, FacultySettingsUpdate
from app.services.settings_repo import get_settings_repository, BaseSettingsRepository
from app.auth import require_faculty_admin

router = APIRouter(prefix="/api/faculty", tags=["Faculty"])


@router.get("/settings", response_model=FacultySettingsModel)
def get_settings(
    _: bool = Depends(require_faculty_admin),
    repo: BaseSettingsRepository = Depends(get_settings_repository),
) -> FacultySettingsModel:
    """Retrieve current faculty settings.

    Requires faculty authorization.
    """
    return repo.get_settings()


@router.patch("/settings", response_model=FacultySettingsModel)
def update_settings(
    updates: FacultySettingsUpdate,
    _: bool = Depends(require_faculty_admin),
    repo: BaseSettingsRepository = Depends(get_settings_repository),
) -> FacultySettingsModel:
    """Update faculty settings.

    Requires faculty authorization.
    """
    return repo.update_settings(updates)


@router.post("/exam-safe-mode", response_model=FacultySettingsModel)
def enable_exam_safe_mode(
    _: bool = Depends(require_faculty_admin),
    repo: BaseSettingsRepository = Depends(get_settings_repository),
) -> FacultySettingsModel:
    """Enforce Exam Safe Mode immediately.

    Disables test mode, PuLP code display, diagnostics, and debug models.
    Requires faculty authorization.
    """
    return repo.reset_to_exam_safe_mode()
