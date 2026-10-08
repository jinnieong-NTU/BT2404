"""Tests for authoritative PuLP/CBC numerical solver."""

import pytest
from app.services.normalizer import normalize_input
from app.services.deterministic_gates import evaluate_gates_deterministically
from app.services.model_validator import build_and_validate_structured_model
from app.services.pulp_builder import build_pulp_model
from app.services.pulp_solver import run_pulp_cbc_solver
from app.models.structured_model import ProblemType


def solve_from_text(text: str):
    norm = normalize_input(text)
    det = evaluate_gates_deterministically(norm)
    assert det.passed is True
    is_valid, model, err = build_and_validate_structured_model(det, norm.descriptions)
    assert is_valid is True
    prob, v_map = build_pulp_model(model)
    return run_pulp_cbc_solver(model, prob, v_map, identified_model_type=det.identified_model_type)


class TestPuLPSolver:
    def test_solve_linear_programming_lp(self):
        text = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        assert summary.type == "LP"
        assert abs(obj - 22.0) < 1e-4

        var_dict = {v.variable: v.value for v in vars_}
        assert abs(var_dict["x"] - (10.0 / 3.0)) < 1e-4
        assert abs(var_dict["y"] - (4.0 / 3.0)) < 1e-4
        assert "The optimal solution is" in interp
        assert "Linear Programming (LP)" in interp

    def test_solve_integer_programming_ip(self):
        text = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x, y >= 0
x, y are integers"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        assert summary.type == "IP"
        assert obj == 20.0  # x=4, y=0 gives 5*4 + 0 = 20

        var_dict = {v.variable: v.value for v in vars_}
        assert var_dict["x"] == 4.0
        assert var_dict["y"] == 0.0
        assert "Integer Linear Programming (ILP)" in interp

    def test_solve_mixed_integer_programming_mip(self):
        text = """Max 5*x + 4*y
s.t.
x + 2*y <= 6
2*x + y <= 8
x >= 0
y in {0, 1}"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        assert summary.type == "MIP"
        assert obj is not None
        assert status == "Optimal"
        assert "Mixed-Integer Linear Programming (MILP)" in interp

    def test_solve_infeasible_model(self):
        text = """Max x + y
s.t.
x + y <= 2
x + y >= 5
x, y >= 0"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Infeasible"
        assert obj is None
        assert "no feasible solution" in interp

    def test_solve_unbounded_model(self):
        text = """Max x + y
s.t.
x - y <= 2
x, y >= 0"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Unbounded"
        assert obj is None
        assert "unbounded" in interp.lower()

    def test_solve_default_description_dash(self):
        text = """Max 25*x_1 + 30*x_2
s.t.
2*x_1 + 3*x_2 <= 240
x_1, x_2 >= 0"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        for v in vars_:
            assert v.description == "-"

    def test_solve_custom_description_preserved(self):
        text = """Let x_1 = Premium Widgets
x_2: Standard Gadgets
Max 25*x_1 + 30*x_2
s.t.
2*x_1 + 3*x_2 <= 240
x_1, x_2 >= 0"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        var_map = {v.variable: v.description for v in vars_}
        assert var_map["x_1"] == "Premium Widgets"
        assert var_map["x_2"] == "Standard Gadgets"

    def test_solve_refinery_blending_lp3(self):
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
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        assert summary.type == "LP"
        assert summary.identified_model_type == "Linear Programming (LP) - Blending Model"
        assert abs(obj - (-3333.33333)) < 1e-2
        var_map = {v.variable: v.value for v in vars_}
        assert abs(var_map["x_1R"] - 3000.0) < 1e-4
        assert abs(var_map["x_1P"] - 0.0) < 1e-4
        assert abs(var_map["x_2R"] - 333.33333) < 1e-2
        assert abs(var_map["x_2P"] - 1666.66667) < 1e-2
        assert abs(var_map["x_3R"] - 666.66667) < 1e-2
        assert abs(var_map["x_3P"] - 333.33333) < 1e-2
        assert "Linear Programming (LP) - Blending Model" in interp
        assert "-3333.33" in interp

    def test_solve_binary_shorthand(self):
        text = """min 100*y_1 + 150*y_2 + 200*y_3
s.t.
y_1 + y_2 + y_3 >= 1
y_i in {0, 1} for all i"""
        status, obj, vars_, interp, summary = solve_from_text(text)
        assert status == "Optimal"
        assert summary.type in ("IP", "ILP")
        assert summary.identified_model_type == "Integer Linear Programming (ILP)"
        assert abs(obj - 100.0) < 1e-4
        var_map = {v.variable: v.value for v in vars_}
        assert var_map["y_1"] == 1.0
        assert var_map["y_2"] == 0.0
        assert var_map["y_3"] == 0.0
