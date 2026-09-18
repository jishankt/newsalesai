"""
Business Info Route for Kepler Tech Conversational AI.
Returns verified business information deterministically — no LLM needed.
"""

from domain.conversation_types import LLMUnderstanding, RouteResult
from domain.conversation_state import ConversationState


# Verified information from https://www.keplertechllc.com/
_BUSINESS_INFO = {
    "hours": "Our office is open Monday through Friday from 8:30 AM to 5:30 PM, and Saturday from 8:30 AM to 1:00 PM (closed on Sunday).",
    "location": "We are located at D79, Khalid Bin Waleed Road, Office No. 1, Abdulla Al Awar Building, Dubai, UAE. We provide fast delivery across the UAE and Middle East.",
    "contact": "You can reach our team at +971 4 323 1008 or +971 55 835 8586, and by email at info@keplertech.ae or sales@keplertech.ae.",
    "delivery": "Yes, Kepler Tech LLC provides fast delivery and certified on-site installation across Dubai, all emirates of the UAE, and the wider Middle East.",
    "warranty": "All new printers supplied by Kepler Tech LLC include an official 1-Year On-Site Manufacturer Warranty covering genuine parts, printheads, and certified technician labor across the UAE. We also offer optional CoverPlus extended warranties (up to 3 or 5 years) and comprehensive Annual Maintenance Contracts (AMC).",
    "services": "Our certified services include hardware delivery, professional on-site installation, operator training, manufacturer warranty support, and Annual Maintenance Contracts (AMC).",
    "brands": "Kepler Tech LLC is an authorized partner and distributor for Epson (Large Format CAD, Photo & Office printers, scanners), Citizen (dye-sublimation photo printers), Innova Art (fine art media), Olmec, and Mirage RIP software."
}


def handle(understanding: LLMUnderstanding, state: ConversationState,
           raw_message: str = "") -> RouteResult:
    """Return verified business information."""
    low = raw_message.lower()

    if any(k in low for k in ["warranty", "guarantee", "coverplus"]):
        reply = _BUSINESS_INFO["warranty"]
    elif any(k in low for k in ["deliver", "shipping", "ship", "transport"]):
        reply = _BUSINESS_INFO["delivery"]
    elif any(k in low for k in ["service", "installation", "install", "training", "amc", "maintenance contract"]):
        reply = _BUSINESS_INFO["services"]
    elif any(k in low for k in ["brand", "company", "companies", "partner", "distributor"]):
        reply = _BUSINESS_INFO["brands"]
    elif any(k in low for k in ["hour", "time", "timing", "open", "working", "schedule"]):
        reply = _BUSINESS_INFO["hours"]
    elif any(k in low for k in ["where", "location", "address", "dubai", "office", "direction"]):
        reply = _BUSINESS_INFO["location"]
    elif any(k in low for k in ["phone", "call", "contact", "email", "whatsapp", "mobile"]):
        reply = _BUSINESS_INFO["contact"]
    else:
        reply = f"{_BUSINESS_INFO['hours']} {_BUSINESS_INFO['location']} {_BUSINESS_INFO['contact']}"

    return RouteResult(
        reply=reply,
        suggested_chips=[],
        source="route:business_info",
    )
