"""
Commercial Lead Generation & Follow-up Specialist Agent (Agent 4).
Handles pricing disclosure, zero-discount policy enforcement, contact capture
(Name, Company, Email, Phone/WhatsApp), SQLite lead persistence, and quotation follow-ups.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from domain.conversation_types import LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState
from agents.base_agent import BaseSpecialistAgent
from persistence.lead_repository import lead_repository
from guardrails import PRICE_REFUSAL

logger = logging.getLogger("agent.sales_lead")

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:\+?(\d{1,3}))?[-. (]*(\d{2,4})[-. )]*(\d{3,4})[-. ]*(\d{3,4})\b")


class SalesLeadAgent(BaseSpecialistAgent):
    def __init__(self):
        super().__init__(
            agent_id="sales_lead",
            name="Sales & Quotation Specialist",
            role="Quotations & Lead Capture",
            theme_color="#f59e0b",
            badge="💼 Sales & Quotes",
            icon="fas fa-handshake",
        )

    def extract_contact_info(self, text: str) -> Dict[str, Optional[str]]:
        """Extracts email, phone, company, and customer details if present in message."""
        info = {
            "email": None,
            "phone": None,
            "company": None,
            "name": None,
        }

        # 1. Email extraction
        email_match = EMAIL_REGEX.search(text)
        if email_match:
            info["email"] = email_match.group(0)

        # 2. Phone extraction (ensure at least 7 digits to avoid small numbers)
        digits_only = re.sub(r"[^\d+]", "", text)
        if len(re.sub(r"[^\d]", "", digits_only)) >= 7:
            phone_match = PHONE_REGEX.search(text)
            if phone_match:
                info["phone"] = phone_match.group(0).strip()
            elif "+" in text or len(re.sub(r"[^\d]", "", text)) >= 8:
                # Fallback digit extraction
                m = re.search(r"(\+?\d[\d\s\-()]{6,16}\d)", text)
                if m:
                    info["phone"] = m.group(1).strip()

        # 3. Company extraction patterns
        comp_m = re.search(
            r"(?:company|from|firm|studio|agency|business)[:\s]+([A-Za-z0-9\s&'-]{2,35}?)(?=[.,\n]|(?:\s+(?:you|we|my|i|email|phone|call|and|our))\b|$)",
            text,
            re.IGNORECASE,
        )
        if comp_m:
            candidate = comp_m.group(1).strip()
            if candidate.lower().startswith("is "):
                candidate = candidate[3:].strip()
            # Exclude common stop words
            if candidate.lower() not in ["none", "na", "no", "private", "myself", "here", "dubai", "uae"]:
                info["company"] = candidate

        # 4. Name extraction patterns
        name_m = re.search(
            r"(?:my name is|i am|name is|this is|name[:\s]+)\s*([A-Za-z\u0600-\u06FF]+(?:\s+[A-Za-z\u0600-\u06FF]+)?)(?=[.,\n]|(?:\s+(?:from|with|at|and|you|email|phone|mobile|contact))\b|$)",
            text,
            re.IGNORECASE,
        )
        if name_m:
            cand = name_m.group(1).strip()
            if cand.lower() not in ["none", "na", "no", "looking", "interested", "sure", "here"]:
                info["name"] = cand.capitalize() if cand.islower() else cand

        # 5. AI fallback if contact details present but name missing, or if ambiguous
        if not info["name"] or (not info["phone"] and not info["email"]):
            if any(k in text.lower() for k in ["name", "email", "@", "phone", "mobile", "+971", "call", "whatsapp"]):
                try:
                    from ollama_client import ollama_client
                    schema = {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "phone": {"type": "string"},
                            "email": {"type": "string"},
                            "company": {"type": "string"}
                        }
                    }
                    ai_res = ollama_client.classify(
                        messages=[
                            {"role": "system", "content": "Extract customer name, phone, email, and company if mentioned in text."},
                            {"role": "user", "content": text}
                        ],
                        schema=schema,
                        temperature=0.0
                    )
                    if ai_res.get("success") and ai_res.get("result"):
                        res = ai_res["result"]
                        if not info["name"] and res.get("name") and str(res["name"]).strip().lower() not in ("none", "n/a", "unknown", "null"):
                            info["name"] = str(res["name"]).strip()
                        if not info["email"] and res.get("email") and "@" in str(res["email"]):
                            info["email"] = str(res["email"]).strip()
                        if not info["phone"] and res.get("phone"):
                            p = str(res["phone"]).strip()
                            if len(re.sub(r"[^\d]", "", p)) >= 7:
                                info["phone"] = p
                        if not info["company"] and res.get("company") and str(res["company"]).strip().lower() not in ("none", "n/a", "unknown", "null"):
                            info["company"] = str(res["company"]).strip()
                except Exception:
                    pass

        return info

    def handle_turn(
        self,
        raw_message: str,
        normalized_message: str,
        understanding: Optional[LLMUnderstanding],
        state: ConversationState,
        **kwargs,
    ) -> RouteResult:
        logger.info(f"SalesLeadAgent handling message: {normalized_message[:60]}")
        session_id = kwargs.get("session_id", "default_session")
        contacts = self.extract_contact_info(raw_message)

        # Update customer name if detected
        if contacts["name"] and not state.customer_name:
            state.customer_name = contacts["name"]
        elif understanding and understanding.entities.get("customer_name") and not state.customer_name:
            state.customer_name = understanding.entities["customer_name"]

        # Derive active product interest
        product_interest = None
        if state.active_product:
            product_interest = state.active_product.get("name")
        elif state.candidate_products:
            product_interest = state.candidate_products[0].get("name")
        elif state.category:
            product_interest = f"Category: {state.category}"

        has_contact_submission = bool(contacts["email"] or contacts["phone"])

        if has_contact_submission:
            # Persist lead directly to SQLite database
            lead_id = lead_repository.save_lead(
                session_id=session_id,
                customer_name=state.customer_name or contacts["name"],
                company=contacts["company"],
                email=contacts["email"],
                phone=contacts["phone"],
                product_interest=product_interest,
                notes=f"Message: {raw_message}",
            )

            name_part = f", {state.customer_name}" if state.customer_name else ""
            reply_lines = [
                f"Thank you{name_part}! Your quotation request has been registered with our commercial sales team at Kepler Tech LLC (Reference #{lead_id or 'REC'}).",
            ]
            if product_interest:
                reply_lines.append(f"• **Equipment Interest:** {product_interest}")
            if contacts["email"]:
                reply_lines.append(f"• **Email Registered:** {contacts['email']}")
            if contacts["phone"]:
                reply_lines.append(f"• **Phone / WhatsApp:** {contacts['phone']}")
            if contacts["company"]:
                reply_lines.append(f"• **Company:** {contacts['company']}")

            reply_lines.append(
                "\nA dedicated commercial sales representative will contact you shortly with an itemized official quotation including delivery and on-site setup options."
            )
            reply_lines.append("Is there any specific accessory, roll media, or warranty requirement you would like included?")

            return RouteResult(
                reply="\n".join(reply_lines),
                suggested_chips=["Add Spare Inks", "Include Extended AMC", "Request Product Demo", "Office Location"],
                source="agent:sales_lead:lead_captured",
                needs_composition=False,
            )

        # If customer asked for price/quote but didn't provide contact info yet:
        low = normalized_message.lower()
        is_discount = any(k in low for k in ["discount", "deal", "cheaper", "negotiate", "offer", "lowest price", "special price"])

        if is_discount:
            msg = (
                "Kepler Tech LLC operates with a transparent zero-discount policy to ensure all commercial "
                "clients receive genuine manufacturer-backed hardware with official warranty and certified installation.\n\n"
                "To receive our official standard commercial proposal or arrange a formal quote for your company, "
                "please provide your **Company Name**, **Email Address**, and **Phone / WhatsApp Number**."
            )
        else:
            interest_text = f" for **{product_interest}**" if product_interest else ""
            msg = (
                f"To obtain an official commercial quotation{interest_text} with guaranteed manufacturer warranty, "
                "delivery, and installation terms, our sales department can prepare an itemized quote for you.\n\n"
                "Please share your **Company Name**, **Email Address**, and **Phone or WhatsApp Number**, "
                "and a sales specialist will reach out promptly."
            )

        return RouteResult(
            reply=msg,
            suggested_chips=["Share Contact Info", "Office Location", "Delivery Terms", "View Specifications"],
            source="agent:sales_lead:inquiry",
            needs_composition=False,
        )


sales_lead_agent = SalesLeadAgent()
