"""Authoritative numerical optimization solver using PuLP with CBC.

Executes CBC on validated PuLP problem, maps status, formats optimal variables,
and produces strict factual interpretations without inventing business context.
"""

from typing import Dict, List, Optional, Tuple, Any
import pulp
from app.models.structured_model import StructuredModel, VariableType
from app.models.api_models import DecisionVariableResult, ProblemSummary


def run_pulp_cbc_solver(
    model: StructuredModel,
    problem: pulp.LpProblem,
    var_map: Dict[str, pulp.LpVariable],
    identified_model_type: Optional[str] = None,
) -> Tuple[str, Optional[float], List[DecisionVariableResult], str, ProblemSummary]:
    """Executes CBC solver and extracts authoritative results.

    Returns:
        (solver_status, objective_val, variable_results, interpretation, summary)
    """
    # Build Problem Summary
    var_type_counts: Dict[str, int] = {}
    for v in model.variables:
        t_name = v.var_type.value
        var_type_counts[t_name] = var_type_counts.get(t_name, 0) + 1

    pt_val = model.problem_type.value if hasattr(model.problem_type, "value") else str(model.problem_type)
    if not identified_model_type:
        if pt_val in ("IP", "ILP"):
            identified_model_type = "Integer Linear Programming (ILP)"
        elif pt_val in ("MIP", "MILP"):
            identified_model_type = "Mixed-Integer Linear Programming (MILP)"
        else:
            identified_model_type = "Linear Programming (LP)"

    summary = ProblemSummary(
        type=pt_val,
        identified_model_type=identified_model_type,
        objective=model.objective.sense.value.capitalize(),
        variables={
            "count": len(model.variables),
            "breakdown": var_type_counts,
        },
        constraints=len(model.constraints),
    )

    # Solve using CBC
    try:
        raw_status = problem.solve(pulp.PULP_CBC_CMD(msg=False))
        status_str = pulp.LpStatus.get(raw_status, "Solver Error")
    except Exception:
        return (
            "Solver Error",
            None,
            [],
            f"Based on the mathematical formulation, this problem is classified as {identified_model_type}. An error occurred while executing the CBC optimization solver.",
            summary,
        )

    # Map status
    if status_str == "Optimal":
        solver_status = "Optimal"
        obj_val = float(pulp.value(problem.objective))
        
        # Format variables
        var_results: List[DecisionVariableResult] = []
        var_summary_parts = []
        
        for v in model.variables:
            pulp_var = var_map[v.symbol]
            val = float(pulp.value(pulp_var)) if pulp.value(pulp_var) is not None else 0.0
            # Clean floating rounding error: e.g. 3.9999999999 -> 4.0 if close to integer
            if abs(val - round(val)) < 1e-6:
                val = float(round(val))

            desc = v.description.strip() if (v.description and v.description.strip()) else "-"

            var_results.append(
                DecisionVariableResult(
                    variable=v.symbol,
                    description=desc,
                    type=v.var_type.value,
                    value=val,
                )
            )

            if desc != "-":
                var_summary_parts.append(f"{v.symbol} ({desc}) = {val:g}")
            else:
                var_summary_parts.append(f"{v.symbol} = {val:g}")

        # Interpretation: 2-3 sentences concise, stating the identified model paradigm
        vars_text = ", ".join(var_summary_parts)
        is_max = (
            model.objective.sense.value.lower() == "maximize"
            if hasattr(model.objective.sense, "value")
            else str(model.objective.sense).lower() == "maximize"
        )
        sense_word = "maximum" if is_max else "minimum"
        interpretation = (
            f"Based on the mathematical formulation, this problem is classified as {identified_model_type}. "
            f"The optimal solution is found with a {sense_word} objective value of {obj_val:g}. "
            f"To achieve this, the decision variables are: {vars_text}. "
            f"All stated constraints and bounds are fully satisfied."
        )

        return solver_status, obj_val, var_results, interpretation, summary

    elif status_str == "Infeasible":
        return (
            "Infeasible",
            None,
            [],
            f"Based on the mathematical formulation, this problem is classified as {identified_model_type}. The submitted formulation has no feasible solution satisfying all stated constraints.",
            summary,
        )

    elif status_str == "Unbounded":
        return (
            "Unbounded",
            None,
            [],
            f"Based on the mathematical formulation, this problem is classified as {identified_model_type}. The submitted formulation is unbounded, meaning the objective can improve indefinitely while satisfying the stated constraints.",
            summary,
        )

    else:
        return (
            "Solver Error",
            None,
            [],
            f"Based on the mathematical formulation, this problem is classified as {identified_model_type}. The solver could not determine an optimal, infeasible, or unbounded state.",
            summary,
        )
