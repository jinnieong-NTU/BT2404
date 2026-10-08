"""Deterministic PuLP Python code generator.

Generates clean Python code from the validated StructuredModel.
Both actual execution and display code originate from the exact same validated model.
"""

from app.models.structured_model import StructuredModel, ObjectiveSense, VariableType


def generate_pulp_code(model: StructuredModel) -> str:
    """Generates Python PuLP source code matching the validated model."""
    lines = [
        "import pulp",
        "",
        "# 1. Initialize Problem",
    ]

    sense_str = "pulp.LpMaximize" if model.objective.sense == ObjectiveSense.MAXIMIZE else "pulp.LpMinimize"
    lines.append(f"problem = pulp.LpProblem(\"OptimizationProblem\", {sense_str})")
    lines.append("")
    lines.append("# 2. Define Decision Variables")

    for v in model.variables:
        comment = f"  # {v.description}" if v.description else ""
        if v.var_type == VariableType.BINARY:
            lines.append(f"{v.id} = pulp.LpVariable(\"{v.id}\", cat=pulp.LpBinary){comment}")
        elif v.var_type == VariableType.INTEGER:
            low = v.lower_bound if v.lower_bound is not None else "None"
            up = v.upper_bound if v.upper_bound is not None else "None"
            lines.append(f"{v.id} = pulp.LpVariable(\"{v.id}\", lowBound={low}, upBound={up}, cat=pulp.LpInteger){comment}")
        else:
            low = v.lower_bound if v.lower_bound is not None else "None"
            up = v.upper_bound if v.upper_bound is not None else "None"
            lines.append(f"{v.id} = pulp.LpVariable(\"{v.id}\", lowBound={low}, upBound={up}, cat=pulp.LpContinuous){comment}")

    lines.append("")
    lines.append("# 3. Objective Function")
    obj_terms = []
    symbol_to_id = {v.symbol: v.id for v in model.variables}
    for t in model.objective.terms:
        var_id = symbol_to_id[t.var_symbol]
        if t.coeff == 1.0:
            obj_terms.append(f"{var_id}")
        elif t.coeff == -1.0:
            obj_terms.append(f"-{var_id}")
        else:
            obj_terms.append(f"{t.coeff:g} * {var_id}")

    obj_str = " + ".join(obj_terms).replace("+ -", "- ")
    if model.objective.constant != 0.0:
        obj_str += f" + {model.objective.constant:g}"
    lines.append(f"problem += ({obj_str}), \"Objective\"")

    lines.append("")
    lines.append("# 4. Constraints")
    for idx, c in enumerate(model.constraints, start=1):
        c_terms = []
        for t in c.terms:
            var_id = symbol_to_id[t.var_symbol]
            if t.coeff == 1.0:
                c_terms.append(f"{var_id}")
            elif t.coeff == -1.0:
                c_terms.append(f"-{var_id}")
            else:
                c_terms.append(f"{t.coeff:g} * {var_id}")

        lhs_str = " + ".join(c_terms).replace("+ -", "- ")
        if not lhs_str:
            lhs_str = "0"
        lines.append(f"problem += ({lhs_str} {c.operator} {c.rhs:g}), \"{c.name}\"")

    lines.append("")
    lines.append("# 5. Solve via CBC")
    lines.append("problem.solve(pulp.PULP_CBC_CMD(msg=False))")
    lines.append("")
    lines.append("# 6. Output Solution")
    lines.append("print(f\"Status: {pulp.LpStatus[problem.status]}\")")
    lines.append("if problem.status == pulp.constants.LpStatusOptimal:")
    lines.append("    print(f\"Objective Value: {pulp.value(problem.objective)}\")")
    for v in model.variables:
        lines.append(f"    print(f\"{v.symbol} ({v.id}) = {{pulp.value({v.id})}}\")")

    return "\n".join(lines)
