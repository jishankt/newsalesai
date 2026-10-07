"""
Naturalness Validator for Kepler Tech SalesAI.

Detects and sanitizes:
- Excessive markdown formatting (e.g., bold asterisks `**`, raw markdown headers `###`)
- Robotic opener phrases ("Based on your requirements...", "Here are the top-matching...")
- Unsolicited sales pitches during factual/technical answers
- Repetitive questions already asked or answered in question ledger
- Database table dumps
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import re
import logging

from domain.conversation_state import ConversationState

logger = logging.getLogger("naturalness_validator")


@dataclass
class NaturalnessResult:
    natural: bool
    issues: List[str] = field(default_factory=list)
    severity: str = "low"  # low, medium, high


class NaturalnessValidator:
    """Validates and polishes conversational output for natural human tone."""

    ROBOTIC_PHRASES = [
        r"based on your (?:requirements|criteria|specifications)",
        r"here are the top-matching",
        r"according to your criteria",
        r"take a look at these approved",
        r"as an ai (?:sales|consultant|assistant)",
    ]

    UNSOLICITED_PITCH_PATTERNS = [
        r"game-changer",
        r"revolutionize your",
        r"unparalleled performance",
        r"best-in-class excellence",
        r"state-of-the-art marvel",
    ]

    @classmethod
    def validate(
        cls,
        text: str,
        customer_behavior: str = "EXPLORING",
        state: Optional[ConversationState] = None,
    ) -> NaturalnessResult:
        """Evaluates whether the generated text meets human sales consultant quality."""
        issues: List[str] = []
        severity = "low"

        # 1. Bold asterisks check (WhatsApp conversational rule)
        if "**" in text:
            issues.append("Contains markdown bold asterisks (**)")

        # 2. Markdown headers check
        if re.search(r"^#{1,6}\s+", text, flags=re.MULTILINE):
            issues.append("Contains markdown headers (###)")

        # 3. Robotic phrases check
        t_l = text.lower()
        for pat in cls.ROBOTIC_PHRASES:
            if re.search(pat, t_l):
                issues.append(f"Contains robotic template phrase: '{pat}'")
                severity = "medium"

        # 4. Unsolicited marketing pitch during technical inquiry
        if customer_behavior in ("RESEARCHING", "FRUSTRATED", "EVALUATING"):
            for pitch_pat in cls.UNSOLICITED_PITCH_PATTERNS:
                if re.search(pitch_pat, t_l):
                    issues.append(f"Contains unsolicited marketing fluff: '{pitch_pat}'")
                    severity = "high"

        # 5. Question loop check
        if state and state.question_ledger and "?" in text:
            # Extract questions in text
            questions_in_text = re.findall(r"([^.?!]+\?)", text)
            for q in questions_in_text:
                q_clean = q.strip().lower()
                for item in state.question_ledger.items:
                    if item.origin == "agent" and item.status.value == "answered" and item.normalized_text and item.normalized_text in q_clean:
                        issues.append(f"Repeats already answered question: '{item.semantic_key}'")
                        severity = "high"

        is_natural = len(issues) == 0
        return NaturalnessResult(natural=is_natural, issues=issues, severity=severity)

    @classmethod
    def sanitize(
        cls,
        text: str,
        customer_behavior: str = "EXPLORING",
        state: Optional[ConversationState] = None,
    ) -> str:
        """
        Deterministically strips markdown formatting flaws and repetitive questions
        without altering verified factual content.
        """
        if not text:
            return ""

        cleaned = text

        # Strip bold asterisks
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = cleaned.replace("**", "")

        # Strip markdown headers
        cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)

        # Strip bullet points into natural sentences
        cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)

        # If customer is frustrated, strip any trailing sales pitch or question
        if customer_behavior == "FRUSTRATED":
            # Keep only the answer portion
            lines = cleaned.split("\n")
            filtered_lines = [l for l in lines if not l.strip().endswith("?") or "apolog" in l.lower() or "clarif" in l.lower()]
            cleaned = "\n".join(filtered_lines).strip()

        # Deduplicate trailing questions if already asked in state
        if state and state.question_ledger:
            for item in state.question_ledger.items:
                if item.origin == "agent" and item.asked_count >= 1:
                    # Strip if repeated in the final sentence
                    if item.original_text and item.original_text in cleaned:
                        cleaned = cleaned.replace(item.original_text, "").strip()

        return cleaned.strip()
