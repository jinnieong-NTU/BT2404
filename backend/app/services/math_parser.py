"""Safe deterministic mathematical parser using Python AST.

Parses mathematical formulations without ever using eval(), exec(), or compile().
"""

import ast
import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from app.models.structured_model import VariableType


@dataclass
class ParsedTerm:
    var_symbol: str
    coeff: float


@dataclass
class ParsedConstraint:
    raw_str: str
    terms: List[ParsedTerm]
    operator: str  # "<=", ">=", "="
    rhs: float
    vars_present: Set[str] = field(default_factory=set)


@dataclass
class ParsedDomain:
    var_symbol: str
    lower_bound: Optional[float] = 0.0
    upper_bound: Optional[float] = None
    var_type: VariableType = VariableType.CONTINUOUS
    is_unrestricted: bool = False
    is_quantified: bool = False
    quantifier_index: Optional[str] = None


@dataclass
class MathParseResult:
    is_valid: bool
    objective_sense: Optional[str] = None  # "maximize" or "minimize"
    objective_terms: List[ParsedTerm] = field(default_factory=list)
    objective_constant: float = 0.0
    constraints: List[ParsedConstraint] = field(default_factory=list)
    declared_domains: Dict[str, ParsedDomain] = field(default_factory=dict)
    all_decision_vars: Set[str] = field(default_factory=set)
    unbounded_or_missing_vars: Set[str] = field(default_factory=set)
    linearity_failed: bool = False
    linearity_reason: Optional[str] = None
    error_message: Optional[str] = None


# Known nonlinear functions
NONLINEAR_FUNCS = {
    "sqrt", "sin", "cos", "tan", "log", "ln", "exp", "abs",
    "asin", "acos", "atan", "sinh", "cosh", "tanh"
}


def clean_math_tokens(expr_str: str) -> str:
    """Prepare math expression string for AST parsing."""
    s = expr_str.strip()
    # Replace ^ with ** for AST power recognition
    s = re.sub(r"\^", "**", s)
    return s


def find_ast_variables(node: ast.AST) -> Set[str]:
    """Find all variable identifiers in an AST node, excluding function names."""
    vars_found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            if sub.id.lower() not in NONLINEAR_FUNCS:
                vars_found.add(sub.id)
    return vars_found


def check_node_linearity(node: ast.AST) -> Tuple[bool, Optional[str]]:
    """Recursively check if an AST expression node is strictly linear."""
    if isinstance(node, ast.Expression):
        return check_node_linearity(node.body)

    if isinstance(node, ast.Constant):
        return True, None

    if isinstance(node, ast.Name):
        return True, None

    if isinstance(node, ast.UnaryOp):
        return check_node_linearity(node.operand)

    if isinstance(node, ast.BinOp):
        left_vars = find_ast_variables(node.left)
        right_vars = find_ast_variables(node.right)

        if isinstance(node.op, (ast.Add, ast.Sub)):
            ok_l, err_l = check_node_linearity(node.left)
            if not ok_l:
                return False, err_l
            ok_r, err_r = check_node_linearity(node.right)
            if not ok_r:
                return False, err_r
            return True, None

        elif isinstance(node.op, ast.Mult):
            if left_vars and right_vars:
                return False, "VARIABLE_PRODUCT"
            ok_l, err_l = check_node_linearity(node.left)
            if not ok_l:
                return False, err_l
            ok_r, err_r = check_node_linearity(node.right)
            if not ok_r:
                return False, err_r
            return True, None

        elif isinstance(node.op, ast.Div):
            if right_vars:
                return False, "VARIABLE_IN_DENOMINATOR"
            ok_l, err_l = check_node_linearity(node.left)
            if not ok_l:
                return False, err_l
            return True, None

        elif isinstance(node.op, ast.Pow):
            return False, "NONLINEAR_POWER"

        else:
            return False, "OTHER_UNSUPPORTED_NONLINEARITY"

    if isinstance(node, ast.Call):
        return False, "NONLINEAR_FUNCTION"

    return False, "OTHER_UNSUPPORTED_NONLINEARITY"


