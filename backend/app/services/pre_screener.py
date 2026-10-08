"""Deterministic security pre-screener and Gate 1 (Topic Lock) checker."""

import re
from typing import Tuple, Optional


# Prompt injection keywords and patterns
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
    r"forget\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
    r"act\s+as\s+(?:a\s+)?(?:tutor|assistant|bot|code|dan|admin|evaluator)",
    r"you\s+are\s+now\s+(?:a\s+)?(?:tutor|developer|unrestricted)",
    r"pretend\s+(?:to\s+be|you\s+are)",
    r"system\s+prompt",
    r"(?:reveal|display|output|show|print)\s+(?:your\s+)?(?:system|hidden|internal)\s+(?:prompt|instructions|rules|api\s*key)",
    r"(?:bypass|disable|override|skip)\s+(?:the\s+)?(?:validation|security|rules|gates|checks)",
    r"jailbreak",
    r"developer\s+mode",
    r"repeat\s+after\s+me",
    r"who\s+(?:created|made|programmed)\s+you",
    r"what\s+is\s+your\s+(?:system\s+prompt|role)",
]

# Tutoring, conceptual questions, coding requests
OFF_TOPIC_PATTERNS = [
    r"^(?:how\s+(?:do|can|to)|what\s+is|why\s+is|explain|describe|tell\s+me\s+about)\b",
    r"\b(?:give\s+me\s+a\s+hint|need\s+a\s+hint|can\s+you\s+help\s+me\s+formulate)\b",
    r"\b(?:write\s+(?:a\s+)?(?:python|c\+\+|code|script|program))\b",
    r"\b(?:debug\s+(?:my|this)\s+code)\b",
    r"\b(?:teach\s+me|help\s+me\s+understand)\b",
]

REJECTION_TOPIC_LOCK_MESSAGE = (
    "⚠️ This tool only accepts optimization problems submitted as mathematical "
    "programme formulations. It does not answer general questions, provide hints, "
    "explain concepts, or perform any other function."
)


def check_gate_1(raw_text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Check Gate 1 (Topic Lock).

    Returns:
        (passed, gate_failed, rejection_code, message)
    """
    text = raw_text.strip()
    if not text:
        return False, "GATE_1", "TOPIC_LOCK", REJECTION_TOPIC_LOCK_MESSAGE

    # 1. Prompt Injection Rule (Section 26) - Checked strictly across entire submission
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "GATE_1", "TOPIC_LOCK", REJECTION_TOPIC_LOCK_MESSAGE

    # 2. Check for general questions, tutoring requests, or conversational queries
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "GATE_1", "TOPIC_LOCK", REJECTION_TOPIC_LOCK_MESSAGE

    # 3. Check for narrative-only problem without mathematical programme
    has_obj = bool(re.search(r"\b(max|min|maximize|minimize|maximise|minimise)\b", text, re.IGNORECASE))
    has_rel = bool(re.search(r"(<=|>=|=|<|>|≤|≥)", text))

    if not has_obj and not has_rel:
        return False, "GATE_1", "TOPIC_LOCK", REJECTION_TOPIC_LOCK_MESSAGE

    # Narrative word problems (e.g., "A company manufactures chairs and tables...")
    narrative_markers = [
        "company", "manufactures", "requires", "available", "hours",
        "profit", "costs", "bakery", "makes", "takes", "find the",
        "calculate", "determine the optimal", "factory", "worker", "units of"
    ]
    narrative_count = sum(
        1 for marker in narrative_markers if re.search(r"\b" + marker + r"\b", text, re.IGNORECASE)
    )

    if not has_obj and narrative_count >= 2:
        return False, "GATE_1", "TOPIC_LOCK", REJECTION_TOPIC_LOCK_MESSAGE

    return True, None, None, None
