"""Mathematical input normalisation.

Performs deterministic safe normalisation on student input:
- Unicode comparison operators (≤, ≥)
- Subscript digits (x₁ -> x1)
- Implicit multiplication (5x -> 5*x)
- Division notation preservation
- Variable description extraction (Let x = ...)
"""

import re
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field


# Map unicode subscripts to ascii digits
SUBSCRIPT_MAP = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
    '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9'
}

# Permitted brief framing text phrases (case-insensitive)
PERMITTED_FRAMING = [
    r"^solve\s+the\s+following[:\.\s]*",
    r"^find\s+the\s+optimal\s+solution[:\.\s]*",
    r"^please\s+solve[:\.\s]*",
    r"^determine\s+the\s+optimum[:\.\s]*",
    r"^solve[:\.\s]*",
]


@dataclass
class NormalizedInput:
    raw_text: str
    cleaned_text: str
    math_text: str
    descriptions: Dict[str, str] = field(default_factory=dict)
    framing_detected: Optional[str] = None


def normalize_subscripts(text: str) -> str:
    """Convert Unicode subscripts to regular digits."""
    for sub, digit in SUBSCRIPT_MAP.items():
        text = text.replace(sub, digit)
    return text


def normalize_comparison_operators(text: str) -> str:
    """Normalize unicode and alternate comparison operators and LaTeX shorthands."""
    text = text.replace('≤', '<=').replace('≥', '>=')
    text = text.replace('=<', '<=').replace('=>', '>=')
    text = text.replace(r'\le', '<=').replace(r'\ge', '>=')
    text = text.replace(r'\{', '{').replace(r'\}', '}')
    text = text.replace(r'\in', 'in').replace('∈', 'in')
    text = text.replace(r'\forall', 'for all')
    return text


