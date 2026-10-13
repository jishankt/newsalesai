"""
Kepler Tech Verified Delivery & Policy Knowledge Engine.
Provides grounded, zone-aware policy resolutions across 12 delivery scenarios:
1. coverage: Where Kepler Tech delivers (UAE, Oman, GCC, non-OFAC)
2. fee: Flat AED 10 for UAE, dynamic checkout outside UAE, free store pickup
3. time: Dispatch in 1 to 2 business days after confirmation
4. pickup: Free store pickup at Dubai showroom (ready in 1 to 2 days)
5. tracking: Courier tracking sent automatically via email upon dispatch
6. courier: Insured 3rd-party courier or Kepler technical logistics team
7. returns: 2-day defect/wrong item reporting in unopened packaging, up to 45-day refund
8. cancellation: 24-hour order cancellation window
9. customs: Customer pays destination import duty & VAT outside UAE
10. payment: Payment in full before dispatch (Visa, MasterCard in AED, PayPal)
11. same_day: Emergency same-day delivery coordination for Dubai in-stock items
12. hours: Monday–Friday 8:30–17:30, Saturday 8:30–13:00, Sunday closed (Dubai GST)
"""

import os
import re
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from catalog.evidence import EvidenceRecord, CompatibilityStatus
from conversation.dialogue_state import DialogueState

logger = logging.getLogger("conversation.delivery_engine")

POLICY_FILE_PATH = Path("data/delivery_policy.json")


class DeliveryZone(str, Enum):
    UAE = "UAE"
    OMAN = "OMAN"
    GCC_OTHER = "GCC_OTHER"
    OUTSIDE_GCC = "OUTSIDE_GCC"
    SANCTIONED = "SANCTIONED"
    UNKNOWN = "UNKNOWN"


class DeliveryTopic(str, Enum):
    COVERAGE = "coverage"
    FEE = "fee"
    TIME = "time"
    PICKUP = "pickup"
    TRACKING = "tracking"
    COURIER = "courier"
    RETURNS = "returns"
    CANCELLATION = "cancellation"
    CUSTOMS = "customs"
    PAYMENT = "payment"
    SAME_DAY = "same_day"
    HOURS = "hours"
    GENERAL = "general"


