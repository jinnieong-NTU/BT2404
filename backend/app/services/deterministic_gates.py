"""Deterministic multi-gate validation engine.

Implements:
- Gate 1: Topic Lock & Security Pre-Screen
- Gate 2: Formulation Completeness & Variable Consistency
- Gate 3: Supported Linear Model & Deterministic Linearity Checks
"""

import ast
import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from app.services.normalizer import NormalizedInput
from app.services.pre_screener import check_gate_1
from app.services.math_parser import (
    clean_math_tokens,
    find_ast_variables,
    check_node_linearity,
    check_raw_string_nonlinearity,
    extract_linear_terms_from_ast,
    ParsedTerm,
    ParsedConstraint,
    ParsedDomain,
)
from app.models.structured_model import ProblemType, VariableType
from app.services.model_classifier import classify_formulation_model


REJECTION_GATE_1_MSG = (
    "⚠️ This tool only accepts optimization problems submitted as mathematical "
    "programme formulations. It does not answer general questions, provide hints, "
    "explain concepts, or perform any other function."
)

REJECTION_GATE_2_MSG = (
    "⚠️ Your submission is missing one or more required components of a complete "
    "mathematical programme formulation.\n\n"
    "Required components:\n\n"
    "Objective Function\n"
    "Max 5*x + 4*y\n\n"
    "Constraints\n"
    "x + 2*y <= 6\n"
    "2*x + y <= 8\n\n"
    "Variable Domains / Bounds\n"
    "x, y >= 0\n\n"
    "Variable descriptions are optional.\n\n"
    "Resubmit with all required mathematical components present."
)

REJECTION_GATE_3_MSG = (
    "⚠️ This tool only solves linear LP, IP, and MIP formulations. "
    "Nonlinear, quadratic, conic, stochastic, or otherwise unsupported "
    "formulations are not accepted."
)


@dataclass
class GateEvaluationResult:
    passed: bool
    gate_failed: Optional[str] = None  # "GATE_1", "GATE_2", "GATE_3"
    rejection_code: Optional[str] = None  # "TOPIC_LOCK", "INCOMPLETE_FORMULATION", "UNSUPPORTED_MODEL"
    reason_code: Optional[str] = None  # "VARIABLE_PRODUCT", "NONLINEAR_POWER", etc.
    message: Optional[str] = None
    
    # Mathematical data extracted deterministically
    objective_sense: Optional[str] = None  # "maximize" or "minimize"
    objective_terms: List[ParsedTerm] = field(default_factory=list)
    objective_constant: float = 0.0
    constraints: List[ParsedConstraint] = field(default_factory=list)
    domains: Dict[str, ParsedDomain] = field(default_factory=dict)
    variables_in_formulation: Set[str] = field(default_factory=set)
    problem_type: Optional[ProblemType] = None
    identified_model_type: Optional[str] = None


def is_objective_header(line: str) -> bool:
    """Check if line starts with an objective keyword."""
    return bool(re.match(r"^\s*(?:max|min|maximize|minimize|maximise|minimise)\b", line, re.IGNORECASE))


def is_subject_to_marker(line: str) -> bool:
    """Check if line is subject to marker (s.t., subject to, etc.)."""
    return bool(re.match(r"^\s*(?:s\.t\.|st\b|subject\s+to|such\s+that)\s*$", line, re.IGNORECASE))


