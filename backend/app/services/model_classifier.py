"""Optimization Model Identification & Classification Engine.

Implements structural analysis of mathematical formulas to identify:
- Linear Programming (LP)
- Integer / Mixed-Integer Linear Programming (ILP / MILP)
- Quadratic Programming (QP)
- Non-Linear Programming (NLP)
"""

import ast
import re
from typing import Dict, List, Optional, Tuple, Set
from app.models.structured_model import VariableType
from app.services.math_parser import (
    clean_math_tokens,
    find_ast_variables,
    evaluate_constant_ast,
    NONLINEAR_FUNCS,
)


def get_expression_degree(node: ast.AST) -> Tuple[int, Optional[str]]:
    """Determine polynomial degree of an AST mathematical expression.
    
    Returns:
        (degree, reason)
        degree == 0: Constant
        degree == 1: Strictly Linear
        degree == 2: Strictly Quadratic
        degree > 2: Higher-degree polynomial (NLP)
        degree == -1: Non-polynomial nonlinear term (sin, exp, log, div by var, etc.)
    """
    if isinstance(node, ast.Expression):
        return get_expression_degree(node.body)

    if isinstance(node, ast.Constant):
        return 0, None

    if isinstance(node, ast.Name):
        if node.id.lower() in NONLINEAR_FUNCS:
            return -1, "NONLINEAR_FUNCTION"
        return 1, None

    if isinstance(node, ast.UnaryOp):
        return get_expression_degree(node.operand)

    if isinstance(node, ast.BinOp):
        deg_l, err_l = get_expression_degree(node.left)
        if deg_l == -1:
            return -1, err_l
        deg_r, err_r = get_expression_degree(node.right)
        if deg_r == -1:
            return -1, err_r

        if isinstance(node.op, (ast.Add, ast.Sub)):
            return max(deg_l, deg_r), None

        elif isinstance(node.op, ast.Mult):
            return deg_l + deg_r, None

        elif isinstance(node.op, ast.Div):
            if deg_r > 0:
                return -1, "VARIABLE_IN_DENOMINATOR"
            return deg_l, None

        elif isinstance(node.op, ast.Pow):
            if deg_r > 0:
                return -1, "VARIABLE_EXPONENT"
            try:
                p_val = evaluate_constant_ast(node.right)
                if p_val == int(p_val) and p_val >= 0:
                    return deg_l * int(p_val), None
                else:
                    return -1, "FRACTIONAL_OR_NEGATIVE_POWER"
            except Exception:
                return -1, "NONLINEAR_POWER"

        else:
            return -1, "OTHER_UNSUPPORTED_OPERATOR"

    if isinstance(node, ast.Call):
        return -1, "NONLINEAR_FUNCTION"

    return -1, "UNSUPPORTED_EXPRESSION"


def sanitize_expr_for_degree(expr_str: str) -> str:
    """Prepares string with unicode power and caret replacements for degree checking."""
    s = expr_str.strip()
    s = s.replace("²", "**2").replace("³", "**3").replace("⁴", "**4")
    s = clean_math_tokens(s)
    # Convert implicit multiplication e.g. 5x -> 5*x
    # Use negative lookbehind so digits within variable identifiers (e.g. x_1R, x_2P) are preserved
    s = re.sub(r"(?<![a-zA-Z_0-9.])(\d+(?:\.\d+)?)\s*([a-zA-Z][a-zA-Z0-9_]*)", r"\1*\2", s)
    return s


def check_raw_nonlinearity(expr_str: str) -> Optional[str]:
    """Detects nonlinear operations that cannot be parsed by standard linear AST."""
    if "√" in expr_str:
        return "NONLINEAR_FUNCTION"
    if re.search(r"\|[^|]+\|", expr_str):
        return "NONLINEAR_FUNCTION"
    for fn in NONLINEAR_FUNCS:
        if re.search(rf"\b{fn}\s*\(", expr_str, re.IGNORECASE):
            return "NONLINEAR_FUNCTION"
    return None


def is_blending_model(vars_set: Set[str], constraint_exprs: List[str]) -> bool:
    """Check if formulation matches Refinery / Quality Blending Model characteristics.

    1. Split product/raw suffixes on decision variables (e.g., R for Raw, P for Product: x_1R, x_1P).
    2. Quality / blending constraints (mixed positive and negative coefficients comparing to 0).
    """
    r_vars = [v for v in vars_set if re.search(r"(?:[0-9_]R$|_r$|_raw\b)", v, re.IGNORECASE)]
    p_vars = [v for v in vars_set if re.search(r"(?:[0-9_]P$|_p$|_prod\b|_product\b)", v, re.IGNORECASE)]
    has_split_suffixes = bool(r_vars and p_vars)

    has_quality_constraint = False
    for c in constraint_exprs:
        c_clean = c.strip()
        m = re.search(r"(<=|>=|=)\s*0(?:\.0*)?$", c_clean)
        if m:
            lhs = c_clean[:m.start()].strip()
            has_minus = bool(re.search(r"-\s*[0-9a-zA-Z_]", lhs))
            has_plus = bool(re.search(r"\+\s*[0-9a-zA-Z_]", lhs))
            if has_minus and has_plus:
                has_quality_constraint = True
                break

    return has_split_suffixes and has_quality_constraint


