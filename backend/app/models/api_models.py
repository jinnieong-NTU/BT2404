"""API Request and Response Models."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SolveRequest(BaseModel):
    formulation: str = Field(..., description="Raw mathematical programme formulation text")


class FacultySettingsModel(BaseModel):
    faculty_test_mode: bool = False
    show_pulp_code: bool = False
    show_validation_diagnostics: bool = False
    show_debug_parsed_model: bool = False


class FacultySettingsUpdate(BaseModel):
    faculty_test_mode: Optional[bool] = None
    show_pulp_code: Optional[bool] = None
    show_validation_diagnostics: Optional[bool] = None
    show_debug_parsed_model: Optional[bool] = None


class DecisionVariableResult(BaseModel):
    variable: str
    description: Optional[str] = None
    type: str
    value: float


class ProblemSummary(BaseModel):
    type: str
    identified_model_type: Optional[str] = None
    objective: str
    variables: Dict[str, Any]
    constraints: int


class ValidationDiagnostics(BaseModel):
    gemini_api_status: str
    gemini_status: str
    gemini_gate_failed: Optional[str] = None
    gemini_rejection_code: Optional[str] = None
    gemini_reason_code: Optional[str] = None
    deterministic_gate_3: str
    gate_3_reason: Optional[str] = None
    model_consistency_check: str
    structured_model_validation: str
    final_validation_decision: str
    variables_detected: List[str]
    variable_descriptions_provided: List[str]
    pulp_solver_invoked: str
    pulp_cbc_status: Optional[str] = None
    pulp_code_generated: str


class SolveResponse(BaseModel):
    status: str  # "approved" or "rejected"
    message: Optional[str] = None
    gate_failed: Optional[str] = None  # "GATE_1", "GATE_2", "GATE_3", etc.
    rejection_code: Optional[str] = None  # "TOPIC_LOCK", "INCOMPLETE_FORMULATION", "UNSUPPORTED_MODEL"
    reason_code: Optional[str] = None  # "VARIABLE_PRODUCT", etc.
    identified_model_type: Optional[str] = None  # e.g. "Linear Programming (LP)", "Mixed-Integer Linear Programming (MILP)"
    summary: Optional[ProblemSummary] = None
    solver_status: Optional[str] = None  # "Optimal", "Infeasible", "Unbounded", "Solver Error"
    objective_value: Optional[float] = None
    variables: Optional[List[DecisionVariableResult]] = None
    interpretation: Optional[str] = None
    pulp_code: Optional[str] = None  # Only sent when show_pulp_code is True
    diagnostics: Optional[ValidationDiagnostics] = None  # Only sent when authorized & show_validation_diagnostics is True
    debug_parsed_model: Optional[Dict[str, Any]] = None  # Only sent when authorized & show_debug_parsed_model is True
