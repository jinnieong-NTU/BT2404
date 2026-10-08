"""Deterministic cross-validation of Gemini's extracted model against raw mathematical AST.

Ensures Gemini has not silently altered signs, bounds, coefficients, or constraints.
"""

from typing import Tuple, Optional, Dict
from app.services.deterministic_gates import GateEvaluationResult
from app.services.gemini_service import GeminiExtractionResult


def check_model_consistency(
    deterministic_eval: GateEvaluationResult,
    gemini_result: GeminiExtractionResult,
) -> Tuple[bool, Optional[str]]:
    """Cross-check Gemini extraction against deterministic GateEvaluationResult.

    Returns:
        (is_consistent, failure_reason)
    """
    # 1. Objective direction / sense
    det_sense = (deterministic_eval.objective_sense or "").lower()
    gem_sense = (gemini_result.objective_sense or "").lower()
    if det_sense != gem_sense:
        return False, f"Objective sense mismatch: deterministic '{det_sense}' vs Gemini '{gem_sense}'"

    # 2. Objective coefficients
    det_obj_map: Dict[str, float] = {
        t.var_symbol: t.coeff for t in deterministic_eval.objective_terms
    }
    gem_obj_map: Dict[str, float] = {
        t.var_symbol: t.coeff for t in gemini_result.objective_terms
    }

    if set(det_obj_map.keys()) != set(gem_obj_map.keys()):
        return False, f"Objective variables mismatch: deterministic {set(det_obj_map.keys())} vs Gemini {set(gem_obj_map.keys())}"

    for var, coeff in det_obj_map.items():
        gem_coeff = gem_obj_map.get(var, 0.0)
        if abs(coeff - gem_coeff) > 1e-4:
            return False, f"Objective coefficient mismatch for variable '{var}': {coeff} vs {gem_coeff}"

    # 3. Objective constant
    if abs(deterministic_eval.objective_constant - gemini_result.objective_constant) > 1e-4:
        return False, f"Objective constant mismatch: {deterministic_eval.objective_constant} vs {gemini_result.objective_constant}"

    # 4. Variables set
    det_vars = set(deterministic_eval.variables_in_formulation)
    gem_vars = {v.symbol for v in gemini_result.variables}
    if det_vars != gem_vars:
        return False, f"Variables set mismatch: deterministic {det_vars} vs Gemini {gem_vars}"

    # 5. Variable bounds and integrality
    gem_var_dict = {v.symbol: v for v in gemini_result.variables}
    for var, det_dom in deterministic_eval.domains.items():
        g_var = gem_var_dict.get(var)
        if not g_var:
            return False, f"Variable '{var}' missing in Gemini extracted variables"

        # Check lower bound
        if det_dom.lower_bound is not None:
            if g_var.lower_bound is None or abs(det_dom.lower_bound - g_var.lower_bound) > 1e-4:
                return False, f"Lower bound mismatch for variable '{var}': {det_dom.lower_bound} vs {g_var.lower_bound}"

        # Check upper bound
        if det_dom.upper_bound is not None:
            if g_var.upper_bound is None or abs(det_dom.upper_bound - g_var.upper_bound) > 1e-4:
                return False, f"Upper bound mismatch for variable '{var}': {det_dom.upper_bound} vs {g_var.upper_bound}"

        # Check integrality / type
        det_type = det_dom.var_type.value.lower()
        gem_type = g_var.var_type.lower()
        if det_type != gem_type:
            return False, f"Variable type mismatch for '{var}': {det_type} vs {gem_type}"

    # 6. Constraint count
    if len(deterministic_eval.constraints) != len(gemini_result.constraints):
        return False, f"Constraint count mismatch: deterministic {len(deterministic_eval.constraints)} vs Gemini {len(gemini_result.constraints)}"

    # 7. Constraint terms, operators, and RHS
    # Match each deterministic constraint to a Gemini constraint
    det_c_list = deterministic_eval.constraints
    gem_c_list = gemini_result.constraints

    for i, det_c in enumerate(det_c_list):
        matched = False
        det_terms_map = {t.var_symbol: t.coeff for t in det_c.terms}

        for gem_c in gem_c_list:
            if det_c.operator != gem_c.operator:
                continue
            if abs(det_c.rhs - gem_c.rhs) > 1e-4:
                continue
            gem_terms_map = {t.var_symbol: t.coeff for t in gem_c.terms}
            if set(det_terms_map.keys()) != set(gem_terms_map.keys()):
                continue

            all_match = True
            for v, c in det_terms_map.items():
                if abs(c - gem_terms_map.get(v, 0.0)) > 1e-4:
                    all_match = False
                    break

            if all_match:
                matched = True
                break

        if not matched:
            return False, f"Deterministic constraint '{det_c.raw_str}' was not matched identically in Gemini extraction"

    return True, None
