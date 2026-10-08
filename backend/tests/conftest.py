import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.settings_repo import get_settings_repository, BaseSettingsRepository
from app.services.gemini_service import (
    GeminiService,
    GeminiExtractionResult,
    GeminiExtractionTerm,
    GeminiExtractionVariable,
    GeminiExtractionConstraint,
)
from app.services.deterministic_gates import evaluate_gates_deterministically
from app.services.normalizer import normalize_input


class MockGeminiService(GeminiService):
    """Deterministic Mock Gemini Service for offline automated testing.

    Generates valid structured extraction corresponding directly to the input,
    or replicates rejection matching the deterministic gate checks,
    ensuring 100% test reproducibility without external API network latency.
    """

    def __init__(self):
        super().__init__(api_key="mock_test_key")

    @property
    def is_available(self) -> bool:
        return True

    def extract_structured_model(self, formulation_text: str):
        norm = normalize_input(formulation_text)
        det = evaluate_gates_deterministically(norm)

        if not det.passed:
            return True, GeminiExtractionResult(
                is_valid_formulation=False,
                gate_failed=det.gate_failed,
                rejection_code=det.rejection_code,
                reason_code=det.reason_code,
            ), "OK"

        # Build valid structured extraction matching deterministic findings
        obj_terms = [
            GeminiExtractionTerm(var_symbol=t.var_symbol, coeff=t.coeff)
            for t in det.objective_terms
        ]

        variables = []
        for sym, dom in det.domains.items():
            desc = norm.descriptions.get(sym, None)
            variables.append(
                GeminiExtractionVariable(
                    symbol=sym,
                    var_type=dom.var_type.value,
                    lower_bound=dom.lower_bound,
                    upper_bound=dom.upper_bound,
                    description=desc,
                )
            )

        constraints = []
        for i, c in enumerate(det.constraints, start=1):
            c_terms = [
                GeminiExtractionTerm(var_symbol=t.var_symbol, coeff=t.coeff)
                for t in c.terms
            ]
            constraints.append(
                GeminiExtractionConstraint(
                    name=f"c{i}",
                    terms=c_terms,
                    operator=c.operator,
                    rhs=c.rhs,
                )
            )

        return True, GeminiExtractionResult(
            is_valid_formulation=True,
            problem_type=det.problem_type.value if det.problem_type else "LP",
            objective_sense=det.objective_sense,
            objective_terms=obj_terms,
            objective_constant=det.objective_constant,
            variables=variables,
            constraints=constraints,
        ), "OK"


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Use isolated settings file for test run so live settings are never mutated
    test_settings_file = str(tmp_path / "test_faculty_settings.json")
    monkeypatch.setenv("SETTINGS_FILE_PATH", test_settings_file)
    from app.services.settings_repo import LocalFileSettingsRepository
    repo = LocalFileSettingsRepository(file_path=test_settings_file)
    repo.reset_to_exam_safe_mode()
    app.dependency_overrides[get_settings_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.pop(get_settings_repository, None)


@pytest.fixture
def mock_gemini():
    return MockGeminiService()
