"""Deterministic PuLP model builder.

Constructs pulp.LpProblem directly and exclusively from validated StructuredModel.
Never receives raw student text. Uses safe internal variable names (v1, v2, ...).
"""

from typing import Dict, Tuple
import pulp
from app.models.structured_model import (
    StructuredModel,
    ObjectiveSense,
    VariableType,
)


def build_pulp_model(
    model: StructuredModel,
) -> Tuple[pulp.LpProblem, Dict[str, pulp.LpVariable]]:
    """Builds a PuLP problem deterministically from validated StructuredModel.

    Returns:
        (problem, symbol_to_pulp_var_map)
    """
    # 1. Create problem with sense
    sense = (
        pulp.LpMaximize
        if model.objective.sense == ObjectiveSense.MAXIMIZE
        else pulp.LpMinimize
    )
    problem = pulp.LpProblem("OptimizationProblem", sense)

    # 2. Create PuLP variables using safe internal identifiers
    var_map: Dict[str, pulp.LpVariable] = {}
    for v in model.variables:
        if v.var_type == VariableType.BINARY:
            pulp_var = pulp.LpVariable(v.id, cat=pulp.LpBinary)
        elif v.var_type == VariableType.INTEGER:
            pulp_var = pulp.LpVariable(
                v.id,
                lowBound=v.lower_bound,
                upBound=v.upper_bound,
                cat=pulp.LpInteger,
            )
        else:
            pulp_var = pulp.LpVariable(
                v.id,
                lowBound=v.lower_bound,
                upBound=v.upper_bound,
                cat=pulp.LpContinuous,
            )
        var_map[v.symbol] = pulp_var

    # 3. Add objective
    obj_expr = pulp.lpSum(
        [term.coeff * var_map[term.var_symbol] for term in model.objective.terms]
    )
    if model.objective.constant != 0.0:
        obj_expr += model.objective.constant
    problem += obj_expr, "Objective"

    # 4. Add constraints
    for c in model.constraints:
        c_expr = pulp.lpSum(
            [term.coeff * var_map[term.var_symbol] for term in c.terms]
        )
        if c.operator == "<=":
            problem += (c_expr <= c.rhs), c.name
        elif c.operator == ">=":
            problem += (c_expr >= c.rhs), c.name
        elif c.operator == "=":
            problem += (c_expr == c.rhs), c.name

    return problem, var_map
