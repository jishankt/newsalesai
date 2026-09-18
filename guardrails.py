"""
Commercial rules guardrail and response validator.
Directs discount and negotiation queries to the official website and customer support team.
Allows verified official website prices to be communicated while strictly prohibiting
unauthorized discount promises, price bargaining, or budget interrogation.
"""

import re
from typing import Optional, Dict, Any

OFFICIAL_SUPPORT_EMAIL = "sales@keplertech.ae"
OFFICIAL_SUPPORT_PHONE = "+971 4 323 1008"
OFFICIAL_WEBSITE_URL = "https://www.keplertechllc.com/"

DISCOUNT_REFUSAL = (
    "For pricing details, special discounts, bulk promotions, or commercial offers, please check our official website at "
    f"{OFFICIAL_WEBSITE_URL} or contact our customer support team directly at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}.\n\n"
    "I am here to help you with verified technical specifications, model recommendations, and consumable compatibility from our authorized catalogue."
)
PRICE_REFUSAL = DISCOUNT_REFUSAL

GENERAL_PRICE_DIRECT = (
    f"Official pricing for available models and genuine consumables is published on our website at {OFFICIAL_WEBSITE_URL}.\n\n"
    f"For enterprise systems not listed for direct online checkout, please contact our customer support team directly at {OFFICIAL_SUPPORT_EMAIL} or {OFFICIAL_SUPPORT_PHONE}."
)

PRICE_USER_PATTERNS = [
    r"\b(?:how much|prices?|pricing|costs?|rates?|commercial rates?|quotations?|quotes?|charges?|fees?|expensive|cheap|affordable)\b",
    r"[$₹€£]\s*\d+",
    r"\b\d+\s*(?:dollars|bucks|rupees|inr|usd|eur|cents|aed)\b",
    r"\bwhat is the price\b",
    r"\bwhat does it cost\b",
]

DISCOUNT_USER_PATTERNS = [
    r"\b(?:discount|discounts|discounting|bargain|bargaining|coupon|promo|rebate|concession)\b",
    r"\b(?:negotiat\w*|negosition|negotiable)\b",
    r"\b(?:cheaper rate|cheaper price|cheaper|best price|special deal|lower the price|reduce the price|reduce price|price drop)\b",
    r"\b(?:can you give me a discount|any discount|give discount|give me discount|need discount|less price|more discount)\b",
    r"\b(?:can we negotiate|can i negotiate|price negotiation|negotiate price)\b",
    r"\b(?:give me (?:a )?better price|what is your lowest price|lowest price|minimum price)\b",
    r"\b(?:special\s+offers?|promotional\s+offers?|discount\s+offers?|best\s+offers?|bulk\s+offers?|exclusive\s+offers?|any\s+offers?|make\s+an\s+offer)\b",
    r"\b(?:better\s+deals?|good\s+deals?|special\s+deals?|best\s+deals?|any\s+deals?)\b",
    r"\boffers?\s+(?:and|or)\s+discounts?\b",
    r"\bdiscounts?\s+(?:and|or)\s+offers?\b",
    r"\bhave\s+(?:any\s+|an\s+)?offers?\b",
    r"\b(?:an|any)\s+offer\b",
]

DISCOUNT_EXCLUSION_PATTERNS = [
    r"\bhow\s+(?:do\s+)?(?:you|we)\s+offer\b",
    r"\b(?:what|which|models?|printers?|products?)\s+(?:do\s+)?(?:you|we)\s+offer\b",
    r"\boffer\s+(?:against|instead|for\s+this)\b",
    r"\bprinters?\s+you\s+offer\b",
    r"\byou\s+offer\s+(?:against|a3|a4|citizen|epson|photo|printer)\b",
]

PROHIBITED_OUTPUT_PATTERNS = [
    r"\b(?:what is your budget|what's your budget|whats your budget|how much are you looking to spend)\b",
    r"\b(?:i can give you a discount|we can offer you a discount|i can lower the price|we can negotiate)\b",
]

STATIC_SAFE_REFUSAL = (
    "I am unable to verify the requested product details against our official catalogue. "
    "Could you please specify your printing requirements again—such as what you plan to print (technical CAD drawings, office documents, or photos) and your desired print size?"
)


def is_commercial_negated(text: str) -> bool:
    """Check if the user is explicitly asking to exclude commercial/discount/price discussion."""
    if not text:
        return False
    t_lower = text.lower()
    neg_patterns = [
        r"\b(?:without|no|not|excluding|ignore|don't|dont|never|free of)\s+(?:discussing|mentioning|including|talking about|asking for|getting into)?\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?|commercials?)(?:\s*(?:and|or|,)\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?|commercials?))*\b",
        r"\bdo not (?:mention|discuss|include)\s+(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?)(?:\s*(?:and|or|,)\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?))*\b",
    ]
    return any(re.search(p, t_lower) for p in neg_patterns)


