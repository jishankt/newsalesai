"""Answer Coverage Validator for Kepler Tech SalesAI.

Verifies that all explicit questions, capabilities, and requested attributes
in the customer's message are answered by the composed response.
Prevents silent omission of multi-part questions.
"""

from typing import Dict, Any, List, Tuple
import re
from domain.response_context import VerifiedEvidenceBundle


class AnswerCoverageValidator:
    """Validates answer coverage across multiple requested attributes."""

    @classmethod
    def validate_coverage(
        cls,
        user_message: str,
        response_text: str,
        requested_attributes: List[str],
        evidence_bundle: VerifiedEvidenceBundle,
    ) -> Tuple[bool, Dict[str, bool], List[str]]:
        """
        Validates whether each requested attribute was addressed in the response.
        Returns: (is_fully_covered, coverage_map, missing_attributes)
        """
        resp_l = (response_text or "").lower()
        coverage_map: Dict[str, bool] = {}
        missing_attrs: List[str] = []

        for attr in requested_attributes:
            covered = False
            if attr == "wifi":
                covered = any(w in resp_l for w in ["wi-fi", "wifi", "wireless", "ethernet", "network"])
            elif attr == "scanner":
                covered = any(w in resp_l for w in ["scanner", "scanning", "scan", "multifunction", "print only", "print-only"])
            elif attr in ("compatible_ink", "ink"):
                covered = any(w in resp_l for w in ["ink", "cartridge", "ultrachrome", "consumable", "tank"])
            elif attr == "speed":
                covered = any(w in resp_l for w in ["speed", "ppm", "seconds", "sec", "d/min", "fast"])
            elif attr == "price":
                covered = any(w in resp_l for w in ["aed", "price", "cost", "vat", "quote", "pricing"])
            elif attr in ("dimension", "dimensions"):
                covered = any(w in resp_l for w in ["inch", "width", "mm", "cm", "dimensions", "footprint"])
            elif attr in ("t-shirts", "apparel", "garment"):
                covered = any(w in resp_l for w in ["t-shirt", "t shirt", "apparel", "garment", "fabric", "textile", "sublimation", "dtg"])
            elif attr in ("media_request", "photo"):
                covered = any(w in resp_l for w in ["photo", "picture", "image", "http", "view", "details"])
            else:
                covered = attr.lower() in resp_l

            coverage_map[attr] = covered
            if not covered:
                missing_attrs.append(attr)

        is_fully_covered = len(missing_attrs) == 0
        return is_fully_covered, coverage_map, missing_attrs


answer_coverage_validator = AnswerCoverageValidator()