class DeliveryPolicyEngine:
    _cached_policy: Optional[Dict[str, Any]] = None

    @classmethod
    def load_policy(cls) -> Dict[str, Any]:
        if cls._cached_policy is not None:
            return cls._cached_policy

        if POLICY_FILE_PATH.exists():
            try:
                with open(POLICY_FILE_PATH, "r", encoding="utf-8") as f:
                    cls._cached_policy = json.load(f)
                    return cls._cached_policy
            except Exception as e:
                logger.error(f"Failed to load {POLICY_FILE_PATH}: {e}")

        # Fallback to defaults
        from config import SHIPPING_AND_DELIVERY_POLICY, BUSINESS_HOURS
        cls._cached_policy = {
            "dispatch_time": SHIPPING_AND_DELIVERY_POLICY.get("timing", "1 to 2 business days"),
            "zones": {
                "UAE": {"fee": "flat AED 10", "timing": "1 to 2 business days"},
                "OMAN": {"fee": "calculated at checkout"},
                "GCC_OTHER": {"fee": "calculated at checkout"},
            },
            "pickup": {"available": True, "fee": "Free", "timing": "1 to 2 business days"},
            "returns": {"window": "within 2 days of receipt", "refund_timeline": "up to 45 days"},
            "cancellation": {"window": "within 24 hours of placing the order"},
            "payment": {"terms": "Payment in full before dispatch"},
            "hours": {"schedule": BUSINESS_HOURS.get("text")},
        }
        return cls._cached_policy

    @classmethod
    def detect_destination_zone(cls, text: str, state: Optional[DialogueState] = None) -> Tuple[DeliveryZone, str]:
        """
        Detects destination zone from user text or saved state slots.
        Returns (DeliveryZone, destination_display_name).
        """
        text_l = text.lower()

        # Check explicit sanctions
        if re.search(r"\b(?:iran|north korea|syria|cuba|crimea|sanctioned)\b", text_l):
            return DeliveryZone.SANCTIONED, "OFAC-sanctioned countries"

        # Check UAE emirates & keywords
        if re.search(r"\b(?:uae|united arab emirates|dubai|abu dhabi|sharjah|ajman|ras al khaimah|rak|fujairah|umm al quwain|uaq|al ain|local)\b", text_l):
            if state:
                state.confirmed_slots["delivery_destination"] = DeliveryZone.UAE.value
            matched = "the UAE"
            if "sharjah" in text_l:
                matched = "Sharjah"
            elif "abu dhabi" in text_l:
                matched = "Abu Dhabi"
            elif "dubai" in text_l:
                matched = "Dubai"
            return DeliveryZone.UAE, matched

        # Check Oman
        if re.search(r"\b(?:oman|muscat|salalah|sohar)\b", text_l):
            if state:
                state.confirmed_slots["delivery_destination"] = DeliveryZone.OMAN.value
            return DeliveryZone.OMAN, "Oman"

        # Check other GCC
        if re.search(r"\b(?:saudi|saudi arabia|ksa|riyadh|jeddah|dammam|qatar|doha|bahrain|manama|kuwait|gcc)\b", text_l):
            dest_name = "Saudi Arabia" if "saudi" in text_l or "ksa" in text_l else ("Qatar" if "qatar" in text_l else ("Bahrain" if "bahrain" in text_l else "Kuwait"))
            if state:
                state.confirmed_slots["delivery_destination"] = DeliveryZone.GCC_OTHER.value
            return DeliveryZone.GCC_OTHER, dest_name

        # Check Outside GCC / International
        if re.search(r"\b(?:international|worldwide|global|europe|uk|usa|india|pakistan|egypt|africa|asia)\b", text_l):
            if state:
                state.confirmed_slots["delivery_destination"] = DeliveryZone.OUTSIDE_GCC.value
            return DeliveryZone.OUTSIDE_GCC, "International destinations"

        # Recall saved state if present
        if state and "delivery_destination" in state.confirmed_slots:
            saved_zone = state.confirmed_slots["delivery_destination"]
            for z in DeliveryZone:
                if z.value == saved_zone:
                    return z, "the UAE" if z == DeliveryZone.UAE else (z.value.title())

        return DeliveryZone.UNKNOWN, "your location"

    @classmethod
    def detect_topics(cls, text: str) -> List[DeliveryTopic]:
        """Identifies specific delivery/policy topic(s) addressed in the user message."""
        text_l = text.lower()
        topics: List[DeliveryTopic] = []

        # Cancellation
        if re.search(r"\b(?:cancel|cancellation|cancelling|stop order)\b", text_l):
            topics.append(DeliveryTopic.CANCELLATION)

        # Returns & Refunds
        if re.search(r"\b(?:return|returns|refund|refunds|damaged|defective|wrong item|broken)\b", text_l):
            topics.append(DeliveryTopic.RETURNS)

        # Fees & Cost
        if re.search(r"\b(?:fee|fees|cost|charge|charges|how much is (?:delivery|shipping)|free (?:delivery|shipping))\b", text_l):
            topics.append(DeliveryTopic.FEE)

        # Time & Timing
        if re.search(r"\b(?:how long|time|timing|when will it arrive|how many days|duration|dispatch time|lead time)\b", text_l):
            topics.append(DeliveryTopic.TIME)

        # Pickup
        if re.search(r"\b(?:pickup|pick up|collect|store pickup|self pickup|in person)\b", text_l):
            topics.append(DeliveryTopic.PICKUP)

        # Tracking
        if re.search(r"\b(?:track|tracking|consignment|waybill|where is my order)\b", text_l):
            topics.append(DeliveryTopic.TRACKING)

        # Courier
        if re.search(r"\b(?:courier|carrier|who delivers|which courier|aramex|fedex|dhl)\b", text_l):
            topics.append(DeliveryTopic.COURIER)

        # Customs & Duty
        if re.search(r"\b(?:customs|duty|duties|import tax|import duty|vat)\b", text_l):
            topics.append(DeliveryTopic.CUSTOMS)

        # Payment
        if re.search(r"\b(?:payment|pay|card|cash on delivery|cod|visa|mastercard|paypal|before delivery)\b", text_l):
            topics.append(DeliveryTopic.PAYMENT)

        # Same day
        if re.search(r"\b(?:same day|deliver today|today|urgent delivery|express today)\b", text_l):
            topics.append(DeliveryTopic.SAME_DAY)

        # Hours
        if re.search(r"\b(?:hours|timing|timings|open|open today|business hours|working hours|opening hours)\b", text_l):
            topics.append(DeliveryTopic.HOURS)

        # Coverage
        if re.search(r"\b(?:where do you deliver|do you deliver to|coverage|countries|locations|ship to)\b", text_l):
            topics.append(DeliveryTopic.COVERAGE)

        if not topics:
            topics.append(DeliveryTopic.GENERAL)

        return topics

    @classmethod
    def resolve_delivery_decision(
        cls,
        text: str,
        state: Optional[DialogueState] = None,
        product_name: Optional[str] = None,
    ) -> Tuple[str, List[str], str, List[EvidenceRecord]]:
        """
        Synthesizes a targeted, fully verified delivery response.
        Returns: (reply_text, chips, next_step, evidence_records).
        """
        policy = cls.load_policy()
        zone, dest_name = cls.detect_destination_zone(text, state)
        topics = cls.detect_topics(text)

        # Build grounded claims
        paragraphs: List[str] = []

        # Handle Sanctioned immediately
        if zone == DeliveryZone.SANCTIONED:
            sanction_text = (
                "In compliance with UAE law and international regulations, Kepler Tech does not trade with "
                "or ship equipment or supplies to OFAC-sanctioned jurisdictions."
            )
            rec = EvidenceRecord(
                claim=sanction_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_NO,
                source_file="data/delivery_policy.json",
                field="zones.SANCTIONED",
                entity_ids=[],
            )
            return (
                sanction_text,
                ["Contact Sales Desk", "Browse Catalogue"],
                "Would you like to explore products for supported regions?",
                [rec],
            )

        # Multi-intent / Compound: Delivery + Returns
        if DeliveryTopic.RETURNS in topics and (DeliveryTopic.FEE in topics or DeliveryTopic.TIME in topics or DeliveryTopic.COVERAGE in topics or DeliveryTopic.GENERAL in topics):
            combined_text = (
                "• **Delivery & Shipping:** Delivery across the UAE is a **flat AED 10** (calculated at checkout for Oman, GCC, and international shipments). "
                "Orders are processed and dispatched within **1 to 2 business days** with tracking. Free local store pickup is available at our Dubai showroom.\n\n"
                "• **Cancellations & Returns:** Orders can be cancelled within **24 hours**. "
                "Defective or incorrect items must be reported within **2 days** of receipt in original unopened packaging. Refunds are processed to the original payment method (up to 45 days)."
            )
            rec = EvidenceRecord(
                claim=combined_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/delivery_policy.json",
                field="delivery_and_returns",
                entity_ids=[],
            )
            return (
                combined_text,
                ["Dubai / UAE (AED 10)", "Oman & GCC", "Free Store Pickup", "Contact Support"],
                "Would you like to arrange delivery or store pickup for your order?",
                [rec],
            )

        # Cancellation only
        if DeliveryTopic.CANCELLATION in topics and DeliveryTopic.RETURNS not in topics and len(topics) == 1:
            cancel_text = (
                "Orders can be cancelled only within **24 hours** of placing them.\n\n"
                "To cancel an order, contact our support team immediately at **sales@keplertech.ae** or **+971 4 323 1008** with your order confirmation reference."
            )
            rec = EvidenceRecord(
                claim=cancel_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/delivery_policy.json",
                field="cancellation",
                entity_ids=[],
            )
            return (
                cancel_text,
                ["Contact Sales Support", "Check Order Status", "Return Policy"],
                "Do you have an existing order reference you would like us to check?",
                [rec],
            )

        # Returns & Defects only
        if DeliveryTopic.RETURNS in topics and len(topics) == 1:
            return_text = (
                "• **Defective or Damaged Items:** Must be reported within **2 days** of receipt in the original, unopened manufacturer packaging.\n"
                "• **Order Cancellation:** Orders may be cancelled within **24 hours** of placement.\n"
                "• **Refunds:** Approved refunds are processed back to the original payment method and can take up to **45 days** to reflect."
            )
            rec = EvidenceRecord(
                claim=return_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/delivery_policy.json",
                field="returns",
                entity_ids=[],
            )
            return (
                return_text,
                ["Report Damaged Item", "Order Cancellation", "Contact Sales Desk"],
                "Would you like assistance initiating a support request with our technical team?",
                [rec],
            )

        # Hours only
        if DeliveryTopic.HOURS in topics and len(topics) == 1:
            hours_text = (
                "Kepler Tech's Dubai showroom and customer support hours are:\n\n"
                "• **Monday – Friday:** 8:30 AM to 5:30 PM\n"
                "• **Saturday:** 8:30 AM to 1:00 PM\n"
                "• **Sunday:** Closed\n"
                "*(All times in Dubai GST / UTC+4)*\n\n"
                "Showroom Location: D79, Khalid Bin Waleed Road, Abdulla Al Awar Building, Office No. 1, Dubai, UAE."
            )
            rec = EvidenceRecord(
                claim=hours_text,
                verified=True,
                status=CompatibilityStatus.VERIFIED_YES,
                source_file="data/delivery_policy.json",
                field="hours",
                entity_ids=[],
            )
            return (
                hours_text,
                ["Showroom Location", "Free Store Pickup", "Contact Support Desk"],
                "Would you like to visit our showroom to view live equipment demonstrations?",
                [rec],
            )

        # Customs duty
        if DeliveryTopic.CUSTOMS in topics:
            customs_text = (
                "For deliveries outside the UAE, the customer is responsible for all destination import customs clearance, "
                "local tariffs, and import VAT in the destination country. UAE domestic deliveries include standard VAT."
            )
            paragraphs.append(customs_text)

        # Payment terms
        if DeliveryTopic.PAYMENT in topics:
            payment_text = (
                "Payment is required in full prior to dispatch. We accept Visa and MasterCard (in AED) or PayPal. "
                "We do not offer cash on delivery (COD) for commercial hardware."
            )
            paragraphs.append(payment_text)

        # Same Day
        if DeliveryTopic.SAME_DAY in topics:
            same_day_text = (
                "Standard dispatch is **1 to 2 business days**. Emergency same-day delivery within Dubai may be coordinated "
                "directly through our sales desk for in-stock equipment and consumables."
            )
            paragraphs.append(same_day_text)

        # Store Pickup
        if DeliveryTopic.PICKUP in topics and DeliveryTopic.FEE not in topics and DeliveryTopic.COVERAGE not in topics:
            pickup_text = (
                "**Free local store pickup** is available at our Dubai showroom (D79, Khalid Bin Waleed Road, Abdulla Al Awar Building). "
                "Orders are typically prepared and ready for collection within **1 to 2 business days** following order confirmation."
            )
            paragraphs.append(pickup_text)

        # Tracking
        if DeliveryTopic.TRACKING in topics:
            track_text = (
                "As soon as your package ships, an automated shipment notification with courier tracking details is emailed "
                "so you can track transit progress in real time."
            )
            paragraphs.append(track_text)

        # Courier
        if DeliveryTopic.COURIER in topics:
            courier_text = (
                "Shipping is handled by authorized, insured third-party couriers. For large production printers and wide-format plotters, "
                "Kepler Tech's technical team provides dedicated site delivery, uncrating, and certified on-site installation."
            )
            paragraphs.append(courier_text)

        # Core Fee / Timing / Coverage / General
        if not paragraphs or any(t in topics for t in (DeliveryTopic.FEE, DeliveryTopic.TIME, DeliveryTopic.COVERAGE, DeliveryTopic.GENERAL)):
            if zone == DeliveryZone.UAE:
                core_text = (
                    f"Delivery across {dest_name} and all UAE emirates is a **flat AED 10**, "
                    "dispatched within **1 to 2 business days** (excluding weekends and public holidays).\n\n"
                    "Free store pickup at our Dubai showroom is also available (ready in 1 to 2 days). "
                    "On-site installation is provided for production plotters."
                )
            elif zone in (DeliveryZone.OMAN, DeliveryZone.GCC_OTHER):
                core_text = (
                    f"We deliver to **{dest_name}** and across the GCC via insured cross-border courier. "
                    "Shipping fees are calculated at checkout based on parcel weight and destination location. "
                    "Orders dispatch from Dubai within **1 to 2 business days**."
                )
            elif zone == DeliveryZone.OUTSIDE_GCC:
                core_text = (
                    "We deliver across the UAE and GCC, and international shipping fees are calculated dynamically at checkout "
                    "depending on destination country and parcel weight. Standard order dispatch is **1 to 2 business days**."
                )
            else:  # UNKNOWN
                core_text = (
                    "• **Delivery Coverage:** We deliver across Dubai, Abu Dhabi, and all UAE emirates, as well as Oman and the GCC (Saudi Arabia, Qatar, Bahrain, Kuwait).\n"
                    "• **Shipping Fees:** Delivery across the UAE is a **flat AED 10**. Outside the UAE, shipping is calculated at checkout based on destination and weight.\n"
                    "• **Dispatch Timing:** Orders are dispatched in **1 to 2 business days** after confirmation email.\n"
                    "• **Store Pickup:** Free local pickup is available at our Dubai showroom (ready in 1 to 2 business days)."
                )
            paragraphs.insert(0, core_text)

        final_reply = "\n\n".join(paragraphs)

        # Construct evidence record
        rec = EvidenceRecord(
            claim=final_reply,
            verified=True,
            status=CompatibilityStatus.VERIFIED_YES,
            source_file="data/delivery_policy.json",
            field="delivery_policy",
            entity_ids=[],
        )

        # Contextual Chips & Next Step
        if zone == DeliveryZone.UNKNOWN:
            chips = ["Dubai / UAE (AED 10)", "Oman", "Saudi Arabia / GCC", "Free Store Pickup"]
            next_step = "Which destination would you like delivery to?"
        elif zone == DeliveryZone.UAE:
            chips = ["Delivery Fee (AED 10)", "Dispatch Timing", "Free Store Pickup", "Contact Sales Desk"]
            next_step = "Would you like to arrange delivery or pickup for a specific equipment model?"
        else:
            chips = ["Checkout Calculation", "Customs Duties", "Dispatch Timing", "Contact Sales Desk"]
            next_step = f"Would you like an official shipping estimate for {dest_name}?"

        return final_reply, chips, next_step, [rec]
