"""
Offline Multi-Agent Job: Lead Executive Brief & Dispatcher.
Extracts qualified commercial leads from conversations, synthesizes an executive brief
using local LLM, and dispatches the summary to sales representatives via jobs.notifier.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from jobs.runner import JobRunner
from jobs.notifier import NotificationDispatcher, NotificationPayload
from persistence.lead_repository import lead_repository
from persistence.state_repository import StateRepository

logger = logging.getLogger("jobs.lead_brief")


class LeadBriefOutput(BaseModel):
    lead_id: str
    customer_name: str
    phone: str
    email: str = "missing"
    company: str = "missing"
    product_interest: str
    estimated_volume: str = "missing"
    urgency: str = "medium"  # "high", "medium", "low", "unspecified"
    next_step: str
    executive_brief: str = Field(
        ...,
        description="2-4 sentence executive brief summarizing client context, equipment requirements, and immediate action item."
    )


def build_lead_brief_prompt(lead: Dict[str, Any], conversation_context: Optional[str] = None) -> tuple[str, str, Dict[str, Any]]:
    system_instruction = (
        "You are an executive commercial sales assistant for Kepler Tech LLC (Dubai).\n"
        "Your task is to analyze the qualified lead record and conversation history to produce a structured "
        "executive sales brief for our enterprise equipment sales team.\n"
        "Ground all facts strictly in the verified evidence provided. If information is missing, explicitly output 'missing'."
    )

    evidence = {
        "lead_id": str(lead.get("lead_id", "")),
        "customer_name": lead.get("customer_name") or "missing",
        "company": lead.get("company") or "missing",
        "phone": lead.get("phone") or "missing",
        "email": lead.get("email") or "missing",
        "product_interest": lead.get("product_interest") or "missing",
        "notes": lead.get("notes") or "missing",
        "conversation_excerpt": conversation_context or "Not provided",
    }

    user_prompt = (
        f"Generate an executive commercial sales brief for Lead #{evidence['lead_id']} ({evidence['customer_name']}).\n"
        f"Synthesize the client's equipment interest, estimated volume, urgency level, and recommended next action step."
    )

    return system_instruction, user_prompt, evidence


class JobLeadBrief:
    def __init__(self, runner: Optional[JobRunner] = None, notifier: Optional[NotificationDispatcher] = None):
        self.runner = runner or JobRunner(job_name="lead_brief")
        self.notifier = notifier or NotificationDispatcher()
        self.state_repo = StateRepository()

    def process_lead(
        self,
        lead: Dict[str, Any],
        mock_response: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> Optional[LeadBriefOutput]:
        lead_id = str(lead.get("lead_id", ""))
        event_id = f"lead_{lead_id}"

        if not force and self.notifier.is_already_dispatched(event_id):
            logger.info(f"Lead #{lead_id} already briefed and dispatched. Skipping.")
            return None

        # Fetch conversation context if available
        session_id = lead.get("session_id")
        conv_context = None
        if session_id:
            try:
                state, history = self.state_repo.load_state(session_id)
                if history:
                    # Take last 6 turns
                    recent = history[-6:]
                    conv_context = "\n".join([f"{t.get('role', 'user')}: {t.get('content', '')}" for t in recent])
            except Exception as e:
                logger.warning(f"Could not load session {session_id} history: {e}")

        sys_inst, prompt, evidence = build_lead_brief_prompt(lead, conv_context)

        # Run typed step
        brief_output: LeadBriefOutput = self.runner.execute_step(
            step_name=f"synthesize_brief_lead_{lead_id}",
            system_instruction=sys_inst,
            user_prompt=prompt,
            evidence=evidence,
            output_schema=LeadBriefOutput,
            mock_response=mock_response,
        )

        # Dispatch notification
        subject = f"Commercial Lead Alert: {brief_output.customer_name} ({brief_output.product_interest})"
        body = (
            f"KEPLER TECH SALES ALERT - NEW QUALIFIED LEAD\n"
            f"============================================\n"
            f"Lead ID: #{brief_output.lead_id}\n"
            f"Customer: {brief_output.customer_name}\n"
            f"Phone: {brief_output.phone}\n"
            f"Email: {brief_output.email}\n"
            f"Company: {brief_output.company}\n"
            f"Product Interest: {brief_output.product_interest}\n"
            f"Urgency: {brief_output.urgency.upper()}\n"
            f"Estimated Volume: {brief_output.estimated_volume}\n\n"
            f"Executive Brief:\n{brief_output.executive_brief}\n\n"
            f"Recommended Next Step:\n{brief_output.next_step}\n"
        )

        payload = NotificationPayload(
            event_id=event_id,
            channel="webhook" if self.notifier.webhook_url else "log",
            subject=subject,
            body=body,
            metadata=brief_output.model_dump(),
        )

        dispatch_res = self.notifier.dispatch(payload, force=force)
        logger.info(f"Dispatched lead brief #{lead_id}: {dispatch_res.success}")

        return brief_output

    def run(self, limit: int = 10, force: bool = False, specific_lead_id: Optional[int] = None) -> List[LeadBriefOutput]:
        leads = lead_repository.get_leads(limit=limit)
        if specific_lead_id:
            leads = [l for l in leads if str(l.get("lead_id")) == str(specific_lead_id)]

        results = []
        for l in leads:
            try:
                res = self.process_lead(l, force=force)
                if res:
                    results.append(res)
            except Exception as e:
                logger.error(f"Failed processing lead {l.get('lead_id')}: {e}")

        self.runner.finalize()
        return results


def main():
    parser = argparse.ArgumentParser(description="Offline Multi-Agent Lead Executive Brief Job")
    parser.add_argument("--lead-id", type=int, help="Specific lead ID to process")
    parser.add_argument("--limit", type=int, default=10, help="Max leads to process")
    parser.add_argument("--force", action="store_true", help="Force re-dispatch even if already sent")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    job = JobLeadBrief()
    results = job.run(limit=args.limit, force=args.force, specific_lead_id=args.lead_id)
    print(f"Processed {len(results)} lead briefs.")


if __name__ == "__main__":
    main()
