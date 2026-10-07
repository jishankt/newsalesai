"""
Commercial Quotation Generator & Sales Desk Integration.
Generates structured commercial quotations, itemized pricing tables (with UAE 5% VAT),
product specification highlights, and registers high-priority leads in the Sales CRM.
"""

import re
import time
import datetime
from typing import Dict, Any, List, Optional, Tuple

from catalog.price_resolver import price_resolver
from persistence.lead_repository import lead_repository
from guardrails import OFFICIAL_SUPPORT_EMAIL, OFFICIAL_SUPPORT_PHONE, OFFICIAL_WEBSITE_URL


def parse_quantity(message: str) -> int:
    """Parses order quantity from user message (e.g. 'order this 3', '3 units', 'quantity 2')."""
    msg_l = message.lower()
    
    # Direct patterns: "order this 3", "order these 3", "buy 3", "need 3 units"
    patterns = [
        r"\b(?:order|buy|purchase|quantity|qty|need|want|get)\s*(?:of\s+)?(\d+)\b",
        r"\b(\d+)\s*(?:units?|pcs?|pieces?|printers?|machines?|scanners?|items?)\b",
        r"\b(?:this|these|it)\s+(\d+)\b",
        r"\b(?:order|buy|purchase)\s+(?:this|these|it)\s*(?:x|\*|\s)\s*(\d+)\b",
    ]
    for p in patterns:
        m = re.search(p, msg_l)
        if m:
            try:
                val = int(m.group(1))
                if 1 <= val <= 100:
                    return val
            except (ValueError, IndexError):
                pass
    return 1


def is_multi_product_order(message: str) -> bool:
    """Checks if user asked to order multiple models (e.g. 'order these 3', 'order all 3')."""
    msg_l = message.lower()
    return bool(re.search(
        r"\b(?:order|buy|purchase)\s+(?:all|both|these|those)\b"
        r"|\b(?:order|buy|purchase)\s+(?:all\s+)?(?:the\s+)?(?:2|3|4)\s+(?:models|printers|options|units|items)\b"
        r"|\b(?:order|buy|purchase)\s+these\s+(?:2|3|4)\b",
        msg_l
    ))


EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_REGEX = re.compile(r"(?:\+?971|00971|0)?\s*[5234679]\d[\s-]?\d{3}[\s-]?\d{4}\b|\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")


