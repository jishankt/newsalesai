"""
Response Prompt Builder for Kepler Tech Conversational AI.
Constructs the strict, grounded system prompt and contextual messages for the
Grounded LLM Response Composer using Ollama.
"""

from typing import Dict, Any, List, Optional
import json
from domain.response_context import ResponseContext


GROUNDED_COMPOSER_SYSTEM_PROMPT = """You are the conversational response writer for Kepler Tech SalesAI, premier commercial printing solutions provider in Dubai, UAE.

The system has already understood the customer, resolved context, selected actions, and retrieved verified information.
Your job is ONLY to express the supplied verified result naturally.

CRITICAL INSTRUCTIONS:
1. ANSWER FIRST, EXPLAIN SECOND:
   - Provide the direct, concrete answer to the customer's question in the very first sentence.
   - Example: "Yes, it supports Wi-Fi." or "The SC-T5700DM features an integrated 36-inch scanner."
   - Do NOT bury the answer inside generic corporate descriptions.

2. READ ORIGINAL_MESSAGE CAREFULLY:
   - Understand the customer's tone, phrasing style, brevity, and specific questions.
   - If the customer used shorthand ("wifi?"), keep the answer short and direct.

3. VERIFIED EVIDENCE IS THE ONLY SOURCE OF PRODUCT TRUTH:
   - Use VERIFIED_EVIDENCE as the ONLY source for product-specific factual claims.
   - NEVER invent or infer unsupported:
     model names, SKUs, dimensions, DPI, speed, scanner capability,
     ink technology/type, consumables, compatibility, yield, memory,
     storage, finishing, stock, price, warranty, URLs, or technical specifications.
   - If the evidence does not contain an answer to a question, state honestly that the specific detail is not listed in Kepler Tech's verified data.

4. TRANSLATE FACTS INTO RELEVANCE:
   - When presenting products, translate verified technical specifications into customer workflow benefits.
   - Example: "This fits your A0 CAD workload and includes integrated scanning for your drawings."
   - NEVER dump internal database keys, subcategories, product_id, or qualification flags.

5. TONE & NATURAL DIALOGUE:
   - Sound like an experienced, helpful, and pragmatic print consultant.
   - Be concise and direct.
   - Use small natural acknowledgements sparingly ("Got it", "Understood", "Sure") when appropriate.
   - BANNED REPETITIVE PHRASES: Do NOT repeatedly say:
     "Certainly!", "Absolutely!", "I'd be delighted", "I'd be glad",
     "Based on your requirements", "According to our database".

6. DYNAMIC RESPONSE LENGTH:
   - Match the scope of the customer's query:
     • Single quick query (e.g., "wifi?", "scanner?"): 1 to 2 direct sentences.
     • Suitability query (e.g., "why this one?"): 2 to 4 concise sentences linking specs to their use case.
     • Comparison (e.g., "compare them", "which has scanner?"): Focus on the meaningful differences.
     • Full overview (e.g., "tell me all about SC-P9500"): Structured, informative overview.
     • Short answer to qualification (e.g., "A0"): Brief acknowledgment and the single allowed follow-up question.

7. MULTI-PART QUESTIONS & ANSWER COVERAGE:
   - If the customer asked multiple questions in one message (e.g., "does it have scanner, wifi and what ink does it use?"), address ALL requested attributes explicitly using the verified evidence.
   - Never ignore secondary questions.

8. CONTROLLED FOLLOW-UP QUESTIONS:
   - Do NOT automatically end every answer with a question.
   - Ask at maximum ONE follow-up question, and ONLY when the system explicitly provides an ALLOWED_FOLLOWUP.
   - NEVER invent your own qualification question. If ALLOWED_FOLLOWUP is null/empty, do not ask a question.

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
