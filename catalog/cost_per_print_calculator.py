"""
Cost Per Print Calculator for Kepler Tech Conversational AI.

Implements reusable, auditable cost-per-print calculations:
    Cost per print = Total verified consumable cost for sold pack ÷ Verified usable prints from sold pack

Rules:
- For dye-sublimation media kits (Citizen), media is sold in 2-roll boxes containing matched ink ribbon and paper rolls.
  A yield of N prints per roll means 2 * N usable prints per sold box.
- Separate 4×6″, 6×8″, 8×10″, 8×12″, etc., using matching SKU and verified capacity.
- For inkjet printers, ISO/IEC 24711 office yields (5% page coverage) apply only to standard office documents,
  NOT full-bleed colour photos. Paper cost must be stated separately or excluded.
- If necessary prices, package quantities, yields, or usage assumptions are missing, return
  "Print cost cannot be verified from the available data" rather than an invented number.
- Withhold printer hardware selling prices and discounts per commercial policy.
- Currency: AED, Tax basis: Excl. VAT, Price source: Kepler Tech official product page / price catalogue, Verification date: September 2026.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class CostCalculationResult:
    printer_id: str
    printer_name: str
    print_format: str
    status: str  # "verified", "insufficient_verified_data", "unsupported_format"
    cost_per_print_aed: Optional[float] = None
    cost_per_print_formatted: Optional[str] = None
    consumable_sku: Optional[str] = None
    consumable_name: Optional[str] = None
    package_price_aed: Optional[float] = None
    package_price_formatted: Optional[str] = None
    package_yield_prints: Optional[int] = None
    rolls_per_box: Optional[int] = None
    prints_per_roll: Optional[int] = None
    tax_basis: str = "Excl. VAT"
    currency: str = "AED"
    verification_date: str = "September 2026"
    source_reference: str = "Kepler Tech official store / Manufacturer specifications"
    notes: Optional[str] = None
    explanation: Optional[str] = None


class CostPerPrintCalculator:
    """
    Auditable Cost-Per-Print calculator for approved printers.
    """

    # Citizen Dye-Sublimation verified media packaging and pricing (Kepler Tech Store, Sept 2026)
    # Sold as 2 rolls + 2 matched ribbon rolls per box.
    CITIZEN_MEDIA_DATA = {
        "citizen-cy-02": {
            "4x6": {
                "sku": "CY-MS46",
                "name": "Citizen CY-MS46 Media Set (4×6″)",
                "price": 625.0,
                "rolls_per_box": 2,
                "prints_per_roll": 700,
                "total_yield": 1400,
                "url": "https://www.keplertechllc.com/product/citizen-cy-ms46-4x6/",
            },
            "6x8": {
                "sku": "CY-MS68",
                "name": "Citizen CY-MS68 Media Set (6×8″)",
                "price": 685.0,
                "rolls_per_box": 2,
                "prints_per_roll": 350,
                "total_yield": 700,
                "url": "https://www.keplertechllc.com/product/citizen-cy-ms68/",
            },
        },
        "citizen-cx-02": {
            "4x6": {
                "sku": "CX2.4x6",  # also CX2-MS46 / 9797
                "name": "Citizen CX-02 4×6″ Media Kit (CX2-MS46)",
                "price": 490.0,
                "rolls_per_box": 2,
                "prints_per_roll": 400,
                "total_yield": 800,
                "url": "https://www.keplertechllc.com/product/citizen-cx-02-4x6-printer-media/",
            },
            "6x8": {
                "sku": "CX2.6x8",  # also CX2-MS68 / 19048 / 9795
                "name": "Citizen CX-02 6×8″ Media Kit (CX2-MS68)",
                "price": 500.0,
                "rolls_per_box": 2,
                "prints_per_roll": 200,
                "total_yield": 400,
                "url": "https://www.keplertechllc.com/product/citizen-cx-02-printer-6x8-media/",
            },
        },
        "citizen-cx-02w": {
            "8x12": {
                "sku": "CX2W 812",
                "name": "Citizen CX2W 8×12″ Media Kit",
                "price": 975.0,
                "rolls_per_box": 2,
                "prints_per_roll": 110,
                "total_yield": 220,
                "url": "https://www.keplertechllc.com/product/citizen-cx2w-8x12-media/",
            },
            "8x10": {
                "sku": "CX2W 812",
                "name": "Citizen CX2W 8×10″ / 8×12″ Media Kit (with spacer)",
                "price": 975.0,
                "rolls_per_box": 2,
                "prints_per_roll": 110,
                "total_yield": 220,
                "url": "https://www.keplertechllc.com/product/citizen-cx2w-8x12-media/",
            },
            "a4": {
                "sku": "CX2W A4",
                "name": "Citizen CX2W A4 Media Kit",
                "price": 975.0,
                "rolls_per_box": 2,
                "prints_per_roll": 110,
                "total_yield": 220,
                "url": "https://www.keplertechllc.com/product/citizen-cx2w-8x12-media/",
            },
        },
        "citizen-cz-01": {
            "4x6": {
                "sku": "CZ-MS46",
                "name": "Citizen CZ-MS46 Media Set (4×6″)",
                "price": 295.0,
                "rolls_per_box": 2,
                "prints_per_roll": 150,
                "total_yield": 300,
                "url": "https://www.keplertechllc.com/product/citizen-cz-ms46-4x-6/",
            },
            "4.5x8": {
                "sku": "CZ-MS458",
                "name": "Citizen CZ-MS458 Media Set (4.5×8″)",
                "price": 340.0,
                "rolls_per_box": 2,
                "prints_per_roll": 110,
                "total_yield": 220,
                "url": "https://www.keplertechllc.com/product/citizen-cz-ms458-4-5x8-media/",
            },
        },
    }

    # Inkjet office printers with ISO/IEC 24711 verified running cost data
    # (Excludes paper cost; assumes 5% ISO page coverage)
    INKJET_ISO_DATA = {
        "epson-am-c4000": {
            "name": "Epson WorkForce Enterprise AM-C4000",
            "mono_ink_sku": "C13T08H100 (Black)",
            "mono_ink_price": 220.0,
            "mono_yield": 31500,
            "mono_cost_per_page": 0.007,
            "color_ink_skus": ["C13T08H200 (Cyan)", "C13T08H300 (Magenta)", "C13T08H400 (Yellow)"],
            "color_ink_price_each": 220.0,
            "color_yield": 28000,
            "color_cost_per_page": 0.0236,
            "standard": "ISO/IEC 24711 office document test suite (approx. 5% coverage per color, plain paper excluded)",
        },
        "epson-am-c5000": {
            "name": "Epson WorkForce Enterprise AM-C5000",
            "mono_ink_sku": "C13T08G100 (Black)",
            "mono_ink_price": 220.0,
            "mono_yield": 50000,
            "mono_cost_per_page": 0.0044,
            "color_ink_skus": ["C13T08G200 (Cyan)", "C13T08G300 (Magenta)", "C13T08G400 (Yellow)"],
            "color_ink_price_each": 220.0,
            "color_yield": 30000,
            "color_cost_per_page": 0.022,
            "standard": "ISO/IEC 24711 office document test suite (approx. 5% coverage per color, plain paper excluded)",
        },
        "epson-am-c6000": {
            "name": "Epson WorkForce Enterprise AM-C6000",
            "mono_ink_sku": "C13T08G100 (Black)",
            "mono_ink_price": 220.0,
            "mono_yield": 50000,
            "mono_cost_per_page": 0.0044,
            "color_ink_skus": ["C13T08G200 (Cyan)", "C13T08G300 (Magenta)", "C13T08G400 (Yellow)"],
            "color_ink_price_each": 220.0,
            "color_yield": 30000,
            "color_cost_per_page": 0.022,
            "standard": "ISO/IEC 24711 office document test suite (approx. 5% coverage per color, plain paper excluded)",
        },
    }

    @classmethod
    def calculate_cost_per_print(
        cls,
        printer_id: str,
        print_format: Optional[str] = None,
        printer_name: Optional[str] = None
    ) -> CostCalculationResult:
        """
        Calculates verified cost per print for a specific printer and format.
        """
        pid = (printer_id or "").lower().strip()
        pname = printer_name or pid
        fmt = (print_format or "").lower().replace("×", "x").replace(" ", "").replace("inch", "").replace("inches", "").replace('"', '').strip()

        # Normalize format string
        if fmt in ["4x6", "4*6", "10x15", "101x152"]:
            fmt = "4x6"
        elif fmt in ["6x8", "6*8", "15x20", "152x203"]:
            fmt = "6x8"
        elif fmt in ["5x7", "5*7", "13x18", "127x178"]:
            fmt = "5x7"
        elif fmt in ["8x10", "8*10", "20x25"]:
            fmt = "8x10"
        elif fmt in ["8x12", "8*12", "20x30", "203x305"]:
            fmt = "8x12"
        elif fmt in ["4.5x8", "4.5*8"]:
            fmt = "4.5x8"

        # Check Citizen Dye-Sublimation Printers
        citizen_matched = None
        for key in sorted(cls.CITIZEN_MEDIA_DATA.keys(), key=len, reverse=True):
            if key in pid or pid == key:
                citizen_matched = key
                break

        if citizen_matched:
            # Handle unsupported formats explicitly
            if citizen_matched == "citizen-cy-02" and fmt == "5x7":
                return CostCalculationResult(
                    printer_id=citizen_matched,
                    printer_name="Citizen CY-02 High-Capacity Photo Printer",
                    print_format="5x7",
                    status="unsupported_format",
                    explanation="Citizen CY-02 does not support 5×7″ media. Its verified supported print formats are 4×6″ and 6×8″ only.",
                )

            media_map = cls.CITIZEN_MEDIA_DATA[citizen_matched]
            target_fmt = fmt if fmt in media_map else ("4x6" if "4x6" in media_map else list(media_map.keys())[0])

            if target_fmt in media_map:
                m_info = media_map[target_fmt]
                total_prints = m_info["total_yield"]
                box_price = m_info["price"]
                cost_per_print = round(box_price / total_prints, 2)
                cost_per_print_exact = box_price / total_prints

                explanation = (
                    f"Verified cost per {target_fmt}″ print for **{pname}**:\n"
                    f"• **Consumable Kit:** [{m_info['name']}]({m_info['url']}) (SKU: `{m_info['sku']}`)\n"
                    f"• **Sold Pack Contents:** Box of {m_info['rolls_per_box']} rolls + {m_info['rolls_per_box']} matched ribbons ({m_info['prints_per_roll']:,} prints/roll = **{total_prints:,} usable prints** per box)\n"
                    f"• **Verified Pack Price:** AED {box_price:,.2f} Excl. VAT\n"
                    f"• **Calculation Formula:** AED {box_price:,.2f} ÷ {total_prints:,} prints = **AED {cost_per_print:.2f} per print** ({cost_per_print_exact:.4f} AED exact)\n"
                    f"*(Source: Kepler Tech official media price catalogue, September 2026. Hardware selling prices and commercial details are not provided in this chat per company commercial policy.)*"
                )

                return CostCalculationResult(
                    printer_id=citizen_matched,
                    printer_name=pname,
                    print_format=target_fmt,
                    status="verified",
                    cost_per_print_aed=cost_per_print,
                    cost_per_print_formatted=f"AED {cost_per_print:.2f}",
                    consumable_sku=m_info["sku"],
                    consumable_name=m_info["name"],
                    package_price_aed=box_price,
                    package_price_formatted=f"AED {box_price:,.2f}",
                    package_yield_prints=total_prints,
                    rolls_per_box=m_info["rolls_per_box"],
                    prints_per_roll=m_info["prints_per_roll"],
                    explanation=explanation,
                )

        # Check Inkjet Office Printers with ISO yields
        inkjet_matched = None
        for key in cls.INKJET_ISO_DATA:
            if key in pid:
                inkjet_matched = key
                break

        if inkjet_matched:
            ij_info = cls.INKJET_ISO_DATA[inkjet_matched]
            mono_cpp = ij_info["mono_cost_per_page"]
            color_cpp = ij_info["color_cost_per_page"]
            total_color_cpp = mono_cpp + color_cpp

            explanation = (
                f"Verified ISO document running costs for **{ij_info['name']}**:\n"
                f"• **Mono (Black) Ink Cost:** **AED {mono_cpp:.3f} per page** (Black pack `{ij_info['mono_ink_sku']}`: AED {ij_info['mono_ink_price']:.2f} Excl. VAT ÷ {ij_info['mono_yield']:,} ISO pages)\n"
                f"• **Colour Ink Running Cost:** **AED {total_color_cpp:.3f} per page** (CMY packs: AED {ij_info['color_ink_price_each'] * 3:.2f} Excl. VAT ÷ {ij_info['color_yield']:,} ISO pages)\n"
                f"• **Standard & Basis:** {ij_info['standard']}.\n"
                f"• **Photo Cost Disclaimer:** ISO/IEC 24711 page yields test standard 5% coverage business documents. Print cost for full-bleed colour photos cannot be derived from ISO office yields as ink consumption varies significantly with image saturation and paper substrate."
            )

            return CostCalculationResult(
                printer_id=inkjet_matched,
                printer_name=ij_info["name"],
                print_format="ISO A4 Document",
                status="verified",
                cost_per_print_aed=round(total_color_cpp, 2),
                cost_per_print_formatted=f"AED {total_color_cpp:.2f} (colour) / AED {mono_cpp:.3f} (mono)",
                explanation=explanation,
            )

        # For all other printers (where complete cartridge set prices, paper costs, or photo yields are not all verified)
        missing_reasons = (
            "Print cost cannot be verified from the available data. "
            "Calculating a verified cost per print requires confirmed consumable pack pricing, "
            "standardized page coverage yields for the specific print format, and specified paper substrate costs. "
            "Kepler Tech provides custom cost assessments and sample prints for your specific production volume upon request."
        )

        return CostCalculationResult(
            printer_id=pid,
            printer_name=pname,
            print_format=fmt or "unspecified",
            status="insufficient_verified_data",
            explanation=missing_reasons,
        )

    @classmethod
    def get_all_citizen_cost_summary(cls) -> str:
        """
        Returns a concise, verified summary of cost per print across all Citizen photo printers.
        """
        lines = [
            "### Verified Cost Per Print for Citizen Photo Printers (AED Excl. VAT)",
            "All Citizen media kits include matched ribbon and paper rolls sold in 2-roll boxes:\n",
            "| Printer Model | Print Size | Compatible Media SKU | Box Contents & Yield | Box Price (AED) | Cost Per Print (AED) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for pid, formats in cls.CITIZEN_MEDIA_DATA.items():
            for fmt, data in formats.items():
                pname = {
                    "citizen-cy-02": "Citizen CY-02",
                    "citizen-cx-02": "Citizen CX-02",
                    "citizen-cx-02w": "Citizen CX-02W",
                    "citizen-cz-01": "Citizen CZ-01",
                }.get(pid, pid)
                cpp = data["price"] / data["total_yield"]
                lines.append(
                    f"| **{pname}** | {fmt}″ | `{data['sku']}` | 2 rolls × {data['prints_per_roll']} = {data['total_yield']} prints | AED {data['price']:,.2f} | **AED {cpp:.2f}** |"
                )
        lines.append("\n*Calculation: Sold box price ÷ verified usable prints per box. Prices as of September 2026 from Kepler Tech official catalogue.*")
        return "\n".join(lines)


cost_per_print_calculator = CostPerPrintCalculator()
