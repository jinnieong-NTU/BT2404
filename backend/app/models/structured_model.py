"""Structured mathematical model representation.

This represents the validated mathematical programme used deterministically by
the PuLP builder and CBC solver.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class ProblemType(str, Enum):
    LP = "LP"
    IP = "IP"
    MIP = "MIP"


class ObjectiveSense(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class VariableType(str, Enum):
    CONTINUOUS = "continuous"
    INTEGER = "integer"
    BINARY = "binary"


class LinearTerm(BaseModel):
    var_symbol: str
    coeff: float


class ObjectiveModel(BaseModel):
    sense: ObjectiveSense
    terms: List[LinearTerm] = Field(default_factory=list)
    constant: float = 0.0


class VariableModel(BaseModel):
    id: str  # Safe internal identifier: v1, v2, ...
    symbol: str  # Original symbol: x, y, x1, etc.
    var_type: VariableType = VariableType.CONTINUOUS
    lower_bound: Optional[float] = 0.0
    upper_bound: Optional[float] = None
    description: Optional[str] = None  # None if not provided; never invented


class ConstraintModel(BaseModel):
    id: str  # Safe internal identifier: c1, c2, ...
    name: str = ""
    terms: List[LinearTerm] = Field(default_factory=list)
    operator: str  # "<=", ">=", "="
    rhs: float


class StructuredModel(BaseModel):
    problem_type: ProblemType
    objective: ObjectiveModel
    variables: List[VariableModel]
    constraints: List[ConstraintModel]
