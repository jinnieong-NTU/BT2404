"""Authoritative end-to-end processing pipeline orchestrator.

Implements the strict multi-gate trust model:
STUDENT SUBMISSION -> UNTRUSTED
GEMINI OUTPUT -> UNTRUSTED UNTIL VALIDATED
VALIDATED STRUCTURED MODEL -> TRUSTED APPLICATION DATA
DETERMINISTIC PuLP MODEL -> SOLVER INPUT
PuLP/CBC OUTPUT -> AUTHORITATIVE NUMERICAL RESULT
"""

from typing import Optional, Dict, Any, Tuple
from app.models.api_models import (
    SolveResponse,
    ValidationDiagnostics,
    FacultySettingsModel,
)
from app.models.structured_model import StructuredModel
from app.services.normalizer import normalize_input, NormalizedInput
from app.services.deterministic_gates import (
    evaluate_gates_deterministically,
    GateEvaluationResult,
    REJECTION_GATE_1_MSG,
    REJECTION_GATE_2_MSG,
    REJECTION_GATE_3_MSG,
)
from app.config import settings
from app.services.gemini_service import (
    GeminiService,
    default_gemini_service,
    GeminiExtractionResult,
    GeminiExtractionVariable,
    GeminiExtractionConstraint,
    GeminiExtractionTerm,
)
from app.services.consistency_checker import check_model_consistency
from app.services.model_validator import build_and_validate_structured_model
from app.services.pulp_builder import build_pulp_model
from app.services.pulp_solver import run_pulp_cbc_solver
from app.services.pulp_codegen import generate_pulp_code