def generate_quotation(
    items: List[Dict[str, Any]],
    quantities: List[int],
    state: Any,
    session_id: str,
    user_message: str = "",
) -> Dict[str, Any]:
    """
    Generates a formal Commercial Quotation with product details, itemized table,
    UAE VAT calculations, CRM lead registration, and sales desk dispatch notice.
    """
    now = datetime.datetime.now()
    date_str = now.strftime("%d %B %Y")
    ts_seed = int(time.time() * 1000) % 1000000
    quo_ref = f"QUO-{now.year}-{ts_seed:06d}"

    cust_name = getattr(state, "customer_name", None) or "Valued Client"
    cust_contact = getattr(state, "customer_phone_or_email", None)

    # Extract contact info from user_message if provided
    if user_message:
        em = EMAIL_REGEX.search(user_message)
        ph = PHONE_REGEX.search(user_message)
        if em:
            cust_contact = em.group(0)
            if state:
                state.customer_phone_or_email = cust_contact
        elif ph and len(re.sub(r"\D", "", ph.group(0))) >= 7:
            cust_contact = ph.group(0).strip()
            if state:
                state.customer_phone_or_email = cust_contact

        nm = re.search(r"\b(?:my name is|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", user_message, re.I)
        if nm:
            cust_name = nm.group(1).strip()
            if state:
                state.customer_name = cust_name

    line_items: List[Dict[str, Any]] = []
    total_excl_vat = 0.0
    has_custom_pricing = False

    for prod, qty in zip(items, quantities):
        name = prod.get("display_name") or prod.get("name") or prod.get("model") or "Kepler Equipment"
        pinfo = price_resolver.get_price_info(prod=prod)
        price_val = pinfo.get("price")
        url = pinfo.get("url") or prod.get("website_url") or prod.get("product_url") or OFFICIAL_WEBSITE_URL

        if price_val and not pinfo.get("is_request"):
            unit_price = float(price_val)
            line_total = unit_price * qty
            total_excl_vat += line_total
            line_items.append({
                "product": prod,
                "name": name,
                "qty": qty,
                "unit_price": unit_price,
                "line_total": line_total,
                "is_request": False,
                "url": url,
            })
        else:
            has_custom_pricing = True
            line_items.append({
                "product": prod,
                "name": name,
                "qty": qty,
                "unit_price": None,
                "line_total": None,
                "is_request": True,
                "url": url,
            })

    vat_amount = total_excl_vat * 0.05
    grand_total = total_excl_vat + vat_amount

    # Build professional quotation markdown table
    lines = [
        f"### 📋 Official Commercial Quotation",
        f"**Quotation Ref:** `{quo_ref}` | **Date:** {date_str}",
        f"**Prepared For:** {cust_name}" + (f" ({cust_contact})" if cust_contact else "") + "\n",
        "| # | Product Description | Qty | Unit Price (Excl. VAT) | Line Total (AED) |",
        "| :--- | :--- | :---: | :---: | :---: |",
    ]

    for idx, item in enumerate(line_items, 1):
        if not item["is_request"]:
            u_str = f"AED {item['unit_price']:,.2f}"
            t_str = f"AED {item['line_total']:,.2f}"
        else:
            u_str = "Commercial Quote"
            t_str = "Project Pricing"
        lines.append(f"| {idx} | **{item['name']}** | {item['qty']} | {u_str} | {t_str} |")

    lines.append("")
    if not has_custom_pricing or total_excl_vat > 0:
        lines.append(f"• **Subtotal (Excl. VAT):** AED {total_excl_vat:,.2f}")
        lines.append(f"• **UAE Value Added Tax (5% VAT):** AED {vat_amount:,.2f}")
        lines.append(f"• **Grand Total (Incl. 5% VAT):** **AED {grand_total:,.2f}**\n")
    else:
        lines.append("• **Pricing Category:** Enterprise Commercial Supply (Official Contract Terms)\n")

    # Product highlights
    lines.append("#### ⚙️ Included Equipment Specifications & Warranty:")
    for item in line_items:
        prod = item["product"]
        speed = prod.get("speed") or prod.get("print_speed") or prod.get("scan_speed")
        spec_notes = []
        if speed:
            spec_notes.append(f"Speed: {speed}")
        if prod.get("paper_size"):
            spec_notes.append(f"Format: {str(prod['paper_size']).upper()}")
        elif prod.get("max_width_inches"):
            spec_notes.append(f"Width: {prod['max_width_inches']}\"")
        spec_notes.append("1-Year Official Manufacturer Warranty")
        spec_notes.append("Genuine UAE Authorized Stock")
        specs_str = " • ".join(spec_notes)
        lines.append(f"• **{item['name']}** ({item['qty']} unit{'s' if item['qty'] > 1 else ''}): {specs_str}")

    # Commercial Dispatch & Next Steps Notice
    lines.append("\n#### 🚚 Delivery & Order Fulfillment:")
    lines.append("• **Delivery:** Express delivery & optional on-site setup available across all UAE Emirates.")
    lines.append("• **Payment Methods:** Corporate Bank Transfer, Official Tax Invoice, or Direct Online Checkout.")

    # Direct Web Checkout Link
    primary_url = line_items[0]["url"] if line_items else OFFICIAL_WEBSITE_URL
    primary_name = line_items[0]["name"] if line_items else "Equipment"
    if not has_custom_pricing:
        lines.append(f"\n🛒 **Instant Online Checkout:**\n👉 [Complete Order on Kepler Website for {primary_name}]({primary_url})\n")

    # Sales Engineering Team Notification
    lines.append("---")
    lines.append(
        "📞 **Sales Desk Notification:**\n"
        "Our sales engineering team at **Kepler Tech LLC** has received your quotation details and will connect with you shortly to assist with order processing, official PDF invoice delivery, and delivery scheduling."
    )

    if not cust_contact:
        lines.append(
            "\n💡 *To dispatch your formal PDF quotation and finalize delivery, please provide your **Phone Number or Email** and **Delivery City** (e.g., Dubai, Abu Dhabi).*"
        )

    reply_text = "\n".join(lines)

    # ── TRIGGER SALES PORTION: CRM Persistence & High-Priority Lead ──────
    product_summary = ", ".join(f"{it['name']} (Qty: {it['qty']})" for it in line_items)
    notes_content = (
        f"Quotation #{quo_ref} generated. "
        f"Grand Total: AED {grand_total:,.2f} (Incl. 5% VAT). "
        f"Items: {product_summary}. "
        f"Customer instructed: sales team to connect."
    )
    
    lead_id = None
    try:
        lead_id = lead_repository.save_lead(
            session_id=session_id,
            customer_name=getattr(state, "customer_name", None) or "Online Client",
            company=getattr(state, "customer_company", None),
            email=cust_contact if (cust_contact and "@" in cust_contact) else None,
            phone=cust_contact if (cust_contact and "@" not in cust_contact) else None,
            product_interest=f"Quote #{quo_ref}: {product_summary}",
            notes=notes_content,
        )
    except Exception as e:
        pass

    return {
        "reply": reply_text,
        "quotation_ref": quo_ref,
        "grand_total": grand_total,
        "lead_id": lead_id,
        "line_items": line_items,
    }
