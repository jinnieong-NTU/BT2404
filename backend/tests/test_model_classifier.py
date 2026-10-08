import pytest
from app.services.model_classifier import classify_formulation_model
from app.services.normalizer import normalize_input
from app.services.deterministic_gates import evaluate_gates_deterministically
from app.services.pipeline import process_formulation
from app.services.gemini_service import GeminiService
from app.models.api_models import FacultySettingsModel


import ast
from app.services.model_classifier import (
    classify_formulation_model,
    get_expression_degree,
    sanitize_expr_for_degree,
)


def test_classify_linear_programming_lp():
    obj = "25*x_1 + 30*x_2 + 15*x_3"
    constraints = [
        "2*x_1 + 3*x_2 + x_3 <= 240",
        "4*x_1 + x_2 + 3*x_3 <= 180",
    ]
    raw_lines = ["x_1, x_2, x_3 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Linear Programming (LP)"
    assert is_lin is True


def test_classify_integer_linear_programming_ilp():
    obj = "25*x_1 + 30*x_2"
    constraints = ["2*x_1 + 3*x_2 <= 240"]
    raw_lines = ["x_1, x_2 >= 0", "x_1, x_2 are integers"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Integer Linear Programming (ILP)"
    assert is_lin is True


def test_classify_mixed_integer_linear_programming_milp():
    obj = "25*x_1 + 30*x_2"
    constraints = ["2*x_1 + 3*x_2 <= 240"]
    raw_lines = ["x_1, x_2 >= 0", "x_1 is integer", "x_2 is continuous"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Mixed-Integer Linear Programming (MILP)"
    assert is_lin is True


def test_classify_quadratic_programming_qp():
    # Quadratic objective, linear constraints
    obj = "x_1^2 + x_2^2 + 5*x_1"
    constraints = ["x_1 + x_2 <= 10"]
    raw_lines = ["x_1, x_2 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Quadratic Programming (QP)"
    assert is_lin is False

    # Check degree directly
    ast_node = ast.parse(sanitize_expr_for_degree(obj), mode="eval")
    deg, _ = get_expression_degree(ast_node)
    assert deg == 2


def test_classify_quadratic_with_variable_product_qp():
    # x_1 * x_2 in objective, linear constraints
    obj = "25*x_1*x_2 + 10*x_1"
    constraints = ["x_1 + x_2 <= 10"]
    raw_lines = ["x_1, x_2 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Quadratic Programming (QP)"
    assert is_lin is False

    ast_node = ast.parse(sanitize_expr_for_degree(obj), mode="eval")
    deg, _ = get_expression_degree(ast_node)
    assert deg == 2


def test_classify_nonlinear_programming_nlp_due_to_power_3():
    # Degree 3 polynomial
    obj = "x_1^3 + 5*x_2"
    constraints = ["x_1 + x_2 <= 10"]
    raw_lines = ["x_1, x_2 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Non-Linear Programming (NLP)"
    assert is_lin is False

    ast_node = ast.parse(sanitize_expr_for_degree(obj), mode="eval")
    deg, _ = get_expression_degree(ast_node)
    assert deg == 3


def test_classify_nonlinear_programming_nlp_due_to_function():
    # sqrt function
    obj = "sqrt(x_1) + 5*x_2"
    constraints = ["x_1 + x_2 <= 10"]
    raw_lines = ["x_1, x_2 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Non-Linear Programming (NLP)"
    assert is_lin is False


def test_classify_nonlinear_programming_nlp_due_to_nonlinear_constraint():
    # Quadratic constraint makes it NLP (not QP, since QP requires linear constraints)
    obj = "5*x_1 + 4*x_2"
    constraints = ["x_1^2 + x_2^2 <= 100"]
    raw_lines = ["x_1, x_2 >= 0"]
    model_type, is_lin, exp = classify_formulation_model(obj, constraints, raw_lines)
    assert model_type == "Non-Linear Programming (NLP)"
    assert is_lin is False


def test_end_to_end_pipeline_outputs_identified_model():
    text = """max 25*x_1 + 30*x_2 + 15*x_3
s.t.
2*x_1 + 3*x_2 + x_3 <= 240
4*x_1 + x_2 + 3*x_3 <= 180
2*x_1 + 5*x_2 + 2*x_3 <= 300
x_1 <= 40
x_2 <= 30
x_3 <= 50
x_j >= 0 for all j"""
    settings = FacultySettingsModel(faculty_test_mode=True)
    svc = GeminiService(api_key="mock")
    res = process_formulation(text, settings, svc)
    assert res.status == "approved"
    assert res.identified_model_type == "Linear Programming (LP)"
    assert res.summary.identified_model_type == "Linear Programming (LP)"


def test_gate_3_rejection_identifies_qp_and_nlp():
    # QP rejected by Gate 3
    text_qp = "max x_1^2 + x_2\ns.t.\nx_1 + x_2 <= 10\nx_1, x_2 >= 0"
    norm_qp = normalize_input(text_qp)
    res_qp = evaluate_gates_deterministically(norm_qp)
    assert res_qp.passed is False
    assert res_qp.gate_failed == "GATE_3"
    assert res_qp.identified_model_type == "Quadratic Programming (QP)"
    assert "Quadratic Programming (QP)" in res_qp.message

    # NLP rejected by Gate 3
    text_nlp = "max sqrt(x_1) + x_2\ns.t.\nx_1 + x_2 <= 10\nx_1, x_2 >= 0"
    norm_nlp = normalize_input(text_nlp)
    res_nlp = evaluate_gates_deterministically(norm_nlp)
    assert res_nlp.passed is False
    assert res_nlp.gate_failed == "GATE_3"
    assert res_nlp.identified_model_type == "Non-Linear Programming (NLP)"
    assert "Non-Linear Programming (NLP)" in res_nlp.message


def test_classify_refinery_blending_model():
    text = """max   5*x_1R - 15*x_2R - 20*x_3R
    - 5*x_1P +  5*x_2P - 25*x_3P  

s.t.  x_1R + x_1P <= 3000                   
      x_2R + x_2P <= 2000                  
      x_3R + x_3P <= 4000                   
      x_1R + x_2R + x_3R >= 4000           
      x_1P + x_2P + x_3P >= 2000           
      -2*x_1R + 5*x_2R + 11*x_3R >= 0    
      -8*x_1P -   x_2P +  5*x_3P >= 0      
      x_ij >= 0   for all i, j"""
    norm = normalize_input(text)
    res = evaluate_gates_deterministically(norm)
    assert res.passed is True
    assert res.identified_model_type == "Linear Programming (LP) - Blending Model"


def test_reconstruct_split_objective_functions():
    text = """min 10*x1 + 20*x2
    + 30*x3 - 5*x4
s.t.
x1 + x2 + x3 + x4 >= 10
x1, x2, x3, x4 >= 0"""
    norm = normalize_input(text)
    res = evaluate_gates_deterministically(norm)
    assert res.passed is True
    assert len(res.objective_terms) == 4
    terms_dict = {t.var_symbol: t.coeff for t in res.objective_terms}
    assert terms_dict["x1"] == 10.0
    assert terms_dict["x2"] == 20.0
    assert terms_dict["x3"] == 30.0
    assert terms_dict["x4"] == -5.0


def test_dereference_math_set_shorthands_binary():
    text = """min 5*y_1 + 8*y_2 + 12*y_3
s.t.
y_1 + y_2 + y_3 >= 1
y_i in {0, 1} for all i"""
    norm = normalize_input(text)
    res = evaluate_gates_deterministically(norm)
    assert res.passed is True
    assert res.problem_type.value in ("IP", "ILP")
    assert res.identified_model_type == "Integer Linear Programming (ILP)"
    for sym in ("y_1", "y_2", "y_3"):
        assert sym in res.domains
        assert res.domains[sym].lower_bound == 0.0
        assert res.domains[sym].upper_bound == 1.0


def test_independent_alphanumeric_and_numeric_subscripts():
    text = """max 2*x_1 + 3*x_1R + 4*x_2P
s.t.
x_1 + x_1R + x_2P <= 100
x_1 >= 0
x_1R >= 0
x_2P >= 0"""
    norm = normalize_input(text)
    res = evaluate_gates_deterministically(norm)
    assert res.passed is True
    assert "x_1" in res.variables_in_formulation
    assert "x_1R" in res.variables_in_formulation
    assert "x_2P" in res.variables_in_formulation
    assert len(res.variables_in_formulation) == 3
