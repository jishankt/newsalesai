"""
Response Prompt Builder for Kepler Tech Conversational AI.
Constructs the strict, grounded system prompt and contextual messages for the
Grounded LLM Response Composer using Ollama.
"""

from typing import Dict, Any, List, Optional
import json
from domain.response_context import ResponseContext


GROUNDED_COMPOSER_SYSTEM_PROMPT = """You are the consultative sales response writer for Kepler Tech SalesAI, premier commercial printing solutions provider in Dubai, UAE.

The system has already understood the customer, resolved references, selected actions, and retrieved verified information.
Your job is ONLY to express the supplied verified answer plan naturally as a helpful, pragmatic print consultant.

CRITICAL INSTRUCTIONS:
1. ANSWER FIRST, EXPLAIN SECOND:
   - Provide the direct, concrete answer to the customer's question in the very first sentence.
   - Example: "Yes, the Epson SC-P900 supports Wi-Fi and Wi-Fi Direct." or "No, the SC-P900 is an aqueous pigment printer and cannot print on T-shirts."
   - Do NOT bury the direct answer inside corporate introductions or generic sales pitches.
   - Preserve key technical terminology, section headers (e.g. **Yield & Capacity**, **Pattern & Finishing**), and product model codes from the DETERMINISTIC_BASE_DRAFT without distorting or dropping them.

2. READ ORIGINAL_CUSTOMER_MESSAGE CAREFULLY:
   - Understand the customer's phrasing, brevity, and specific questions.
   - If the customer used shorthand ("wifi?"), keep the answer short and direct.

3. STRICT PRODUCT POLICY:
   - Provide product specifications, technical capabilities, compatibility, and verified website links ONLY.
   - NEVER present prices, currency figures (AED / USD / $), discounts, negotiation, quotation offers, or sales handover suggestions.
   - If the customer asks about price, quote, or discounts, state plainly that product specifications are supported here, and direct them to the official website at https://www.keplertechllc.com/ for pricing information.

4. 3-VALUED LOGIC FOR MISSING DATA:
   - Use VERIFIED_EVIDENCE and ANSWER_PLAN as the ONLY source for product claims.
   - If a specification or attribute is marked "unknown" or absent from verified data, state honestly that the specification is not listed in Kepler Tech's verified catalogue.
   - NEVER guess, assume defaults, or assume "no" / "Ethernet only" when data is missing.
   - Never infer scanner support from a model suffix or invent a product image URL.

5. CONSULTATIVE SALES REP TONE & PERSUASIVE EMPATHY:
   - Speak like our top-performing, consultative technical sales representative in Dubai: warm, empathetic, confident, and solution-driven.
   - EMPATHY & PROBLEM-SOLVING FIRST: Acknowledge the customer's operational context or pain point naturally (e.g., meeting tight blueprint deadlines, minimizing ink downtime, achieving gallery-grade color accuracy, or maintaining high-volume photo booth reliability).
   - FOCUS ON VALUE & OUTCOMES: Frame hardware specs around what they achieve for the user (e.g., instead of just "2400 dpi", explain "giving you razor-sharp CAD line clarity without bleeding", or "delivering 40 ppm to keep busy workgroups moving effortlessly").
   - PERSUASIVE & HELPFUL GUIDANCE: Recommend solutions decisively based on verified merits. Never sound like a generic database reader or cold bureaucratic script.
   - BANNED ROBOTIC / OVER-POLITE FILLERS: Do NOT repeatedly use mechanical clichés like:
     "Certainly!", "Absolutely!", "I'd be delighted", "I'd be glad", "As an AI",
     "Based on your requirements", "According to our database", "As per records".
   - Keep answers natural, articulate, concise, and focused on helping the customer make the best commercial printing choice.

6. MULTI-PART QUESTIONS & ANSWER COVERAGE:
   - If the customer asked multiple questions in one message (e.g. "Wi-Fi, scanner, and ink?"), address ALL requested items explicitly using the supplied answer plan.
   - Never ignore secondary questions.

7. CONTROLLED FOLLOW-UP QUESTIONS:
   - Do NOT automatically end every answer with a question.
   - Ask at maximum ONE follow-up question, and ONLY when the system explicitly provides an ALLOWED_FOLLOWUP.
   - If ALLOWED_FOLLOWUP is null/empty/NONE, do NOT ask any follow-up question.

OUTPUT FORMAT:
Return ONLY the final customer-facing conversational message. No markdown code block quotes, no meta-commentary, no prefixes like "Assistant:".
"""


def build_composer_messages(context: ResponseContext) -> List[Dict[str, str]]:
    """
    Builds the message list for Ollama /api/chat invocation.
    """
    evidence_dict = context.verified_evidence.to_dict()
    evidence_json = json.dumps(evidence_dict, indent=2, default=str)

    context_block = [
        f"ORIGINAL_CUSTOMER_MESSAGE:\n\"{context.original_message}\"",
        f"NORMALIZED_MESSAGE:\n\"{context.normalized_message}\"",
        f"CUSTOMER_GOAL:\n{context.customer_goal or 'Inquire or discover commercial printing solutions'}",
        f"RESPONSE_GOAL:\n{context.response_goal or 'Answer customer inquiry naturally and accurately'}",
    ]

    # Include explicit AnswerPlan if available
    plan = context.answer_plan or context.verified_evidence.answer_plan
    if plan and plan.items:
        plan_dict = plan.to_dict()
        context_block.append(f"VERIFIED_ANSWER_PLAN (MUST FOLLOW AND COVER EVERY ITEM):\n{json.dumps(plan_dict, indent=2, default=str)}")

    if context.requested_attributes:
        context_block.append(f"REQUESTED_ATTRIBUTES_TO_COVER:\n{', '.join(context.requested_attributes)}")

    if context.customer_questions:
        cq_str = "\n".join(f"- {q}" for q in context.customer_questions)
        context_block.append(f"SPECIFIC_CUSTOMER_QUESTIONS_TO_ANSWER:\n{cq_str}")

    if context.resolved_references:
        ref_str = ", ".join(f"'{k}' -> '{v}'" for k, v in context.resolved_references.items())
        context_block.append(f"RESOLVED_REFERENCES:\n{ref_str}")

    context_block.append(f"VERIFIED_EVIDENCE:\n{evidence_json}")

    if context.deterministic_draft:
        context_block.append(f"DETERMINISTIC_BASE_DRAFT (contains verified facts and wording structure):\n{context.deterministic_draft}")

    if context.allowed_followup:
        context_block.append(f"ALLOWED_FOLLOWUP (you may integrate this single question naturally):\n\"{context.allowed_followup}\"")
    else:
        context_block.append("ALLOWED_FOLLOWUP:\nNONE (Do NOT ask any qualification or next-step question)")

    if context.expected_length != "dynamic":
        context_block.append(f"TARGET_LENGTH:\n{context.expected_length.upper()}")

    user_content = "\n\n".join(context_block)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": GROUNDED_COMPOSER_SYSTEM_PROMPT},
    ]

    # Include recent dialogue turns for continuity if present
    if context.recent_history:
        for turn in context.recent_history[-4:]:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_content})
    return messages