def parse_domain_line(line: str) -> Optional[List[ParsedDomain]]:
    """Attempt to parse line as variable domain/bound declarations."""
    line = line.strip()
    if not line:
        return None

    results: List[ParsedDomain] = []

    # Check for multiple comma-separated statements on the same line if they contain operators
    # e.g. "x >= 0, y >= 0"
    if re.search(r"[<>=]", line):
        # Check if line has multiple inequalities: e.g., "x >= 0, y >= 0"
        parts = [p.strip() for p in line.split(",") if re.search(r"[<>=]", p)]
        if len(parts) > 1:
            all_parsed = []
            for part in parts:
                sub_res = parse_domain_line(part)
                if sub_res:
                    all_parsed.extend(sub_res)
                else:
                    return None
            return all_parsed if all_parsed else None

    # Pattern 0: Quantified domains, e.g.:
    # "x_j >= 0 for all j", "x_i >= 0, for all i", "x_j >= 0 \forall j", "x_j >= 0, j = 1, 2, 3"
    q_match = re.match(
        r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?:>=|=>|≥)\s*([0-9\.\-]+)\s*(?:and|,)?\s*(?:are\s+)?(integer|integers|binary)?\s*(?:,|\b)?\s*(?:for\s+all|\\forall|for|all)\s+([a-zA-Z0-9_,\s=]+)$",
        line,
        re.IGNORECASE,
    )
    if not q_match:
        q_match = re.match(
            r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?:>=|=>|≥)\s*([0-9\.\-]+)\s*(?:and|,)?\s*(?:are\s+)?(integer|integers|binary)?\s*,\s*([a-zA-Z])\s*=\s*([0-9,\s\.]+)",
            line,
            re.IGNORECASE,
        )
    if q_match:
        sym = q_match.group(1).strip()
        val = float(q_match.group(2))
        typ = q_match.group(3)
        quant = q_match.group(4).strip()
        var_type = VariableType.CONTINUOUS
        if typ:
            if "int" in typ.lower():
                var_type = VariableType.INTEGER
            elif "bin" in typ.lower():
                var_type = VariableType.BINARY
        return [ParsedDomain(var_symbol=sym, lower_bound=val, var_type=var_type, is_quantified=True, quantifier_index=quant)]

    # Pattern 1: var_list >= number (e.g. "x, y >= 0", "x, y >= 0, integer", "x >= 0")
    m1 = re.match(
        r"^([a-zA-Z][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z][a-zA-Z0-9_]*)*)\s*(?:>=|=>|≥)\s*([0-9\.\-]+)(?:\s*(?:and|,)?\s*(?:are\s+)?(integer|integers|binary))?$",
        line,
        re.IGNORECASE,
    )
    if m1:
        var_names = [v.strip() for v in m1.group(1).split(",")]
        val = float(m1.group(2))
        type_str = m1.group(3)
        var_type = VariableType.CONTINUOUS
        if type_str:
            if "int" in type_str.lower():
                var_type = VariableType.INTEGER
            elif "bin" in type_str.lower():
                var_type = VariableType.BINARY
        for v in var_names:
            results.append(ParsedDomain(var_symbol=v, lower_bound=val, var_type=var_type))
        return results

    # Pattern 2: lower <= var <= upper (e.g. "0 <= x <= 20")
    m2 = re.match(
        r"^([0-9\.\-]+)\s*(?:<=|=<|≤)\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?:<=|=<|≤)\s*([0-9\.\-]+)$",
        line,
        re.IGNORECASE,
    )
    if m2:
        low = float(m2.group(1))
        var_name = m2.group(2).strip()
        up = float(m2.group(3))
        results.append(ParsedDomain(var_symbol=var_name, lower_bound=low, upper_bound=up))
        return results

    # Pattern 3: var_list is unrestricted / free (e.g. "x is unrestricted", "x, y free")
    m3 = re.match(
        r"^([a-zA-Z][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z][a-zA-Z0-9_]*)*)\s+(?:is|are)?\s*(?:unrestricted|free)$",
        line,
        re.IGNORECASE,
    )
    if m3:
        var_names = [v.strip() for v in m3.group(1).split(",")]
        for v in var_names:
            results.append(ParsedDomain(var_symbol=v, lower_bound=None, is_unrestricted=True))
        return results

    # Pattern 4: var_list in {0, 1} or binary (e.g. "y in {0,1}", "x, y binary")
    m4 = re.match(
        r"^([a-zA-Z][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z][a-zA-Z0-9_]*)*)\s*(?:(?:in|∈)\s*\{\s*0\s*,\s*1\s*\}|(?:is|are)?\s*binary)$",
        line,
        re.IGNORECASE,
    )
    if m4:
        var_names = [v.strip() for v in m4.group(1).split(",")]
        for v in var_names:
            results.append(ParsedDomain(var_symbol=v, lower_bound=0.0, upper_bound=1.0, var_type=VariableType.BINARY))
        return results

    # Pattern 5: var_list in Z+ or integers (e.g. "x, y in Z+", "x, y are integers", "x, y are non-negative integers")
    m5 = re.match(
        r"^([a-zA-Z][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z][a-zA-Z0-9_]*)*)\s*(?:(?:in|∈)\s*Z\+|(?:is|are)?\s*(?:non-negative\s+)?integers?)$",
        line,
        re.IGNORECASE,
    )
    if m5:
        var_names = [v.strip() for v in m5.group(1).split(",")]
        is_non_neg = bool(re.search(r"non-negative|Z\+", line, re.IGNORECASE))
        for v in var_names:
            results.append(ParsedDomain(var_symbol=v, lower_bound=0.0 if is_non_neg else None, var_type=VariableType.INTEGER))
        return results

    return None


