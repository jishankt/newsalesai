"""
Customer Onboarding, Consent, and Chat History Flow Handler.
Handles:
1. Opt-in inquiry ("Are you interested in sharing your name and contact details?").
   - If user says NO -> mark declined, never trigger again.
2. If YES -> ask for Name and Phone Number or Email ID.
3. Once details received -> ask if they want to continue with chat history
   (Username = Name, Password = Phone/Email).
   - If user says NO -> "further chat don't do anything" (do not create account/credentials, continue as guest).
   - If user says YES -> create customer profile, link session, enable credentials.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple
from domain.conversation_state import ConversationState
from persistence.customer_repository import customer_repository
from persistence.lead_repository import lead_repository
from agents.sales_lead_agent import sales_lead_agent

logger = logging.getLogger("conversation.customer_flow")

SUBSTANTIVE_QUERY_RE = re.compile(
    r"\b(?:need|want|looking|search|show|find|recommend|buy|purchase|price|cost|quote|spec|specs|specification|datasheet|compare|difference|support|printer|plotter|scanner|copier|mfp|ink|toner|cartridge|ribbon|roll|paper|a3|a4|cad|photo|sublimation|surecolor|workforce|ecotank|expression|label|hybrid|flatbed|adf|speed|ppm|dpi)\b",
    re.IGNORECASE
)

NEGATIVE_PATTERNS = [
    r"^(?:no|nope|nah|not\s+really|not\s+interested|no\s+thanks?|no\s+thank\s+you|don['']?t\s+want(?:(?:\s+to)?(?:\s+share)?(?:\s+save)?)?|never\s*mind|skip|not\s+now|maybe\s+later|later|refuse|decline|no\s+need|continue\s+as\s+guest|guest|don['']?t\s+save|without\s+saving|don['']?t\s+do\s+anything|stop)[.!?, ]*$"
]

POSITIVE_PATTERNS = [
    r"^(?:yes|yeah|yep|sure|ok|okay|of\s*course|definitely|certainly|i['']?m\s+interested|yes\s+please|yes\s+i\s+am|save\s+it|save\s+chat|enable|enable\s+history|save\s+chat\s+history|yes\s+save)[.!?, ]*$"
]


def is_negative_response(text: str) -> bool:
    """Checks if text expresses refusal/decline without substantive product intent."""
    t = text.strip().lower()
    if SUBSTANTIVE_QUERY_RE.search(t):
        return False
    bare_negatives = {
        "no", "no.", "no!", "n", "nope", "nah", "no thanks", "no thank you",
        "skip", "not now", "maybe later", "later", "no, continue as guest",
        "continue as guest", "guest", "don't save", "dont save", "without saving",
        "don't do anything", "dont do anything", "not interested", "not really",
        "never mind", "nevermind", "stop", "refuse", "decline", "no need"
    }
    cleaned = re.sub(r"[^\w\s]", "", t).strip()
    if cleaned in bare_negatives or t in bare_negatives:
        return True
    return any(re.search(pat, t) for pat in NEGATIVE_PATTERNS)


def is_positive_response(text: str) -> bool:
    """Checks if text expresses consent/agreement without substantive product intent."""
    t = text.strip().lower()
    if SUBSTANTIVE_QUERY_RE.search(t):
        return False
    bare_positives = {
        "yes", "yes.", "yes!", "y", "sure", "ok", "okay", "yep", "yeah",
        "yes, i'm interested", "yes, save chat history"
    }
    cleaned = re.sub(r"[^\w\s]", "", t).strip()
    if cleaned in bare_positives or t in bare_positives:
        return True
    return any(re.search(pat, t) for pat in POSITIVE_PATTERNS)


STOP_WORDS = {
    "and", "my", "mobile", "phone", "number", "email", "is", "am", "the", "whatsapp",
    "contact", "here", "call", "at", "from", "with", "me", "hi", "hello", "hey",
    "dear", "mr", "mrs", "ms", "it",
    "و", "في", "من", "على", "رقم", "رقمي", "ورقمي", "هاتف", "هاتفي", "وهاتفي",
    "موبايل", "جوال", "ايميل", "بريد", "البريد", "إيميل", "واتساب"
}

NAME_TOKEN_REGEX = re.compile(
    r"^[a-zA-Z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
    r"(?:['’\-][a-zA-Z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*$"
)


def format_name_token(token: str) -> str:
    """Properly capitalizes Latin tokens while preserving Arabic script and internal punctuation."""
    if token.islower() and re.search(r"[a-z]", token):
        return re.sub(r"[a-z]+", lambda m: m.group(0).capitalize(), token)
    return token


def extract_full_name(text: str, email: Optional[str] = None, phone: Optional[str] = None) -> Optional[str]:
    """
    Extracts customer full name:
    - Takes up to 4 alphabetic tokens (allows Arabic script, hyphens, apostrophes)
    - Stops at stop-words (and, my, mobile, phone, number, email, is, am, the, whatsapp, etc.)
    - Stops at any digit or '@'
    """
    clean = text
    intro_match = re.search(
        r"\b(?:my\s+name\s+is|i['’]?m|i\s+am|name\s+is|this\s+is|اسمي|أنا)\b[:\s]*",
        clean,
        re.IGNORECASE
    )
    if intro_match:
        sub = clean[intro_match.end():]
    else:
        sub = clean
        if email:
            sub = sub.replace(email, " ")
        if phone:
            sub = sub.replace(phone, " ")

    tokens = []
    raw_tokens = sub.split()
    for raw in raw_tokens:
        tok = raw.strip("\"'`()[]{}")
        # Stop at digit or @
        if "@" in tok or any(c.isdigit() for c in tok):
            break
        # Strip trailing punctuation
        tok = re.sub(r"[,.:;!?]+$", "", tok)
        if not tok:
            continue
        # Stop at stop-word
        if tok.lower() in STOP_WORDS:
            break
        # Check token validity
        if not NAME_TOKEN_REGEX.match(tok):
            break
        tokens.append(format_name_token(tok))
        if len(tokens) == 4:
            break

    if not tokens:
        return None
    return " ".join(tokens)


def extract_name_and_contact(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extracts (name, contact, phone, email) from input text.
    Uses robust full-name extraction supporting up to 4 tokens (Arabic, hyphens, apostrophes).
    """
    contact_info = sales_lead_agent.extract_contact_info(text)
    email = contact_info.get("email")
    phone = contact_info.get("phone")
    contact = email or phone

    name = extract_full_name(text, email=email, phone=phone)
    if not name:
        name = contact_info.get("name")

    return name, contact, phone, email


