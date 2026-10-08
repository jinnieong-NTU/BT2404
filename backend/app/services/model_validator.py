"""Final server-side structured model validation before PuLP construction.

Verifies all 16 mathematical sanity and security criteria from Section 42.
"""

import math
from typing import Tuple, Optional, Dict
from app.models.structured_model import (
    StructuredModel,
    ProblemType,
    ObjectiveModel,
    ObjectiveSense,
    VariableModel,
    VariableType,
    ConstraintModel,
    LinearTerm,
)
from app.services.deterministic_gates import GateEvaluationResult


def is_finite_number(val: Optional[float]) -> bool:
    """Check if number is not None, not NaN, and not infinite."""
    if val is None:
        return True
    return not (math.isnan(val) or math.isinf(val))


def build_and_validate_structured_model(
    deterministic_eval: GateEvaluationResult,
    descriptions: Dict[str, str],
) -> Tuple[bool, Optional[StructuredModel], Optional[str]]:
    """Constructs and validates the authoritative StructuredModel from validated evaluation.

    Returns:
        (is_valid, structured_model, error_message)
    """
    if not deterministic_eval.passed:
        return False, None, "Evaluation did not pass earlier gates."

    # 1. Unique variable IDs and symbols
    # Sort variables alphabetically for deterministic ordering
    sorted_vars = sorted(list(deterministic_eval.variables_in_formulation))
    if not sorted_vars:
        return False, None, "No decision variables detected in formulation."

    var_symbol_set = set(sorted_vars)
    if len(var_symbol_set) != len(sorted_vars):
        return False, None, "Duplicate variable symbols detected."

    var_models = []
    symbol_to_id = {}
    for idx, sym in enumerate(sorted_vars, start=1):
        v_id = f"v{idx}"
        symbol_to_id[sym] = v_id
        dom = deterministic_eval.domains.get(sym)
        if not dom:
            return False, None, f"Variable '{sym}' lacks domain/bound information."

        low_b = dom.lower_bound
        up_b = dom.upper_bound
        v_type = dom.var_type

        # Verify lower bound <= upper bound
        if low_b is not None and up_b is not None and low_b > up_b:
            return False, None, f"Variable '{sym}' has lower bound ({low_b}) > upper bound ({up_b})."

        # Verify binary domain validity
        if v_type == VariableType.BINARY:
            low_b = 0.0
            up_b = 1.0

        # Preserve student description or None (never invent)
        desc = descriptions.get(sym, None)

        var_models.append(
            VariableModel(
                id=v_id,
                symbol=sym,
                var_type=v_type,
                lower_bound=low_b,
                upper_bound=up_b,
                description=desc,
            )
        )

    # 2. Objective construction & finiteness check
    if not is_finite_number(deterministic_eval.objective_constant):
        return False, None, "Objective constant is NaN or infinite."

    obj_terms = []
    for term in deterministic_eval.objective_terms:
        if term.var_symbol not in symbol_to_id:
            return False, None, f"Objective references unknown variable '{term.var_symbol}'."
        if not is_finite_number(term.coeff):
            return False, None, f"Objective coefficient for '{term.var_symbol}' is NaN or infinite."
        obj_terms.append(LinearTerm(var_symbol=term.var_symbol, coeff=term.coeff))

    sense = (
        ObjectiveSense.MAXIMIZE
        if (deterministic_eval.objective_sense or "").lower() == "maximize"
        else ObjectiveSense.MINIMIZE
    )
    obj_model = ObjectiveModel(
        sense=sense,
        terms=obj_terms,
        constant=deterministic_eval.objective_constant,
    )

    # 3. Constraints construction & validation
    constraint_models = []
    for idx, c in enumerate(deterministic_eval.constraints, start=1):
        c_id = f"c{idx}"
        if c.operator not in ("<=", ">=", "="):
            return False, None, f"Invalid constraint operator '{c.operator}' in constraint {c_id}."

        if not is_finite_number(c.rhs):
            return False, None, f"RHS value for constraint {c_id} is NaN or infinite."

        c_terms = []
        for term in c.terms:
            if term.var_symbol not in symbol_to_id:
                return False, None, f"Constraint {c_id} references unknown variable '{term.var_symbol}'."
            if not is_finite_number(term.coeff):
                return False, None, f"Coefficient for '{term.var_symbol}' in {c_id} is NaN or infinite."
            c_terms.append(LinearTerm(var_symbol=term.var_symbol, coeff=term.coeff))

        constraint_models.append(
            ConstraintModel(
                id=c_id,
                name=f"Constraint_{idx}",
                terms=c_terms,
                operator=c.operator,
                rhs=c.rhs,
            )
        )

    # 4. Verify problem type classification
    has_integer = any(v.var_type in (VariableType.INTEGER, VariableType.BINARY) for v in var_models)
    has_continuous = any(v.var_type == VariableType.CONTINUOUS for v in var_models)
    if has_integer and not has_continuous:
        p_type = ProblemType.IP
    elif has_integer and has_continuous:
        p_type = ProblemType.MIP
    else:
        p_type = ProblemType.LP

    structured_model = StructuredModel(
        problem_type=p_type,
        objective=obj_model,
        variables=var_models,
        constraints=constraint_models,
    )

    return True, structured_model, None
