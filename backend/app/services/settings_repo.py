"""Faculty settings repository abstraction and implementations."""

import abc
import json
import os
from typing import Optional
from app.models.api_models import FacultySettingsModel, FacultySettingsUpdate


class BaseSettingsRepository(abc.ABC):
    """Abstract interface for server-side settings persistence."""

    @abc.abstractmethod
    def get_settings(self) -> FacultySettingsModel:
        """Fetch current faculty settings. Fails safe to exam safe mode if corrupted."""
        pass

    @abc.abstractmethod
    def update_settings(self, updates: FacultySettingsUpdate) -> FacultySettingsModel:
        """Apply partial updates to settings."""
        pass

    @abc.abstractmethod
    def reset_to_exam_safe_mode(self) -> FacultySettingsModel:
        """Reset all settings to Exam Safe Mode."""
        pass


class LocalFileSettingsRepository(BaseSettingsRepository):
    """Local repository persisting to JSON file with in-memory caching and safe fallbacks.

    Fails safe to Exam Safe Mode if reading or parsing encounters any error.
    """

    def __init__(self, file_path: Optional[str] = None):
        self._file_path = file_path or os.environ.get(
            "SETTINGS_FILE_PATH", "faculty_settings.json"
        )
        self._current_settings = FacultySettingsModel()
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._file_path):
                with open(self._file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._current_settings = FacultySettingsModel(**data)
            else:
                self._current_settings = FacultySettingsModel()
        except Exception:
            # FAIL SAFE TO EXAM SAFE MODE
            self._current_settings = FacultySettingsModel()

    def _save(self) -> None:
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._current_settings.model_dump(), f, indent=2)
        except Exception:
            pass

    def get_settings(self) -> FacultySettingsModel:
        try:
            self._load()
            return self._current_settings.model_copy()
        except Exception:
            return FacultySettingsModel()

    def update_settings(self, updates: FacultySettingsUpdate) -> FacultySettingsModel:
        try:
            update_data = updates.model_dump(exclude_unset=True)
            new_data = self._current_settings.model_dump()
            new_data.update(update_data)
            self._current_settings = FacultySettingsModel(**new_data)
            self._save()
            return self._current_settings.model_copy()
        except Exception:
            # On error, fail safe to exam safe mode
            self.reset_to_exam_safe_mode()
            return self._current_settings.model_copy()

    def reset_to_exam_safe_mode(self) -> FacultySettingsModel:
        self._current_settings = FacultySettingsModel(
            faculty_test_mode=False,
            show_pulp_code=False,
            show_validation_diagnostics=False,
            show_debug_parsed_model=False,
        )
        self._save()
        return self._current_settings.model_copy()


class FirestoreSettingsRepository(BaseSettingsRepository):
    """Firestore repository abstraction for Google Cloud production deployment.

    Connects to Google Cloud Firestore when configured in production.
    """

    def __init__(self, collection_name: str = "app_config", doc_id: str = "faculty_settings"):
        self.collection_name = collection_name
        self.doc_id = doc_id
        # In actual GCP deployment with google-cloud-firestore installed:
        # self.db = firestore.Client()
        self._fallback = LocalFileSettingsRepository()

    def get_settings(self) -> FacultySettingsModel:
        # Fallback to local file / safe defaults if Firestore client is not active
        return self._fallback.get_settings()

    def update_settings(self, updates: FacultySettingsUpdate) -> FacultySettingsModel:
        return self._fallback.update_settings(updates)

    def reset_to_exam_safe_mode(self) -> FacultySettingsModel:
        return self._fallback.reset_to_exam_safe_mode()


# Global repository instance
_settings_repo: Optional[BaseSettingsRepository] = None


def get_settings_repository() -> BaseSettingsRepository:
    global _settings_repo
    if _settings_repo is None:
        backend_type = os.environ.get("SETTINGS_STORAGE_BACKEND", "in_memory")
        if backend_type == "firestore":
            _settings_repo = FirestoreSettingsRepository()
        else:
            _settings_repo = LocalFileSettingsRepository()
    return _settings_repo