def check_raw_string_nonlinearity(raw_str: str) -> Optional[str]:
    """Check for unicode characters or syntax that represent nonlinear operations."""
    # Check powers: x², x³, etc.
    if re.search(r"[²³⁴⁵⁶⁷⁸⁹]", raw_str):
        return "NONLINEAR_POWER"

    # Check square root: √
    if "√" in raw_str:
        return "NONLINEAR_FUNCTION"

    # Check absolute value bars: |x|
    if re.search(r"\|[^|]+\|", raw_str):
        return "NONLINEAR_FUNCTION"

    # Check nonlinear functions like sin, cos, sqrt, log
    for fn in NONLINEAR_FUNCS:
        pattern = rf"\b{fn}\s*\("
        if re.search(pattern, raw_str, re.IGNORECASE):
            return "NONLINEAR_FUNCTION"

    return None


def evaluate_constant_ast(node: ast.AST) -> float:
    """Safely compute constant numeric value from AST node."""
    if isinstance(node, ast.Constant):
        return float(node.value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -evaluate_constant_ast(node.operand)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return evaluate_constant_ast(node.operand)
    elif isinstance(node, ast.BinOp):
        left = evaluate_constant_ast(node.left)
        right = evaluate_constant_ast(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        elif isinstance(node.op, ast.Sub):
            return left - right
        elif isinstance(node.op, ast.Mult):
            return left * right
        elif isinstance(node.op, ast.Div):
            return left / right
    raise ValueError("Not a pure constant AST expression")


def extract_linear_terms_from_ast(node: ast.AST, sign: float = 1.0) -> Tuple[Dict[str, float], float]:
    """Extract variable coefficients and constant from a linear AST node."""
    coeffs: Dict[str, float] = {}
    constant = 0.0

    if isinstance(node, ast.Expression):
        return extract_linear_terms_from_ast(node.body, sign)

    if isinstance(node, ast.Constant):
        return {}, sign * float(node.value)

    if isinstance(node, ast.Name):
        return {node.id: sign * 1.0}, 0.0

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return extract_linear_terms_from_ast(node.operand, -sign)
        elif isinstance(node.op, ast.UAdd):
            return extract_linear_terms_from_ast(node.operand, sign)

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            c1, k1 = extract_linear_terms_from_ast(node.left, sign)
            c2, k2 = extract_linear_terms_from_ast(node.right, sign)
            for v, val in c2.items():
                c1[v] = c1.get(v, 0.0) + val
            return c1, k1 + k2

        elif isinstance(node.op, ast.Sub):
            c1, k1 = extract_linear_terms_from_ast(node.left, sign)
            c2, k2 = extract_linear_terms_from_ast(node.right, -sign)
            for v, val in c2.items():
                c1[v] = c1.get(v, 0.0) + val
            return c1, k1 + k2

        elif isinstance(node.op, ast.Mult):
            left_vars = find_ast_variables(node.left)
            right_vars = find_ast_variables(node.right)
            if not left_vars and not right_vars:
                return {}, sign * (evaluate_constant_ast(node.left) * evaluate_constant_ast(node.right))
            elif not left_vars and right_vars:
                k = evaluate_constant_ast(node.left)
                return extract_linear_terms_from_ast(node.right, sign * k)
            elif left_vars and not right_vars:
                k = evaluate_constant_ast(node.right)
                return extract_linear_terms_from_ast(node.left, sign * k)

        elif isinstance(node.op, ast.Div):
            right_vars = find_ast_variables(node.right)
            if not right_vars:
                denom = evaluate_constant_ast(node.right)
                return extract_linear_terms_from_ast(node.left, sign / denom)

    raise ValueError("Cannot extract linear terms: unsupported or nonlinear expression")