def strip_negated_commercial(text: str) -> str:
    """Strips negated commercial phrases from the query to prevent false-positive intercept."""
    if not text:
        return ""
    neg_patterns = [
        r"\b(?:without|no|not|excluding|ignore|don't|dont|never|free of)\s+(?:discussing|mentioning|including|talking about|asking for|getting into)?\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?|commercials?)(?:\s*(?:and|or|,)\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?|commercials?))*\b",
        r"\bdo not (?:mention|discuss|include)\s+(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?)(?:\s*(?:and|or|,)\s*(?:prices?|discounts?|costs?|rates?|pricing|quotations?|quotes?))*\b",
    ]
    cleaned = text
    for p in neg_patterns:
        cleaned = re.sub(p, " ", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def is_discount_inquiry(user_message: str) -> bool:
    """Checks if the user message asks for discounts, bargaining, or price negotiations."""
    if not user_message:
        return False
    clean_msg = strip_negated_commercial(user_message.lower().strip())
    if any(re.search(p, clean_msg) for p in DISCOUNT_EXCLUSION_PATTERNS):
        return False
    return any(re.search(p, clean_msg) for p in DISCOUNT_USER_PATTERNS)


def is_price_inquiry(user_message: str) -> bool:
    """Checks if the user message asks about product pricing or cost."""
    if not user_message:
        return False
    clean_msg = strip_negated_commercial(user_message.lower().strip())
    return any(re.search(p, clean_msg) for p in PRICE_USER_PATTERNS)


def check_user_intent_for_pricing_or_discount(user_message: str) -> Optional[str]:
    """
    Checks if the user message asks for discounts, bargaining, or negotiations.
    Discounts return DISCOUNT_REFUSAL.
    Pure price inquiries without discount negotiation return None so they can be
    handled dynamically with website prices or support referral.
    """
    if is_discount_inquiry(user_message):
        return DISCOUNT_REFUSAL
    return None


def format_product_price_response(prod: Dict[str, Any], price_info: Dict[str, Any]) -> str:
    """Formats an official pricing response for a catalogue product."""
    name = prod.get("display_name") or prod.get("name") or prod.get("model") or prod.get("title") or "Product"
    url = price_info.get("url") or prod.get("website_url") or prod.get("product_url") or OFFICIAL_WEBSITE_URL

    if not price_info.get("is_request") and price_info.get("price"):
        price_str = price_info.get("price_str") or f"AED {price_info['price']:,.2f}"
        vat = price_info.get("vat_note") or "(Excl. VAT)"
        return (
            f"The official price for the **{name}** on our website is **{price_str} {vat}**.\n\n"
            f"You can view complete product specifications or purchase directly on our website at {url}.\n\n"
            "Would you like details on compatible consumables or technical specifications?"
        )
    else:
        return (
            f"The **{name}** is an enterprise/large-format production system and its price is not listed for direct online checkout on our website.\n\n"
            f"Please contact our customer support and sales team directly at **{OFFICIAL_SUPPORT_EMAIL}** or **{OFFICIAL_SUPPORT_PHONE}** to receive an official commercial quotation and check availability."
        )


def validate_and_sanitize_response(response_text: str, user_message: str) -> str:
    """
    Validates model output against strict commercial rules.
    Guarantees zero unauthorized discount promises and no budget queries.
    Preserves authorized Kepler Tech customer support contact details and official website URLs.
    """
    if not response_text:
        return "I am here to help. Could you tell me what type of product or service you're looking for?"

    text = response_text.strip()

    # Remove internal reasoning blocks or markdown artifacts if emitted
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```[a-zA-Z]*\n?.*?\n?```", "", text, flags=re.DOTALL)

    # Check if user explicitly asked for discounts or negotiations
    clean_user_msg = strip_negated_commercial(user_message.lower().strip())
    if is_discount_inquiry(clean_user_msg):
        return DISCOUNT_REFUSAL

    # If user explicitly specified not to discuss price or discounts, scrub commercial terms
    if is_commercial_negated(user_message):
        text = re.sub(r"(?i)[^.!?\n]*\b(?:discount|discounts|pricing policy|zero-discount|quotation|quote|rate|rates|pricing)\b[^.!?\n]*[.!?]?", "", text)

    # Check if model asked about budget
    if re.search(r"\b(?:budget|how much are you willing to spend)\b", text, re.IGNORECASE):
        text = re.sub(
            r"(?i)[^.!?]*\bbudget\b[^.!?]*[.!?]?",
            "What specific features or volume requirements do you have?",
            text
        )

    # Clean unauthorized handover patterns, but preserve authorized Kepler Tech support contacts
    # Protect authorized contacts:
    placeholders = {
        "__KEPLER_EMAIL__": OFFICIAL_SUPPORT_EMAIL,
        "__KEPLER_PHONE__": OFFICIAL_SUPPORT_PHONE,
        "__KEPLER_WEB__": OFFICIAL_WEBSITE_URL,
    }
    for placeholder, val in placeholders.items():
        text = text.replace(val, placeholder)

    # Scrub other arbitrary emails
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", text)

    # Scrub other arbitrary phone numbers (international formats not matching placeholder)
    text = re.sub(
        r"(?<![\w.])\+\d{1,3}[\s\-]?\d{1,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}(?![\w])",
        "",
        text
    )

    # Restore authorized contacts
    for placeholder, val in placeholders.items():
        text = text.replace(placeholder, val)

    # Remove internal grounding/audit tags
    text = re.sub(r"\s*\[(?:VERIFIED|CONFLICT|INFERRED|CALCULATED)[^\]]*\]", "", text)

    # Clean whitespace
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return "Could you tell me a little more about the specific requirements you have in mind?"

    return text