def process_formulation(
    raw_submission: str,
    faculty_settings: FacultySettingsModel,
    is_authorized_faculty: bool = False,
    gemini_service: Optional[GeminiService] = None,
) -> SolveResponse:
    """Executes the authoritative 12-stage processing pipeline."""
    svc = gemini_service or default_gemini_service

    # Track diagnostics
    diag = ValidationDiagnostics(
        gemini_api_status="UNAVAILABLE" if not svc.is_available else "AVAILABLE",
        gemini_status="NOT_INVOKED",
        gemini_gate_failed=None,
        gemini_rejection_code=None,
        gemini_reason_code=None,
        deterministic_gate_3="NOT_EVALUATED",
        gate_3_reason=None,
        model_consistency_check="NOT_EVALUATED",
        structured_model_validation="NOT_EVALUATED",
        final_validation_decision="REJECTED",
        variables_detected=[],
        variable_descriptions_provided=[],
        pulp_solver_invoked="No",
        pulp_cbc_status=None,
        pulp_code_generated="No",
    )

    # 1. Safe Input Normalisation
    norm: NormalizedInput = normalize_input(raw_submission)
    diag.variable_descriptions_provided = [
        f"{v} = {d}" for v, d in norm.descriptions.items()
    ]

    # 2. Deterministic Security Pre-Screen & Gate Evaluation
    det_eval: GateEvaluationResult = evaluate_gates_deterministically(norm)
    diag.variables_detected = sorted(list(det_eval.variables_in_formulation))

    # If deterministic checks fail at Gate 1 or Gate 3, reject immediately
    if not det_eval.passed:
        diag.final_validation_decision = "REJECTED"
        if det_eval.gate_failed == "GATE_3":
            diag.deterministic_gate_3 = "FAILED"
            diag.gate_3_reason = det_eval.reason_code
        elif det_eval.gate_failed == "GATE_1":
            diag.deterministic_gate_3 = "NOT_EVALUATED"

        return _build_response(
            status="rejected",
            message=det_eval.message,
            gate_failed=det_eval.gate_failed,
            rejection_code=det_eval.rejection_code,
            reason_code=det_eval.reason_code,
            identified_model_type=det_eval.identified_model_type,
            diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        )

    diag.deterministic_gate_3 = "PASSED"

    # 3. Server-side Gemini API Check & Extraction (Section 21)
    if not svc.is_available:
        if faculty_settings.faculty_test_mode:
            class LocalDevGeminiAdapter:
                is_available = True
                def extract_structured_model(self, text: str):
                    g_vars = [
                        GeminiExtractionVariable(
                            symbol=v,
                            description=norm.descriptions.get(v),
                            var_type=det_eval.domains[v].var_type.value,
                            lower_bound=det_eval.domains[v].lower_bound,
                            upper_bound=det_eval.domains[v].upper_bound,
                        )
                        for v in det_eval.variables_in_formulation
                    ]
                    g_cons = [
                        GeminiExtractionConstraint(
                            terms=[GeminiExtractionTerm(var_symbol=t.var_symbol, coeff=t.coeff) for t in c.terms],
                            operator=c.operator,
                            rhs=c.rhs,
                        )
                        for c in det_eval.constraints
                    ]
                    res = GeminiExtractionResult(
                        is_valid_formulation=True,
                        problem_type=det_eval.problem_type.value if det_eval.problem_type else "LP",
                        objective_sense=det_eval.objective_sense,
                        objective_terms=[GeminiExtractionTerm(var_symbol=t.var_symbol, coeff=t.coeff) for t in det_eval.objective_terms],
                        objective_constant=det_eval.objective_constant,
                        variables=g_vars,
                        constraints=g_cons,
                    )
                    return True, res, "OK (Dev Mode)"

            svc = LocalDevGeminiAdapter()
            diag.gemini_api_status = "DEV_MOCK_ACTIVE" if not faculty_settings.faculty_test_mode else "FACULTY_TEST_MODE"
        else:
            # FAIL CLOSED
            diag.gemini_api_status = "UNAVAILABLE"
            diag.gemini_status = "SERVICE_UNAVAILABLE"
            return _build_response(
                status="rejected",
                message="⚠️ AI validation service is currently unavailable.",
                gate_failed="GATE_1",
                rejection_code="AI_SERVICE_UNAVAILABLE",
                diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
            )

    gem_success, gem_extract, gem_msg = svc.extract_structured_model(raw_submission)
    if not gem_success or not gem_extract:
        diag.gemini_status = "CALL_FAILED"
        return _build_response(
            status="rejected",
            message=gem_msg or "⚠️ AI validation service is currently unavailable.",
            diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        )

    diag.gemini_status = "EXTRACTION_COMPLETE"

    # Check Gemini validation rejection if reported
    if not gem_extract.is_valid_formulation:
        diag.gemini_gate_failed = gem_extract.gate_failed
        diag.gemini_rejection_code = gem_extract.rejection_code
        diag.gemini_reason_code = gem_extract.reason_code
        diag.final_validation_decision = "REJECTED"
        
        msg = REJECTION_GATE_1_MSG
        if gem_extract.gate_failed == "GATE_2":
            msg = REJECTION_GATE_2_MSG
        elif gem_extract.gate_failed == "GATE_3":
            msg = REJECTION_GATE_3_MSG

        return _build_response(
            status="rejected",
            message=msg,
            gate_failed=gem_extract.gate_failed,
            rejection_code=gem_extract.rejection_code,
            reason_code=gem_extract.reason_code,
            diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        )

    # 4. Deterministic Model Consistency Check (Section 41)
    # Cross-check Gemini's extraction against raw mathematical AST
    is_consistent, mismatch_reason = check_model_consistency(det_eval, gem_extract)
    if not is_consistent:
        diag.model_consistency_check = f"FAILED: {mismatch_reason}"
        diag.final_validation_decision = "REJECTED"
        return _build_response(
            status="rejected",
            message=REJECTION_GATE_2_MSG,
            gate_failed="GATE_2",
            rejection_code="MODEL_CONSISTENCY_FAILED",
            reason_code=mismatch_reason,
            diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        )

    diag.model_consistency_check = "PASSED"

    # 5. Server-Side Structured Model Validation (Section 42 - 16 checks)
    is_valid_model, structured_model, validation_err = build_and_validate_structured_model(
        det_eval, norm.descriptions
    )
    if not is_valid_model or not structured_model:
        diag.structured_model_validation = f"FAILED: {validation_err}"
        diag.final_validation_decision = "REJECTED"
        return _build_response(
            status="rejected",
            message="⚠️ Mathematical model validation failed sanity criteria.",
            gate_failed="GATE_2",
            rejection_code="VALIDATION_FAILED",
            reason_code=validation_err,
            diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        )

    diag.structured_model_validation = "PASSED"
    diag.final_validation_decision = "APPROVED"

    # 6. Deterministic PuLP Model Builder (Section 43)
    pulp_problem, var_map = build_pulp_model(structured_model)

    # 7. Authoritative PuLP CBC Solver (Section 48-49)
    diag.pulp_solver_invoked = "Yes"
    solver_status, obj_val, var_results, interpretation, summary = run_pulp_cbc_solver(
        structured_model, pulp_problem, var_map, identified_model_type=det_eval.identified_model_type
    )
    diag.pulp_cbc_status = solver_status

    # 8. Optional PuLP Code Generation (Section 18 & 54)
    # ONLY generate and attach if show_pulp_code is true
    pulp_code = None
    if faculty_settings.show_pulp_code:
        pulp_code = generate_pulp_code(structured_model)
        diag.pulp_code_generated = "Yes"

    # 9. Debug Parsed Model (Section 20)
    # ONLY attach if authorized faculty AND show_debug_parsed_model is true
    debug_model = None
    if is_authorized_faculty and faculty_settings.show_debug_parsed_model:
        debug_model = structured_model.model_dump()

    # 10. Assemble Secure Response
    model_type_name = (
        det_eval.identified_model_type
        or (summary.identified_model_type if summary else None)
        or "Linear Programming (LP)"
    )
    return SolveResponse(
        status="approved",
        message=None,
        gate_failed=None,
        rejection_code=None,
        reason_code=None,
        identified_model_type=model_type_name,
        summary=summary,
        solver_status=solver_status,
        objective_value=obj_val,
        variables=var_results,
        interpretation=interpretation,
        pulp_code=pulp_code,
        diagnostics=diag if (is_authorized_faculty and faculty_settings.show_validation_diagnostics) else None,
        debug_parsed_model=debug_model,
    )


def _build_response(
    status: str,
    message: Optional[str] = None,
    gate_failed: Optional[str] = None,
    rejection_code: Optional[str] = None,
    reason_code: Optional[str] = None,
    identified_model_type: Optional[str] = None,
    diagnostics: Optional[ValidationDiagnostics] = None,
) -> SolveResponse:
    """Helper to build rejection response."""
    return SolveResponse(
        status=status,
        message=message,
        gate_failed=gate_failed,
        rejection_code=rejection_code,
        reason_code=reason_code,
        identified_model_type=identified_model_type,
        diagnostics=diagnostics,
    )
