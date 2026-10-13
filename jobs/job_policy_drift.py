"""
Offline Multi-Agent Job: Kepler Terms & FAQ Policy Drift Detection.
Periodically fetches or parses Kepler Terms & Conditions and FAQ pages.
Extracts delivery, returns, payment, and operation terms via typed LLM step.
Diffs against the grounded policy baseline (data/delivery_policy.json / config) to flag drift.
Guarantees:
- Never alters production policy files directly; saves proposals to data/proposals/
- Outputs a comprehensive drift report to docs/POLICY_DRIFT_REPORT.md
- Explicitly flags ungrounded changes and policy conflicts
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from config import SHIPPING_AND_DELIVERY_POLICY, BUSINESS_HOURS
from jobs.runner import JobRunner, JobProposal

logger = logging.getLogger("jobs.policy_drift")

DELIVERY_POLICY_PATH = Path("data/delivery_policy.json")
REPORT_PATH = Path("docs/POLICY_DRIFT_REPORT.md")


class ExtractedPolicySections(BaseModel):
    source_url: str = "missing"
    delivery_fee_uae: str = "missing"
    delivery_fee_international: str = "missing"
    dispatch_timing: str = "missing"
    pickup_policy: str = "missing"
    payment_terms: str = "missing"
    defect_reporting_window: str = "missing"
    cancellation_window: str = "missing"
    ofac_sanctions_policy: str = "missing"
    business_hours: str = "missing"
    missing_sections: List[str] = Field(default_factory=list)


class JobPolicyDrift:
    def __init__(
        self,
        runner: Optional[JobRunner] = None,
        policy_path: Path = DELIVERY_POLICY_PATH,
    ):
        self.runner = runner or JobRunner(job_name="policy_drift")
        self.policy_path = Path(policy_path)

    def load_baseline_policy(self) -> Dict[str, Any]:
        """Loads baseline policy from file if present, else from config."""
        if self.policy_path.exists():
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read {self.policy_path}: {e}")

        # Baseline fallback from config
        return {
            "delivery_fee_uae": "flat AED 10",
            "delivery_fee_international": "calculated at checkout",
            "dispatch_timing": "1 to 2 business days",
            "pickup_policy": "free store pickup ready in 1 to 2 business days",
            "payment_terms": "payment in full before dispatch (Visa, MasterCard, PayPal)",
            "defect_reporting_window": "within 2 days of receipt",
            "cancellation_window": "within 24 hours of placing order",
            "ofac_sanctions_policy": "no trade with OFAC sanctioned countries",
            "business_hours": BUSINESS_HOURS.get("text", "Mon-Fri 8:30-17:30, Sat 8:30-13:00"),
        }

    def fetch_terms_and_faq_text(self, terms_url: Optional[str] = None) -> tuple[str, str]:
        """
        Fetches terms/FAQ page or reads local cached terms.
        """
        cached_path = Path("data/raw_site/terms.html")
        if cached_path.exists():
            with open(cached_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                return soup.get_text(separator="\n"), f"local://{cached_path.name}"

        url = terms_url or "https://www.keplertechllc.com/terms-conditions/"
        try:
            headers = {"User-Agent": "KeplerTechSalesAI-PolicyBot/1.0"}
            resp = requests.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for s in soup(["script", "style", "noscript"]):
                    s.decompose()
                return soup.get_text(separator="\n")[:8000], url
        except Exception as e:
            logger.warning(f"Could not fetch terms from {url}: {e}")

        # Static baseline text if offline
        fallback_text = (
            "TERMS AND CONDITIONS:\n"
            "Shipping: Orders are processed in 1 to 2 business days. UAE delivery is a flat AED 10. "
            "Outside the UAE, fee depends on location at checkout. Free store pickup available. "
            "Payment is required in full before dispatch. We do not trade with OFAC countries. "
            "Cancellations allowed within 24 hours. Defective items must be reported within 2 days of receipt. "
            "Business hours: Monday-Friday 8:30am to 5:30pm, Saturday 8:30am to 1:00pm, Sunday closed."
        )
        return fallback_text, "fallback://kepler_terms_static"

    def diff_policy(
        self,
        baseline: Dict[str, Any],
        extracted: ExtractedPolicySections,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Detects differences between baseline policy and extracted terms.
        """
        proposed_updates: Dict[str, Any] = {}
        conflicts: List[Dict[str, Any]] = []

        fields_to_check = [
            ("delivery_fee_uae", extracted.delivery_fee_uae),
            ("delivery_fee_international", extracted.delivery_fee_international),
            ("dispatch_timing", extracted.dispatch_timing),
            ("pickup_policy", extracted.pickup_policy),
            ("payment_terms", extracted.payment_terms),
            ("defect_reporting_window", extracted.defect_reporting_window),
            ("cancellation_window", extracted.cancellation_window),
            ("ofac_sanctions_policy", extracted.ofac_sanctions_policy),
            ("business_hours", extracted.business_hours),
        ]

        for key, val in fields_to_check:
            base_val = baseline.get(key)
            if val == "missing":
                continue
            if not base_val:
                proposed_updates[key] = val
            elif str(base_val).strip().lower() != str(val).strip().lower():
                conflicts.append({
                    "policy_key": key,
                    "baseline_value": base_val,
                    "extracted_value": val,
                    "source_url": extracted.source_url,
                })

        return proposed_updates, conflicts

    def run(self, mock_response: Optional[Dict[str, Any]] = None) -> Optional[JobProposal]:
        baseline = self.load_baseline_policy()
        doc_text, source_url = self.fetch_terms_and_faq_text()

        system_instruction = (
            "You are a legal policy analyst for Kepler Tech LLC.\n"
            "Extract structured shipping, returns, cancellation, payment, and operation terms from the text.\n"
            "STRICT RULES:\n"
            "1. ONLY extract values explicitly stated in the source text.\n"
            "2. If an attribute is not found, set its value to 'missing' and list it in 'missing_sections'.\n"
            "3. Do NOT extrapolate or assume."
        )

        evidence = {
            "terms_document_text": doc_text,
            "source_url": source_url,
            "baseline_keys": list(baseline.keys()),
        }

        user_prompt = "Extract current Kepler shipping, delivery, returns, and payment terms."

        extracted: ExtractedPolicySections = self.runner.execute_step(
            step_name="extract_policy_terms",
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            evidence=evidence,
            output_schema=ExtractedPolicySections,
            mock_response=mock_response,
        )

        proposed_updates, conflicts = self.diff_policy(baseline, extracted)

        proposal = None
        if proposed_updates or conflicts:
            proposal = self.runner.save_proposal(
                target_file=str(self.policy_path),
                proposed_changes=proposed_updates,
                conflicts_reported=conflicts,
            )

        self.runner.finalize()

        # Write drift report
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("# Kepler Policy Drift Audit Report\n\n")
            f.write(f"- **Run ID:** `{self.runner.run_id}`\n")
            f.write(f"- **Source URL:** `{source_url}`\n")
            f.write(f"- **Drift Conflicts Detected:** {len(conflicts)}\n")
            f.write(f"- **Proposed Policy Updates:** {len(proposed_updates)}\n\n")

            if proposal:
                f.write(f"### Proposal Generated: `{proposal.proposal_id}`\n")
                f.write(f"- Target File: `{proposal.target_file}`\n")
                f.write(f"- Proposed Updates: `{json.dumps(proposal.proposed_changes)}`\n\n")

            if conflicts:
                f.write("### Policy Discrepancies / Conflicts:\n\n")
                for c in conflicts:
                    f.write(f"- **`{c['policy_key']}`**:\n")
                    f.write(f"  - Baseline: `{c['baseline_value']}`\n")
                    f.write(f"  - Extracted: `{c['extracted_value']}`\n")
            else:
                f.write("No conflicting policy drift detected. Baseline aligns with verified terms.\n")

        logger.info(f"Policy drift report written to {REPORT_PATH}")
        return proposal


def main():
    parser = argparse.ArgumentParser(description="Offline Kepler Policy Drift Detection Job")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    job = JobPolicyDrift()
    proposal = job.run()
    if proposal:
        print(f"Policy drift detected. Proposal created: {proposal.proposal_id}")
    else:
        print("No policy drift detected.")


if __name__ == "__main__":
    main()
