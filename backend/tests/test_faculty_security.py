"""Tests for Faculty Authentication, Settings Security, and Fail-Safe Isolation."""

import pytest
from app.config import settings
from app.services.pipeline import process_formulation
from app.models.api_models import FacultySettingsModel


class TestFacultySecurity:
    def test_unauthorized_user_cannot_read_settings(self, client):
        res = client.get("/api/faculty/settings")
        assert res.status_code == 401

    def test_unauthorized_user_cannot_update_settings(self, client):
        res = client.patch(
            "/api/faculty/settings",
            json={"faculty_test_mode": True},
        )
        assert res.status_code == 401

    def test_unauthorized_user_cannot_enable_exam_safe_mode(self, client):
        res = client.post("/api/faculty/exam-safe-mode")
        assert res.status_code == 401

    def test_invalid_token_rejected(self, client):
        res = client.get(
            "/api/faculty/settings",
            headers={"X-Faculty-Token": "wrong_token_123"},
        )
        assert res.status_code == 401

    def test_authorized_faculty_can_read_and_update_settings(self, client):
        token = settings.FACULTY_SECRET_TOKEN
        headers = {"X-Faculty-Token": token}

        # 1. Read settings
        res = client.get("/api/faculty/settings", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "faculty_test_mode" in data

        # 2. Update settings
        res = client.patch(
            "/api/faculty/settings",
            headers=headers,
            json={"show_pulp_code": True},
        )
        assert res.status_code == 200
        assert res.json()["show_pulp_code"] is True

        # 3. Reset to Exam Safe Mode
        res = client.post("/api/faculty/exam-safe-mode", headers=headers)
        assert res.status_code == 200
        safe_data = res.json()
        assert safe_data["faculty_test_mode"] is False
        assert safe_data["show_pulp_code"] is False
        assert safe_data["show_validation_diagnostics"] is False
        assert safe_data["show_debug_parsed_model"] is False

    def test_disabled_pulp_code_not_in_student_response(self, mock_gemini):
        """When show_pulp_code is False, student solve response must NOT contain PuLP code."""
        formulation = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0"""
        safe_settings = FacultySettingsModel(show_pulp_code=False)
        response = process_formulation(
            raw_submission=formulation,
            faculty_settings=safe_settings,
            is_authorized_faculty=False,
            gemini_service=mock_gemini,
        )
        assert response.status == "approved"
        assert response.pulp_code is None
        assert response.diagnostics is None
        assert response.debug_parsed_model is None

    def test_enabled_pulp_code_present_when_setting_is_on(self, mock_gemini):
        """When show_pulp_code is True, solver response includes generated PuLP code."""
        formulation = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0"""
        pulp_settings = FacultySettingsModel(show_pulp_code=True)
        response = process_formulation(
            raw_submission=formulation,
            faculty_settings=pulp_settings,
            is_authorized_faculty=False,
            gemini_service=mock_gemini,
        )
        assert response.status == "approved"
        assert response.pulp_code is not None
        assert "pulp.LpProblem" in response.pulp_code
        assert response.diagnostics is None  # Student still cannot see diagnostics!

    def test_diagnostics_withheld_from_unauthorized_student(self, mock_gemini):
        """Even if diagnostics is ON, an unauthorized student must not receive diagnostics."""
        formulation = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0"""
        diag_settings = FacultySettingsModel(show_validation_diagnostics=True)
        # Student request (is_authorized_faculty=False)
        response = process_formulation(
            raw_submission=formulation,
            faculty_settings=diag_settings,
            is_authorized_faculty=False,
            gemini_service=mock_gemini,
        )
        assert response.diagnostics is None

        # Faculty request (is_authorized_faculty=True)
        faculty_resp = process_formulation(
            raw_submission=formulation,
            faculty_settings=diag_settings,
            is_authorized_faculty=True,
            gemini_service=mock_gemini,
        )
        assert faculty_resp.diagnostics is not None
        assert faculty_resp.diagnostics.final_validation_decision == "APPROVED"