def classify_formulation_model(
    obj_expr: str,
    constraint_exprs: List[str],
    variable_types: Optional[Dict[str, VariableType]] = None,
    raw_lines: Optional[List[str]] = None,
) -> Tuple[str, bool, Optional[str]]:
    """Classifies mathematical programming paradigm.
    
    Returns:
        (identified_model_type, is_supported_for_cbc, explanation)
    """
    if isinstance(variable_types, (list, tuple)) and any(isinstance(x, str) for x in variable_types):
        if raw_lines is None:
            raw_lines = list(variable_types)
        variable_types = {}
    elif variable_types is None:
        variable_types = {}
    
    # 1. Analyze Objective
    obj_clean = sanitize_expr_for_degree(obj_expr)
    raw_obj_err = check_raw_nonlinearity(obj_clean)
    if raw_obj_err:
        return "Non-Linear Programming (NLP)", False, f"Objective contains nonlinear operation: {raw_obj_err}"

    try:
        obj_ast = ast.parse(obj_clean, mode="eval")
        obj_deg, obj_err = get_expression_degree(obj_ast)
    except Exception:
        if re.search(r"\^|\*\*|²|³", obj_expr):
            return "Non-Linear Programming (NLP)", False, "Objective contains nonlinear powers"
        obj_deg = 1
        obj_err = None

    if obj_deg == -1 or obj_deg > 2:
        return "Non-Linear Programming (NLP)", False, f"Objective contains non-linear terms"

    # 2. Analyze Constraints
    constraints_are_linear = True
    for c_str in constraint_exprs:
        raw_c_err = check_raw_nonlinearity(c_str)
        if raw_c_err:
            return "Non-Linear Programming (NLP)", False, f"Constraint contains nonlinear operation: {raw_c_err}"

        # Split operator
        op_match = re.search(r"<=|>=|<|>|=", c_str)
        if not op_match:
            continue
        op = op_match.group(0)
        lhs_raw, rhs_raw = c_str.split(op, 1)
        lhs_clean = sanitize_expr_for_degree(lhs_raw)
        rhs_clean = sanitize_expr_for_degree(rhs_raw)

        try:
            lhs_ast = ast.parse(lhs_clean, mode="eval")
            rhs_ast = ast.parse(rhs_clean, mode="eval")
            deg_l, err_l = get_expression_degree(lhs_ast)
            deg_r, err_r = get_expression_degree(rhs_ast)

            if deg_l > 1 or deg_r > 1 or deg_l == -1 or deg_r == -1:
                constraints_are_linear = False
                return "Non-Linear Programming (NLP)", False, "One or more constraints contain non-linear terms"
        except Exception:
            if re.search(r"\^|\*\*|²|³", c_str):
                return "Non-Linear Programming (NLP)", False, "Constraint contains nonlinear powers"

    # 3. Check for Quadratic Programming (QP)
    if obj_deg == 2 and constraints_are_linear:
        return "Quadratic Programming (QP)", False, "Quadratic objective with linear constraints"

    # If constraints not linear
    if not constraints_are_linear:
        return "Non-Linear Programming (NLP)", False, "Nonlinear constraints detected"

    # 4. Strictly Linear Objective & Linear Constraints: Check Variable Domains (LP vs ILP/MILP)
    has_integer = False
    has_continuous = False

    # Check variable types safely (dict or list or iterable)
    if isinstance(variable_types, dict):
        v_types_list = list(variable_types.values())
    elif isinstance(variable_types, (list, set, tuple)):
        v_types_list = list(variable_types)
    else:
        v_types_list = []

    for v_type in v_types_list:
        if v_type in (VariableType.INTEGER, VariableType.BINARY):
            has_integer = True
        else:
            has_continuous = True

    # Also inspect raw_lines if variable_types was empty
    if not v_types_list and raw_lines:
        full_text = " ".join(raw_lines).lower()
        has_int_kw = bool(re.search(r"\b(integer|integers|binary|bin|\{0,1\}|int)\b", full_text))
        has_cont_kw = bool(re.search(r"\b(continuous|real|reals)\b", full_text))
        if has_int_kw and has_cont_kw:
            has_integer = True
            has_continuous = True
        elif has_int_kw:
            has_integer = True
            has_continuous = False
        else:
            has_continuous = True

    if has_integer and not has_continuous:
        return "Integer Linear Programming (ILP)", True, "Strictly linear with all integer decision variables"
    elif has_integer and has_continuous:
        return "Mixed-Integer Linear Programming (MILP)", True, "Strictly linear with mixed integer and continuous decision variables"
    else:
        # Check for Blending Model characteristics (Rule 4)
        vars_found: Set[str] = set()
        if isinstance(variable_types, dict):
            vars_found.update(variable_types.keys())
        if raw_lines:
            for l in raw_lines:
                for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", l):
                    if w.lower() not in ("max", "min", "subject", "to", "st", "all", "for", "and", "or"):
                        vars_found.add(w)
        for c in constraint_exprs:
            for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", c):
                if w.lower() not in ("max", "min", "subject", "to", "st", "all", "for", "and", "or"):
                    vars_found.add(w)

        if is_blending_model(vars_found, constraint_exprs):
            return (
                "Linear Programming (LP) - Blending Model",
                True,
                "Refinery blending linear programming model with raw/product split variables and quality blending constraints",
            )
        return "Linear Programming (LP)", True, "Strictly linear objective and constraints with continuous decision variables"