def evaluate_gates_deterministically(norm: NormalizedInput) -> GateEvaluationResult:
    """Run deterministic multi-gate validation pipeline."""
    # ----------------------------------------------------
    # GATE 1 — TOPIC LOCK & PRE-SCREEN
    # ----------------------------------------------------
    passed_g1, gate_f, rej_code, msg = check_gate_1(norm.raw_text)
    if not passed_g1:
        return GateEvaluationResult(
            passed=False,
            gate_failed=gate_f,
            rejection_code=rej_code,
            message=msg or REJECTION_GATE_1_MSG,
        )

    # ----------------------------------------------------
    # LINE CLASSIFICATION (OBJECTIVE, CONSTRAINTS, DOMAINS)
    # ----------------------------------------------------
    lines = [ln.strip() for ln in norm.math_text.splitlines() if ln.strip()]

    # Clean raw check for non-linearity (roots, functions, powers) across the entire text
    raw_nonlin = check_raw_string_nonlinearity(norm.math_text)
    if raw_nonlin:
        obj_line_cand = ""
        for ln in lines:
            if is_objective_header(ln):
                obj_line_cand = ln
                break
        obj_expr_cand = re.sub(
            r"^\s*(max|min|maximize|minimize|maximise|minimise)\b\s*", "", obj_line_cand, flags=re.IGNORECASE
        ).strip() if obj_line_cand else norm.math_text
        constraint_lines_cand = [
            ln for ln in lines if re.search(r"(<=|>=|=|<|>|≤|≥)", ln) and not is_objective_header(ln)
        ]
        m_type, _, _ = classify_formulation_model(
            obj_expr=obj_expr_cand,
            constraint_exprs=constraint_lines_cand,
            raw_lines=lines,
        )
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_3",
            rejection_code="UNSUPPORTED_MODEL",
            reason_code=raw_nonlin,
            identified_model_type=m_type,
            message=f"⚠️ Identified Optimization Model: {m_type}\n\nThis system solves Linear Programming (LP) and Mixed-Integer Linear Programming (ILP/MILP) formulations using CBC. {m_type} models are not supported for execution.",
        )

    obj_line: Optional[str] = None
    constraint_lines: List[str] = []
    domain_items: Dict[str, ParsedDomain] = {}

    in_objective = False
    for line in lines:
        if is_subject_to_marker(line):
            in_objective = False
            continue

        if is_objective_header(line):
            obj_line = line
            in_objective = True
            continue

        # Strip subject-to prefix if attached to constraint
        line_clean = re.sub(r"^\s*(?:s\.t\.|st\b|subject\s+to:?|such\s+that:?)\s*", "", line, flags=re.IGNORECASE).strip()
        if not line_clean:
            in_objective = False
            continue

        # Check if line is a domain declaration
        doms = parse_domain_line(line_clean)
        if doms:
            in_objective = False
            for d in doms:
                # If already exists, update properties (e.g. add integrality or tighter bound)
                if d.var_symbol in domain_items:
                    existing = domain_items[d.var_symbol]
                    if d.var_type != VariableType.CONTINUOUS:
                        existing.var_type = d.var_type
                    if d.lower_bound is not None:
                        existing.lower_bound = d.lower_bound
                    if d.upper_bound is not None:
                        existing.upper_bound = d.upper_bound
                else:
                    domain_items[d.var_symbol] = d
            continue

        # Check if line contains a constraint comparison operator
        if re.search(r"(<=|>=|=|<|>|≤|≥)", line_clean):
            in_objective = False
            constraint_lines.append(line_clean)
            continue

        # If in_objective is True and line has no comparison operators and is not a domain,
        # it is a continuation of the objective function!
        if in_objective and obj_line:
            hdr_match = re.match(r"^(max|min|maximize|minimize|maximise|minimise)\b\s*$", obj_line, re.IGNORECASE)
            if hdr_match:
                obj_line = f"{obj_line} {line}"
            elif line.startswith(("+", "-")) or obj_line.rstrip().endswith(("+", "-")):
                obj_line = f"{obj_line} {line}"
            else:
                obj_line = f"{obj_line} + {line}"
            continue

        # If a line has no operator, no objective, not a subject to, check if it's unparsed domain
        doms_fallback = parse_domain_line(line)
        if doms_fallback:
            in_objective = False
            for d in doms_fallback:
                domain_items[d.var_symbol] = d
        else:
            # Unrecognized line
            pass

    # ----------------------------------------------------
    # GATE 2 — REQUIRED 1: OBJECTIVE FUNCTION
    # ----------------------------------------------------
    if not obj_line:
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_2",
            rejection_code="INCOMPLETE_FORMULATION",
            message=REJECTION_GATE_2_MSG,
        )

    # Parse objective sense and expression
    obj_match = re.match(r"^\s*(max|min|maximize|minimize|maximise|minimise)\b\s*(.*)$", obj_line, re.IGNORECASE)
    if not obj_match or not obj_match.group(2).strip():
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_2",
            rejection_code="INCOMPLETE_FORMULATION",
            message=REJECTION_GATE_2_MSG,
        )

    sense_str = obj_match.group(1).lower()
    obj_sense = "maximize" if sense_str.startswith("max") else "minimize"
    obj_expr = obj_match.group(2).strip()

    # ----------------------------------------------------
    # GATE 2 — REQUIRED 2: CONSTRAINTS
    # ----------------------------------------------------
    if not constraint_lines:
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_2",
            rejection_code="INCOMPLETE_FORMULATION",
            message=REJECTION_GATE_2_MSG,
        )

    # ----------------------------------------------------
    # PARSE OBJECTIVE LINEARITY & VARIABLES (GATE 3 & G2)
    # ----------------------------------------------------
    clean_obj = clean_math_tokens(obj_expr)
    try:
        obj_ast = ast.parse(clean_obj, mode="eval")
    except Exception:
        # Check if raw non-linearity caused syntax error
        raw_err = check_raw_string_nonlinearity(obj_expr)
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_3" if raw_err else "GATE_2",
            rejection_code="UNSUPPORTED_MODEL" if raw_err else "INCOMPLETE_FORMULATION",
            reason_code=raw_err or "SYNTAX_ERROR",
            message=REJECTION_GATE_3_MSG if raw_err else REJECTION_GATE_2_MSG,
        )

    is_lin, nonlin_reason = check_node_linearity(obj_ast)
    if not is_lin:
        m_type, _, _ = classify_formulation_model(
            obj_expr=obj_expr,
            constraint_exprs=constraint_lines,
            raw_lines=lines,
        )
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_3",
            rejection_code="UNSUPPORTED_MODEL",
            reason_code=nonlin_reason,
            identified_model_type=m_type,
            message=f"⚠️ Identified Optimization Model: {m_type}\n\nThis system solves Linear Programming (LP) and Mixed-Integer Linear Programming (ILP/MILP) formulations using CBC. {m_type} models are not supported for execution.",
        )

    try:
        obj_coeffs, obj_const = extract_linear_terms_from_ast(obj_ast)
    except Exception:
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_3",
            rejection_code="UNSUPPORTED_MODEL",
            reason_code="OTHER_UNSUPPORTED_NONLINEARITY",
            message=REJECTION_GATE_3_MSG,
        )

    parsed_obj_terms = [ParsedTerm(var_symbol=v, coeff=c) for v, c in obj_coeffs.items()]
    all_decision_vars: Set[str] = set(obj_coeffs.keys())

    # ----------------------------------------------------
    # PARSE CONSTRAINTS LINEARITY & VARIABLES (GATE 3 & G2)
    # ----------------------------------------------------
    parsed_constraints: List[ParsedConstraint] = []
    c_idx = 1

    for c_line in constraint_lines:
        # Match comparison operator
        op_match = re.search(r"(<=|>=|=)", c_line)
        if not op_match:
            return GateEvaluationResult(
                passed=False,
                gate_failed="GATE_2",
                rejection_code="INCOMPLETE_FORMULATION",
                message=REJECTION_GATE_2_MSG,
            )

        op = op_match.group(1)
        lhs_str = c_line[:op_match.start()].strip()
        rhs_str = c_line[op_match.end():].strip()

        # Parse LHS and RHS with AST
        clean_lhs = clean_math_tokens(lhs_str)
        clean_rhs = clean_math_tokens(rhs_str)

        try:
            lhs_ast = ast.parse(clean_lhs, mode="eval")
            rhs_ast = ast.parse(clean_rhs, mode="eval")
        except Exception:
            raw_err = check_raw_string_nonlinearity(c_line)
            return GateEvaluationResult(
                passed=False,
                gate_failed="GATE_3" if raw_err else "GATE_2",
                rejection_code="UNSUPPORTED_MODEL" if raw_err else "INCOMPLETE_FORMULATION",
                reason_code=raw_err or "SYNTAX_ERROR",
                message=REJECTION_GATE_3_MSG if raw_err else REJECTION_GATE_2_MSG,
            )

        # Linearity check on both LHS and RHS
        is_lhs_lin, lhs_reason = check_node_linearity(lhs_ast)
        if not is_lhs_lin:
            m_type, _, _ = classify_formulation_model(
                obj_expr=obj_expr,
                constraint_exprs=constraint_lines,
                raw_lines=lines,
            )
            return GateEvaluationResult(
                passed=False,
                gate_failed="GATE_3",
                rejection_code="UNSUPPORTED_MODEL",
                reason_code=lhs_reason,
                identified_model_type=m_type,
                message=f"⚠️ Identified Optimization Model: {m_type}\n\nThis system solves Linear Programming (LP) and Mixed-Integer Linear Programming (ILP/MILP) formulations using CBC. {m_type} models are not supported for execution.",
            )

        is_rhs_lin, rhs_reason = check_node_linearity(rhs_ast)
        if not is_rhs_lin:
            m_type, _, _ = classify_formulation_model(
                obj_expr=obj_expr,
                constraint_exprs=constraint_lines,
                raw_lines=lines,
            )
            return GateEvaluationResult(
                passed=False,
                gate_failed="GATE_3",
                rejection_code="UNSUPPORTED_MODEL",
                reason_code=rhs_reason,
                identified_model_type=m_type,
                message=f"⚠️ Identified Optimization Model: {m_type}\n\nThis system solves Linear Programming (LP) and Mixed-Integer Linear Programming (ILP/MILP) formulations using CBC. {m_type} models are not supported for execution.",
            )

        # Extract terms: LHS - RHS <= 0
        lhs_terms, lhs_const = extract_linear_terms_from_ast(lhs_ast)
        rhs_terms, rhs_const = extract_linear_terms_from_ast(rhs_ast)

        # Combine terms into net_terms * vars <= rhs_val
        combined_coeffs: Dict[str, float] = dict(lhs_terms)
        for v, c in rhs_terms.items():
            combined_coeffs[v] = combined_coeffs.get(v, 0.0) - c

        # Filter near-zero coefficients
        final_terms = [
            ParsedTerm(var_symbol=v, coeff=coeff)
            for v, coeff in combined_coeffs.items()
            if abs(coeff) > 1e-9
        ]
        net_rhs = rhs_const - lhs_const

        vars_in_constraint = set(combined_coeffs.keys())
        all_decision_vars.update(vars_in_constraint)

        parsed_constraints.append(
            ParsedConstraint(
                raw_str=c_line,
                terms=final_terms,
                operator=op,
                rhs=net_rhs,
                vars_present=vars_in_constraint,
            )
        )
        c_idx += 1

    # ----------------------------------------------------
    # GATE 2 — REQUIRED 3: VARIABLE CONSISTENCY & DOMAINS
    # (Section 27 & 29: Every decision variable appearing in
    # objective or constraints MUST have explicit domain/bound info)
    # ----------------------------------------------------
    # Instantiate any quantified domain specifications (e.g. x_j >= 0 for all j)
    quantified = [d for d in domain_items.values() if d.is_quantified]
    for q in quantified:
        prefix = re.sub(r"[ij_]+$", "", q.var_symbol).lower()
        for v in all_decision_vars:
            if v.lower().startswith(prefix) or not prefix or q.var_symbol.lower() in ("all", "vars"):
                if v not in domain_items or domain_items[v].is_quantified:
                    domain_items[v] = ParsedDomain(
                        var_symbol=v,
                        lower_bound=q.lower_bound,
                        upper_bound=q.upper_bound,
                        var_type=q.var_type,
                        is_unrestricted=q.is_unrestricted,
                    )

    # Also expand any non-quantified domain symbol not in all_decision_vars acting as a generalized placeholder (e.g. x_ij >= 0)
    for sym, d in list(domain_items.items()):
        if sym not in all_decision_vars:
            base_prefix = re.sub(r"[_ijkltmnab\d]+$", "", sym).lower()
            matching_vars = [v for v in all_decision_vars if not base_prefix or v.lower().startswith(base_prefix)]
            if matching_vars:
                for v in matching_vars:
                    if v not in domain_items or domain_items[v].is_quantified:
                        domain_items[v] = ParsedDomain(
                            var_symbol=v,
                            lower_bound=d.lower_bound,
                            upper_bound=d.upper_bound,
                            var_type=d.var_type,
                            is_unrestricted=d.is_unrestricted,
                        )
                del domain_items[sym]

    # Clean dummy quantified symbols that are not actual variables
    for q in quantified:
        if q.var_symbol not in all_decision_vars and q.var_symbol in domain_items:
            del domain_items[q.var_symbol]

    declared_vars = set(domain_items.keys())
    missing_domains = all_decision_vars - declared_vars

    if missing_domains:
        # Variable consistency failed!
        return GateEvaluationResult(
            passed=False,
            gate_failed="GATE_2",
            rejection_code="INCOMPLETE_FORMULATION",
            reason_code="MISSING_VARIABLE_DOMAIN",
            message=REJECTION_GATE_2_MSG,
            variables_in_formulation=all_decision_vars,
        )

    # Classify Problem Type and paradigm deterministically
    v_types = {v: d.var_type for v, d in domain_items.items()}
    c_exprs = [c.raw_str for c in parsed_constraints]
    m_type, _, _ = classify_formulation_model(
        obj_expr=obj_expr,
        constraint_exprs=c_exprs,
        variable_types=v_types,
        raw_lines=lines,
    )

    has_integer = any(d.var_type in (VariableType.INTEGER, VariableType.BINARY) for d in domain_items.values())
    has_continuous = any(d.var_type == VariableType.CONTINUOUS for d in domain_items.values())
    if has_integer and not has_continuous:
        p_type = ProblemType.IP
    elif has_integer and has_continuous:
        p_type = ProblemType.MIP
    else:
        p_type = ProblemType.LP

    return GateEvaluationResult(
        passed=True,
        objective_sense=obj_sense,
        objective_terms=parsed_obj_terms,
        objective_constant=obj_const,
        constraints=parsed_constraints,
        domains=domain_items,
        variables_in_formulation=all_decision_vars,
        problem_type=p_type,
        identified_model_type=m_type,
    )
