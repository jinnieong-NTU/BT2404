"""End-to-end API endpoint integration tests."""

import pytest
from app.config import settings
from app.services.pipeline import process_formulation
from app.services.gemini_service import GeminiService


class TestApiEndpoints:
    def test_health_check(self, client):
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_public_config_default(self, client):
        res = client.get("/api/config/public")
        assert res.status_code == 200
        data = res.json()
        assert "faculty_test_mode" in data
        assert data["faculty_test_mode"] is False

    def test_student_page_serves_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "Optimization Solver" in res.text

    def test_faculty_page_serves_html(self, client):
        res = client.get("/faculty")
        assert res.status_code == 200
        assert "Optimization Solver — Faculty Controls" in res.text

        res_html = client.get("/faculty.html")
        assert res_html.status_code == 200
        assert "Optimization Solver — Faculty Controls" in res_html.text

        res_slash = client.get("/faculty/")
        assert res_slash.status_code == 200
        assert "Optimization Solver — Faculty Controls" in res_slash.text

    def test_fail_closed_when_gemini_unavailable(self):
        """Section 21: If GEMINI_API_KEY is unavailable, FAIL CLOSED."""
        formulation = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0"""
        # Create unconfigured service without API key
        empty_svc = GeminiService(api_key="")
        from app.models.api_models import FacultySettingsModel
        res = process_formulation(
            raw_submission=formulation,
            faculty_settings=FacultySettingsModel(),
            gemini_service=empty_svc,
        )
        assert res.status == "rejected"
        assert "⚠️ AI validation service is currently unavailable." in res.message

    def test_api_solve_gate_1_rejected(self, client):
        payload = {"formulation": "What is linear programming?"}
        res = client.post("/api/solve", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rejected"
        assert data["gate_failed"] == "GATE_1"
        assert data["rejection_code"] == "TOPIC_LOCK"

    def test_api_solve_gate_2_rejected(self, client):
        payload = {"formulation": "Max 5*x + 4*y\ns.t.\nx + y <= 10\nx >= 0"}
        res = client.post("/api/solve", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rejected"
        assert data["gate_failed"] == "GATE_2"
        assert data["rejection_code"] == "INCOMPLETE_FORMULATION"

    def test_api_solve_gate_3_rejected(self, client):
        payload = {"formulation": "Max 5*x*y\ns.t.\nx + y <= 10\nx, y >= 0"}
        res = client.post("/api/solve", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rejected"
        assert data["gate_failed"] == "GATE_3"
        assert data["rejection_code"] == "UNSUPPORTED_MODEL"
        assert data["reason_code"] == "VARIABLE_PRODUCT"