def mask_contact(contact: str) -> str:
    """Masks phone number or email for safe display."""
    if not contact:
        return ""
    if "@" in contact:
        parts = contact.split("@")
        user = parts[0]
        domain = parts[1] if len(parts) > 1 else ""
        masked_user = user[0] + "***" + (user[-1] if len(user) > 2 else "")
        return f"{masked_user}@{domain}"
    digits = re.sub(r"[^\d+]", "", contact)
    if digits.startswith("+971") and len(digits) >= 12:
        return f"+971 ** *** {digits[-4:]}"
    elif len(digits) >= 7:
        prefix = digits[:4] if digits.startswith("+") else digits[:3]
        suffix = digits[-4:]
        return f"{prefix} ** *** {suffix}"
    return "****"


def handle_customer_onboarding(
    raw_message: str,
    normalized_msg: str,
    state: ConversationState,
    session_id: str
) -> Optional[Dict[str, Any]]:
    """
    Checks and advances customer onboarding state if currently in an active step.
    Returns response dict if handled, or None if normal conversation should proceed.
    """
    import config
    if not getattr(config, "CUSTOMER_LOGIN_ENABLED", False):
        return None

    status = state.lead_prompt_status

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: User was asked "Are you interested in sharing your name and details?"
    # ─────────────────────────────────────────────────────────────────────────
    if status == "offered_opt_in":
        if is_negative_response(raw_message):
            state.lead_prompt_status = "declined_opt_in"
            logger.info(f"[{session_id[:8]}] Customer declined sharing contact details.")
            reply = (
                "No problem at all! We respect your privacy. Let's continue without saving any personal information.\n\n"
                "What type of printing equipment, specifications, or consumables can I assist you with today?"
            )
            return {
                "reply": reply,
                "source": "customer_flow:declined_opt_in",
                "suggested_chips": ["Office & Business Printers", "Technical CAD Plotters", "Consumables & Inks"],
                "active_agent": "Front Desk"
            }

        if is_positive_response(raw_message):
            # Check if user also provided their details in the same message
            name, contact, phone, email = extract_name_and_contact(raw_message)
            if contact:
                # User gave details right away! Advance to history save offer
                return _process_contact_submission(raw_message, name, contact, phone, email, state, session_id)

            state.lead_prompt_status = "awaiting_details"
            logger.info(f"[{session_id[:8]}] Customer agreed to share contact details.")
            reply = "Wonderful! Could you please share your **Name** and your **Phone Number or Email ID**?"
            return {
                "reply": reply,
                "source": "customer_flow:awaiting_details",
                "suggested_chips": [],
                "active_agent": "Front Desk"
            }

        # If user typed something unrelated (e.g. asked a printer question instead),
        # check if it contains contact details anyway
        name, contact, phone, email = extract_name_and_contact(raw_message)
        if contact:
            return _process_contact_submission(raw_message, name, contact, phone, email, state, session_id)

        # User neither said yes/no nor gave details; treat as not interested for now so we don't trap them
        state.lead_prompt_status = "declined_opt_in"
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: Assistant is waiting for Name and Phone/Email
    # ─────────────────────────────────────────────────────────────────────────
    if status == "awaiting_details":
        if is_negative_response(raw_message):
            state.lead_prompt_status = "declined_opt_in"
            logger.info(f"[{session_id[:8]}] Customer changed mind and declined sharing details.")
            reply = (
                "No problem at all! We'll continue without saving any details.\n\n"
                "How else can I assist with your printing requirements today?"
            )
            return {
                "reply": reply,
                "source": "customer_flow:declined_details",
                "suggested_chips": ["Office & Business Printers", "Technical CAD Plotters", "Consumables & Inks"],
                "active_agent": "Front Desk"
            }

        name, contact, phone, email = extract_name_and_contact(raw_message)
        if contact:
            return _process_contact_submission(raw_message, name, contact, phone, email, state, session_id)

        # If user changed subject to a product query or gave a substantive requirement,
        # don't mistakenly treat their question as a person name! Abort details and fall through to orchestrator.
        if SUBSTANTIVE_QUERY_RE.search(raw_message):
            state.lead_prompt_status = "declined_opt_in"
            logger.info(f"[{session_id[:8]}] Customer changed subject to product query during details collection.")
            return None

        # User gave something without phone or email
        if name and not state.customer_name:
            state.customer_name = name

        reply = (
            "Thank you! Could you also provide your **Phone Number** (e.g. +971 50 123 4567) or **Email ID**?\n"
            "This ensures we can register your quotation request and enable chat history if you'd like."
        )
        return {
            "reply": reply,
            "source": "customer_flow:awaiting_contact_retry",
            "suggested_chips": ["No, continue as guest"],
            "active_agent": "Front Desk"
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3: Details captured; asking if user wants to continue with chat history
    # ─────────────────────────────────────────────────────────────────────────
    if status == "offered_history_save":
        if is_negative_response(raw_message):
            state.lead_prompt_status = "declined_history"
            logger.info(f"[{session_id[:8]}] Customer declined chat history save. Keeping as guest.")
            reply = (
                "Understood! We won't create a login account or store this chat in history. "
                "We can continue right here as a guest.\n\n"
                "What would you like to explore next?"
            )
            return {
                "reply": reply,
                "source": "customer_flow:declined_history",
                "suggested_chips": ["Recommended Printers", "Check Inks & Media", "Technical Specifications"],
                "active_agent": "Front Desk"
            }

        if is_positive_response(raw_message):
            state.lead_prompt_status = "history_enabled"
            name = state.customer_name or "Valued Customer"
            contact = state.customer_phone_or_email or "your phone/email"

            # Create or update customer record in database
            customer = customer_repository.create_or_update_customer(
                name=name,
                contact=contact
            )
            state.customer_id = customer.customer_id
            customer_repository.link_session(session_id, customer.customer_id, customer.display_name)
            logger.info(f"[{session_id[:8]}] Customer account activated (id={customer.customer_id})")

            reply = (
                f"🎉 Excellent! Your chat history is now saved and active.\n\n"
                f"You can log in anytime using the **Login** button at the top with:\n"
                f"• **Username:** **{customer.display_name}**\n"
                f"• **Password:** The phone number or email you shared with us\n\n"
                f"Your conversations, recommended configurations, and quote references will be preserved for your next visit. "
                f"What equipment or supplies would you like to review now?"
            )
            return {
                "reply": reply,
                "source": "customer_flow:history_enabled",
                "suggested_chips": ["Recommended Printers", "Consumables & Inks", "Talk to Sales Specialist"],
                "active_agent": "Front Desk"
            }

        # If user asked a new question instead of answering yes/no, mark as declined_history so we don't trap them
        state.lead_prompt_status = "declined_history"
        return None

    return None


def _process_contact_submission(
    raw_message: str,
    name: Optional[str],
    contact: str,
    phone: Optional[str],
    email: Optional[str],
    state: ConversationState,
    session_id: str
) -> Dict[str, Any]:
    """Helper to register lead and transition to history continuation inquiry."""
    final_name = name or state.customer_name or "Guest"
    state.customer_name = final_name
    state.customer_phone_or_email = contact

    # Save to commercial_leads table for sales tracking
    try:
        product_interest = None
        if state.active_product:
            product_interest = state.active_product.get("name")
        elif state.candidate_products:
            product_interest = state.candidate_products[0].get("name")
        elif state.category:
            product_interest = f"Category: {state.category}"

        lead_repository.save_lead(
            session_id=session_id,
            customer_name=final_name,
            company=None,
            email=email or (contact if "@" in contact else None),
            phone=phone or (contact if "@" not in contact else None),
            product_interest=product_interest,
            notes=f"Customer details shared during chat: {raw_message}"
        )
    except Exception as e:
        logger.warning(f"Could not persist commercial lead: {e}")

    state.lead_prompt_status = "offered_history_save"
    logger.info(f"[{session_id[:8]}] Details captured for session. Prompting history save.")

    masked = mask_contact(contact)
    reply = (
        f"Thank you, **{final_name}**! I have noted your contact details ({masked}).\n\n"
        f"Would you like to save this conversation so you can continue your chat history anytime?\n\n"
        f"*(If enabled, you can easily log in whenever you return using your name as username and the phone number or email you shared as password).* "
        f"Would you like to enable chat history?"
    )
    return {
        "reply": reply,
        "source": "customer_flow:offered_history_save",
        "suggested_chips": ["Yes, save chat history", "No, continue as guest"],
        "active_agent": "Front Desk"
    }


def should_trigger_opt_in_prompt(state: ConversationState) -> bool:
    """
    Determines if it's the right moment during normal chatting to ask the initial opt-in question.
    Only triggers if:
    - Customer is not already logged in
    - Opt-in has not been offered or declined before
    - At least 1 turn has occurred (customer has interacted)
    """
    import config
    if not getattr(config, "CUSTOMER_LOGIN_ENABLED", False):
        return False
    if state.customer_id:
        return False
    if state.lead_prompt_status is not None:
        return False
    # Check turn count: at turn 1 or 2 of normal conversation
    turns = state.turn_count or len(state.history_turns) // 2
    return turns >= 1