def extract_variable_descriptions(text: str) -> Tuple[str, Dict[str, str]]:
    """Extract optional variable descriptions such as:

    Let x = number of units of Product A
    Let y = number of units of Product B
    x_1: Units of Product 1
    where x is units ...
    - Let x_1 = Units of Product 1

    Removes these lines from the mathematical text so '=' is not treated as a constraint.
    """
    lines = text.splitlines()
    math_lines = []
    descriptions: Dict[str, str] = {}

    desc_pattern = re.compile(
        r"^\s*(?:let\s+|where\s+|define\s+|def\s+)?([a-zA-Z][a-zA-Z0-9_]*)\s*(?:=|:|\bbe\b|\brepresents?\b)\s*(.+)$",
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        clean_line = re.sub(r"^[-*#/\s]+", "", stripped).strip()
        is_explicit_intro = bool(
            re.match(r"^\s*(?:let|where|define|def)\b", stripped, re.IGNORECASE)
            or re.match(r"^\s*(?:let|where|define|def)\b", clean_line, re.IGNORECASE)
        )
        m = desc_pattern.match(clean_line)

        if m:
            var_sym = m.group(1).strip()
            desc_val = m.group(2).strip()
            words = re.findall(r"[a-zA-Z]{2,}", desc_val)

            if is_explicit_intro and words:
                descriptions[var_sym] = desc_val
                continue
            elif ":" in clean_line and len(words) >= 1 and not re.search(r"<=|>=|<|>|==", clean_line):
                descriptions[var_sym] = desc_val
                continue
            elif (
                len(words) >= 2
                and not re.search(r"<=|>=|<|>|==", clean_line)
                and not re.search(r"[+\-*/^]\s*[a-zA-Z0-9_]+", desc_val)
            ):
                descriptions[var_sym] = desc_val
                continue

        math_lines.append(line)

    return "\n".join(math_lines), descriptions


COMMON_NON_VARIABLE_WORDS = {
    "for", "all", "in", "and", "or", "where", "such", "that", "subject", "to",
    "let", "integer", "integers", "binary", "continuous", "unrestricted", "free",
    "s", "t", "st", "max", "min", "maximize", "minimize", "maximise", "minimise",
    "of", "the", "each", "per", "are", "is", "with"
}


def normalize_implicit_multiplication(text: str) -> str:
    """Convert implicit multiplication like 5x -> 5*x, 2.5y -> 2.5*y.
    
    Does not modify common English words like '0 for all j', and does not
    treat digits inside variable identifiers (e.g. x_1R, x_2P) as multiplication.
    """
    def _repl_num_var(match: re.Match) -> str:
        num = match.group(1)
        word = match.group(2)
        if word.lower() in COMMON_NON_VARIABLE_WORDS:
            return match.group(0)
        return f"{num}*{word}"

    tokens = []
    for line in text.splitlines():
        # Replace number followed immediately by letter: e.g. 5x, 5x1, 2*x_1
        # Use negative lookbehind to ensure number is not part of a variable name like x_1R
        line_norm = re.sub(r"(?<![a-zA-Z_0-9.])(\d+(?:\.\d+)?)\s*([a-zA-Z][a-zA-Z0-9_]*)", _repl_num_var, line)
        # Number followed immediately by parenthesis: 5(x -> 5*(x
        line_norm = re.sub(r"(?<![a-zA-Z_0-9.])(\d+(?:\.\d+)?)\s*\(", r"\1*(", line_norm)
        # ) followed by variable: )x -> )*x
        def _repl_paren_var(match: re.Match) -> str:
            word = match.group(1)
            if word.lower() in COMMON_NON_VARIABLE_WORDS:
                return match.group(0)
            return f")*{word}"
        line_norm = re.sub(r"\)\s*([a-zA-Z][a-zA-Z0-9_]*)", _repl_paren_var, line_norm)
        tokens.append(line_norm)
    return "\n".join(tokens)


def strip_permitted_framing(text: str) -> Tuple[str, Optional[str]]:
    """Detect and strip permitted brief framing text from the start of submission."""
    cleaned = text.strip()
    detected = None
    for pattern in PERMITTED_FRAMING:
        m = re.match(pattern, cleaned, re.IGNORECASE)
        if m:
            detected = m.group(0).strip()
            cleaned = cleaned[m.end():].strip()
            break
    return cleaned, detected


def synthesize_multiline_objective(text: str) -> str:
    """Reconstruct split objective functions across multiple lines.
    
    If lines immediately following min or max begin with arithmetic operators
    (like + or -), merge them onto a single line before validating the
    objective requirement.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out_lines = []
    in_obj = False
    current_obj = ""

    for line in lines:
        if not in_obj:
            if re.match(r"^\s*(?:max|min|maximize|minimize|maximise|minimise)\b", line, re.IGNORECASE):
                in_obj = True
                current_obj = line
            else:
                out_lines.append(line)
        else:
            # Check if line is a subject to marker, constraint, or domain declaration
            is_st = bool(re.match(r"^\s*(?:s\.t\.|st\b|subject\s+to:?|such\s+that:?)", line, re.IGNORECASE))
            has_comparison = bool(re.search(r"(<=|>=|=|<|>|≤|≥)", line))
            is_domain_shorthand = bool(re.search(r"\b(in\s*\{|binary|integers?)\b", line, re.IGNORECASE))

            if is_st or has_comparison or is_domain_shorthand:
                in_obj = False
                out_lines.append(current_obj)
                out_lines.append(line)
                current_obj = ""
            else:
                hdr_match = re.match(r"^(max|min|maximize|minimize|maximise|minimise)\b\s*$", current_obj, re.IGNORECASE)
                if hdr_match:
                    current_obj = f"{current_obj} {line}"
                elif line.startswith(("+", "-")) or current_obj.rstrip().endswith(("+", "-")):
                    current_obj = f"{current_obj} {line}"
                else:
                    current_obj = f"{current_obj} + {line}"

    if in_obj and current_obj:
        out_lines.append(current_obj)

    return "\n".join(out_lines)


def extract_decision_variables_from_math(text: str) -> List[str]:
    """Extract unique decision variable symbols present in objective and constraints."""
    vars_found: List[str] = []
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        # Skip lines that are purely bounds or set declarations
        if re.search(r"\b(for\s+all|\\forall|in\s*\{|binary|integers?)\b", line_s, re.IGNORECASE):
            continue
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", line_s)
        for tok in tokens:
            if tok.lower() not in COMMON_NON_VARIABLE_WORDS:
                if tok not in vars_found:
                    vars_found.append(tok)
    return vars_found


def dereference_math_set_shorthands(text: str) -> str:
    """De-reference math set shorthands into explicit variable list format.

    Interprets:
    - 'y_i in {0, 1} for all i' -> 'y_1, y_2, y_3 in {0, 1}'
    - 'x_ij >= 0 for all i, j' -> 'x_1R, x_1P, ... >= 0'
    Maps shorthand expressions internally to a list format so the Variable Domains / Bounds
    checker passes automatically.
    """
    vars_in_model = extract_decision_variables_from_math(text)
    new_lines = []

    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            new_lines.append(line)
            continue

        # 1. Shorthand: y_i in {0, 1} for all i (or y_i \in {0, 1}, etc.)
        m_bin = re.match(
            r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(?:\\in|in)\s*\\?\{\s*0\s*,\s*1\s*\\?\}\s*(?:(?:,|for\s+all|\\forall|for|all)\s+([a-zA-Z0-9_,\s]*))?$",
            line_s,
            re.IGNORECASE,
        )
        if m_bin:
            shorthand_sym = m_bin.group(1)
            prefix = re.sub(r"[ij_]+$", "", shorthand_sym).lower()
            matching = [v for v in vars_in_model if v.lower().startswith(prefix) or not prefix]
            if matching and (len(matching) > 1 or shorthand_sym not in vars_in_model):
                new_lines.append(f"{', '.join(matching)} in {{0, 1}}")
                continue

        # 2. Shorthand: x_ij >= 0 for all i, j (or x_i >= 0, etc.)
        m_ineq = re.match(
            r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(>=|=>|≥|<=|=<|≤|>|<|=)\s*([0-9\.\-]+)\s*(?:and|,)?\s*(?:are\s+)?(integer|integers|binary)?\s*(?:,|\b)?\s*(?:for\s+all|\\forall|for|all)\s+([a-zA-Z0-9_,\s=]+)$",
            line_s,
            re.IGNORECASE,
        )
        if m_ineq:
            shorthand_sym = m_ineq.group(1)
            op = m_ineq.group(2)
            val = m_ineq.group(3)
            int_type = m_ineq.group(4)
            prefix = re.sub(r"[ij_]+$", "", shorthand_sym).lower()
            matching = [v for v in vars_in_model if v.lower().startswith(prefix) or not prefix]
            if matching and (len(matching) > 1 or shorthand_sym not in vars_in_model):
                suffix = f", {int_type}" if int_type else ""
                new_lines.append(f"{', '.join(matching)} {op} {val}{suffix}")
                continue

        # 3. Fallback: non-quantified shorthand like 'x_ij >= 0' where x_ij is not in vars_in_model
        m_ineq_plain = re.match(
            r"^\s*([a-zA-Z][a-zA-Z0-9_]*)\s*(>=|=>|≥|<=|=<|≤|>|<|=)\s*([0-9\.\-]+)\s*$",
            line_s,
            re.IGNORECASE,
        )
        if m_ineq_plain:
            shorthand_sym = m_ineq_plain.group(1)
            if shorthand_sym not in vars_in_model and re.search(r"_[ijkltmnab]+$", shorthand_sym):
                prefix = re.sub(r"[ij_]+$", "", shorthand_sym).lower()
                matching = [v for v in vars_in_model if v.lower().startswith(prefix) or not prefix]
                if matching:
                    op = m_ineq_plain.group(2)
                    val = m_ineq_plain.group(3)
                    new_lines.append(f"{', '.join(matching)} {op} {val}")
                    continue

        new_lines.append(line)

    return "\n".join(new_lines)


def normalize_input(raw_text: str) -> NormalizedInput:
    """Run full normalisation pipeline on raw student submission."""
    text = raw_text.strip()
    
    # 1. Normalize unicode and LaTeX comparison and set operators
    text = normalize_comparison_operators(text)
    
    # 2. Normalize unicode subscripts
    text = normalize_subscripts(text)
    
    # 3. Strip permitted framing text if present
    cleaned_after_framing, framing = strip_permitted_framing(text)
    
    # 4. Extract variable descriptions
    math_text, descriptions = extract_variable_descriptions(cleaned_after_framing)
    
    # 5. Reconstruct split multi-line objective functions
    math_text = synthesize_multiline_objective(math_text)

    # 6. De-reference math set shorthands to list format
    math_text = dereference_math_set_shorthands(math_text)

    # 7. Normalize implicit multiplication in math text
    math_text_norm = normalize_implicit_multiplication(math_text)
    
    return NormalizedInput(
        raw_text=raw_text,
        cleaned_text=cleaned_after_framing,
        math_text=math_text_norm,
        descriptions=descriptions,
        framing_detected=framing,
    )
