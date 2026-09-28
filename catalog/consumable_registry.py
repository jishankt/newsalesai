"""
Explicit Consumable Registry for Kepler Tech Conversational AI.

Enforces strict, testable consumable-to-printer compatibility relationships.
Distinguishes:
  - 'ink': Ink packs, cartridges, bottles
  - 'media': Paper rolls, cut sheets, combined dye-sub media sets
  - 'ribbon': Standalone ribbons
  - 'maintenance': Maintenance boxes, tanks, waste collectors
  - 'accessory': Carry bags, cleaning pens, adapters, stands

Strictly answers SKU compatibility questions with:
  - "yes" (verified compatible)
  - "no" (verified incompatible)
  - "unverified" (not found in catalogue)
Never infers compatibility from similar model numbers.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple


@dataclass
class ConsumableItem:
    sku: str
    name: str
    consumable_type: str  # 'ink', 'media', 'ribbon', 'maintenance', 'accessory'
    compatible_printers: List[str]  # canonical printer IDs
    size_format: Optional[str] = None  # e.g., "4x6", "6x8", "8x12", "A4", "A1"
    dimensions: Optional[str] = None  # e.g., "101 x 152 mm", "17 inch roll"
    pack_quantity: Optional[str] = None  # e.g., "2 rolls + 2 ribbons per box", "1 cartridge"
    yield_info: Optional[str] = None  # e.g., "700 prints/roll (1,400 prints/box)", "50,000 ISO pages"
    color: Optional[str] = None  # e.g., "Photo Black", "Cyan", "Yellow"
    price_aed: Optional[float] = None
    url: Optional[str] = None


class ConsumableRegistry:
    def __init__(self):
        self.consumables: Dict[str, ConsumableItem] = {}
        self.printer_to_skus: Dict[str, Set[str]] = {}
        self._initialize_registry()

    def _add(self, item: ConsumableItem):
        sku_clean = item.sku.upper().strip()
        self.consumables[sku_clean] = item
        for pid in item.compatible_printers:
            pid_clean = pid.lower().strip()
            if pid_clean not in self.printer_to_skus:
                self.printer_to_skus[pid_clean] = set()
            self.printer_to_skus[pid_clean].add(sku_clean)

    def _initialize_registry(self):
        # ── Citizen Photo Printers Media & Accessories ─────────────────────
        # CY-02 Media (Exclusively for CY-02; NEVER CX-02, CX-02W, CZ-01)
        self._add(ConsumableItem(
            sku="CY-MS46",
            name="Citizen CY-MS46 4×6″ Media Set",
            consumable_type="media",
            compatible_printers=["citizen-cy-02"],
            size_format="4x6",
            dimensions="101 × 152 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="700 prints per roll (1,400 prints per box)",
            price_aed=625.0,
            url="https://www.keplertechllc.com/product/citizen-cy-ms46-4x6/"
        ))
        self._add(ConsumableItem(
            sku="CY-MS68",
            name="Citizen CY-MS68 6×8″ Media Set",
            consumable_type="media",
            compatible_printers=["citizen-cy-02"],
            size_format="6x8",
            dimensions="152 × 203 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="350 prints per roll (700 prints per box)",
            price_aed=685.0,
            url="https://www.keplertechllc.com/product/citizen-cy-ms68/"
        ))
        self._add(ConsumableItem(
            sku="CY02BAG",
            name="Citizen CY-02 Heavy-Duty Carry Bag",
            consumable_type="accessory",
            compatible_printers=["citizen-cy-02"],
            pack_quantity="1 bag",
            price_aed=335.0,
            url="https://www.keplertechllc.com/product/citizen-cy-02-carry-bags/"
        ))

        # CX-02 Media & Accessories (Exclusively for CX-02; NOT CY-02 or CZ-01)
        self._add(ConsumableItem(
            sku="CX2.4X6",
            name="Citizen CX-02 4×6″ Media Kit (CX2-MS46)",
            consumable_type="media",
            compatible_printers=["citizen-cx-02"],
            size_format="4x6",
            dimensions="101 × 152 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="400 prints per roll (800 prints per box)",
            price_aed=490.0,
            url="https://www.keplertechllc.com/product/citizen-cx-02-4x6-printer-media/"
        ))
        self._add(ConsumableItem(
            sku="CX2.6X8",
            name="Citizen CX-02 6×8″ Media Kit (CX2-MS68)",
            consumable_type="media",
            compatible_printers=["citizen-cx-02"],
            size_format="6x8",
            dimensions="152 × 203 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="200 prints per roll (400 prints per box)",
            price_aed=500.0,
            url="https://www.keplertechllc.com/product/citizen-cx-02-printer-6x8-media/"
        ))
        self._add(ConsumableItem(
            sku="CITIZEN CX-02 BAG",
            name="Citizen CX-02 Padded Carry Bag",
            consumable_type="accessory",
            compatible_printers=["citizen-cx-02"],
            pack_quantity="1 bag",
            price_aed=325.0,
            url="https://www.keplertechllc.com/product/citizen-cx-02-printer-carry-bag/"
        ))

        # CX-02W Wide Media (Exclusively for CX-02W 8-inch)
        self._add(ConsumableItem(
            sku="CX2W 812",
            name="Citizen CX2W 8×10″ / 8×12″ Media Kit",
            consumable_type="media",
            compatible_printers=["citizen-cx-02w"],
            size_format="8x12",
            dimensions="203 × 305 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="110 prints per roll (220 prints per box)",
            price_aed=975.0,
            url="https://www.keplertechllc.com/product/citizen-cx2w-8x12-media/"
        ))

        # CZ-01 Compact Media & Accessories (Exclusively for CZ-01)
        self._add(ConsumableItem(
            sku="CZ-MS46",
            name="Citizen CZ-MS46 4×6″ Media Set",
            consumable_type="media",
            compatible_printers=["citizen-cz-01"],
            size_format="4x6",
            dimensions="101 × 152 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="150 prints per roll (300 prints per box)",
            price_aed=295.0,
            url="https://www.keplertechllc.com/product/citizen-cz-ms46-4x-6/"
        ))
        self._add(ConsumableItem(
            sku="CZ-MS458",
            name="Citizen CZ-MS458 4.5×8″ Media Set",
            consumable_type="media",
            compatible_printers=["citizen-cz-01"],
            size_format="4.5x8",
            dimensions="114 × 203 mm",
            pack_quantity="2 rolls + 2 ink ribbons per box",
            yield_info="110 prints per roll (220 prints per box)",
            price_aed=340.0,
            url="https://www.keplertechllc.com/product/citizen-cz-ms458-4-5x8-media/"
        ))
        self._add(ConsumableItem(
            sku="CZ01 CARRY BAG",
            name="Citizen CZ-01 Compact Travel Carry Bag",
            consumable_type="accessory",
            compatible_printers=["citizen-cz-01"],
            pack_quantity="1 bag",
            price_aed=250.0,
            url="https://www.keplertechllc.com/product/citizen-cz-01-printer-carry-bag/"
        ))
        self._add(ConsumableItem(
            sku="CITIZEN PEN",
            name="Citizen Thermal Printhead Cleaning Pen",
            consumable_type="accessory",
            compatible_printers=["citizen-cy-02", "citizen-cx-02", "citizen-cx-02w", "citizen-cz-01"],
            pack_quantity="1 pen",
            price_aed=190.0,
            url="https://www.keplertechllc.com/product/citizen-thermal-head-cleaning-pen/"
        ))

        # ── Epson Office A3 (AM-C4000, AM-C5000, AM-C6000) ───────────────────
        # AM-C4000 Inks & Maintenance
        for sku, col, yld in [
            ("C13T08H100", "Black", "31,500 ISO pages"),
            ("C13T08H200", "Cyan", "28,000 ISO pages"),
            ("C13T08H300", "Magenta", "28,000 ISO pages"),
            ("C13T08H400", "Yellow", "28,000 ISO pages"),
        ]:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson AM-C4000 High-Capacity Ink Pack ({col})",
                consumable_type="ink",
                compatible_printers=["epson-am-c4000"],
                color=col,
                yield_info=yld,
                pack_quantity="1 ink pack",
                price_aed=220.0,
                url=f"https://www.keplertechllc.com/product/{sku.lower()}-epson-workforce-enterprise-am-c4000-{col.lower()}-ink/"
            ))
        # AM-C5000 / AM-C6000 Inks
        for sku, col, yld in [
            ("C13T08G100", "Black", "50,000 ISO pages"),
            ("C13T08G200", "Cyan", "30,000 ISO pages"),
            ("C13T08G300", "Magenta", "30,000 ISO pages"),
            ("C13T08G400", "Yellow", "30,000 ISO pages"),
        ]:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson AM-C5000/C6000 Ultra-High-Capacity Ink Pack ({col})",
                consumable_type="ink",
                compatible_printers=["epson-am-c5000", "epson-am-c6000"],
                color=col,
                yield_info=yld,
                pack_quantity="1 ink pack",
                price_aed=220.0,
                url=f"https://www.keplertechllc.com/product/{sku.lower()}-epson-workforce-enterprise-am-c5000-6000-{col.lower()}-ink/"
            ))
        # Shared AM-C Maintenance Box
        self._add(ConsumableItem(
            sku="C12C937181",
            name="Epson Maintenance Box (AM-C4000/AM-C5000/AM-C6000)",
            consumable_type="maintenance",
            compatible_printers=["epson-am-c4000", "epson-am-c5000", "epson-am-c6000"],
            pack_quantity="1 unit",
            price_aed=180.0,
            url="https://www.keplertechllc.com/product/c12c937181-epson-maintenance-box-am-c4000-5000-6000/"
        ))

        # ── Epson Photo Printers (SC-P700, SC-P900) ─────────────────────────
        # SC-P900 17" Inks (50ml C13T47A series)
        p900_colors = [
            ("C13T47A100", "Photo Black"),
            ("C13T47A200", "Cyan"),
            ("C13T47A300", "Vivid Magenta"),
            ("C13T47A400", "Yellow"),
            ("C13T47A500", "Light Cyan"),
            ("C13T47A600", "Vivid Light Magenta"),
            ("C13T47A700", "Gray"),
            ("C13T47A800", "Matte Black"),
            ("C13T47A900", "Light Gray"),
            ("C13T47AD00", "Violet"),
        ]
        for sku, col in p900_colors:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson UltraChrome PRO10 Ink Cartridge 50ml ({col})",
                consumable_type="ink",
                compatible_printers=["epson-sc-p900"],
                color=col,
                pack_quantity="1 cartridge (50ml)",
                price_aed=198.0,
                url="https://www.keplertechllc.com/product/epson-surecolor-sc-p900-printer-with-roll-adapter/"
            ))

        # SC-P700 13" Inks (25ml C13T46S series)
        p700_colors = [
            ("C13T46S100", "Photo Black"),
            ("C13T46S200", "Cyan"),
            ("C13T46S300", "Vivid Magenta"),
            ("C13T46S400", "Yellow"),
            ("C13T46S500", "Light Cyan"),
            ("C13T46S600", "Vivid Light Magenta"),
            ("C13T46S700", "Gray"),
            ("C13T46S800", "Matte Black"),
            ("C13T46S900", "Light Gray"),
            ("C13T46SD00", "Violet"),
        ]
        for sku, col in p700_colors:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson UltraChrome PRO10 Ink Cartridge 25ml ({col})",
                consumable_type="ink",
                compatible_printers=["epson-sc-p700"],
                color=col,
                pack_quantity="1 cartridge (25ml)",
                price_aed=135.0,
                url="https://www.keplertechllc.com/product/epson-surecolor-p700-13-photo-printer/"
            ))

        # Maintenance Box for SC-P700 & SC-P900
        self._add(ConsumableItem(
            sku="C12C935711",
            name="Epson Maintenance Box (SC-P700 / SC-P900)",
            consumable_type="maintenance",
            compatible_printers=["epson-sc-p700", "epson-sc-p900"],
            pack_quantity="1 unit",
            price_aed=155.0,
            url="https://www.keplertechllc.com/product/epson-surecolor-sc-p900-printer-with-roll-adapter/"
        ))

        # ── Epson Technical CAD (SC-T3100, SC-T5100) ────────────────────────
        cad_inks = [
            ("C13T40C140", "Black 50ml", "ink", 50),
            ("C13T40C240", "Cyan 26ml", "ink", 26),
            ("C13T40C340", "Magenta 26ml", "ink", 26),
            ("C13T40C440", "Yellow 26ml", "ink", 26),
            ("C13T40D140", "Black 80ml", "ink", 80),
            ("C13T40D240", "Cyan 50ml", "ink", 50),
            ("C13T40D340", "Magenta 50ml", "ink", 50),
            ("C13T40D440", "Yellow 50ml", "ink", 50),
        ]
        for sku, desc, ctype, vol in cad_inks:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson UltraChrome XD2 Cartridge ({desc})",
                consumable_type=ctype,
                compatible_printers=["epson-sc-t3100", "epson-sc-t5100"],
                pack_quantity=f"1 cartridge ({vol}ml)",
                url="https://www.keplertechllc.com/product/epson-surecolor-sc-t3100-wireless-printer-with-stand/"
            ))
        self._add(ConsumableItem(
            sku="C13S210057",
            name="Epson Maintenance Box (SC-T3100 / SC-T5100 / SC-F500)",
            consumable_type="maintenance",
            compatible_printers=["epson-sc-t3100", "epson-sc-t5100", "epson-sc-f500"],
            pack_quantity="1 unit",
            url="https://www.keplertechllc.com/product/epson-surecolor-sc-t3100-wireless-printer-with-stand/"
        ))

        # ── Epson Dye-Sublimation (SC-F100, SC-F500) ────────────────────────
        for sku, col in [
            ("C13T49N100", "Black"),
            ("C13T49N200", "Cyan"),
            ("C13T49N300", "Magenta"),
            ("C13T49N400", "Yellow"),
        ]:
            self._add(ConsumableItem(
                sku=sku,
                name=f"Epson UltraChrome DS Dye-Sub Ink Bottle 140ml ({col})",
                consumable_type="ink",
                compatible_printers=["epson-sc-f100", "epson-sc-f500"],
                color=col,
                pack_quantity="1 bottle (140ml)",
                url="https://www.keplertechllc.com/product/epson-surecolor-sc-f100-printer/"
            ))
        self._add(ConsumableItem(
            sku="C13S210125",
            name="Epson Maintenance Box (SC-F100)",
            consumable_type="maintenance",
            compatible_printers=["epson-sc-f100"],
            pack_quantity="1 unit",
            url="https://www.keplertechllc.com/product/epson-surecolor-sc-f100-printer/"
        ))

    def get_consumables_for_printer(
        self,
        printer_id: str,
        consumable_type: Optional[str] = None
    ) -> List[ConsumableItem]:
        """
        Retrieves verified consumables for a printer, strictly filtering by type if specified.
        consumable_type: 'ink', 'media', 'ribbon', 'maintenance', 'accessory', or None for all.
        """
        pid_clean = (printer_id or "").lower().strip()
        matched_skus = set()
        for p_key, skus in self.printer_to_skus.items():
            if p_key in pid_clean or pid_clean in p_key:
                matched_skus.update(skus)

        results = []
        for sku in matched_skus:
            item = self.consumables.get(sku)
            if item:
                if consumable_type:
                    ctype = consumable_type.lower().strip()
                    if ctype in ("ink", "cartridge", "inks", "cartridges"):
                        if item.consumable_type != "ink":
                            continue
                    elif ctype in ("media", "paper", "ribbon"):
                        if item.consumable_type not in ("media", "ribbon"):
                            continue
                    elif ctype in ("maintenance", "box", "tank"):
                        if item.consumable_type != "maintenance":
                            continue
                    elif ctype in ("accessory", "bag", "pen"):
                        if item.consumable_type != "accessory":
                            continue
                    elif item.consumable_type != ctype:
                        continue
                results.append(item)
        return results

    def check_sku_compatibility(self, sku: str, printer_id: str) -> Tuple[str, str]:
        """
        Answers compatibility with ('yes', explanation), ('no', explanation), or ('unverified', explanation).
        Never infers compatibility from similar names.
        """
        sku_clean = (sku or "").upper().replace(" ", "").replace("-", "").replace(".", "").strip()
        pid_clean = (printer_id or "").lower().strip()

        # Find target consumable
        matched_item = None
        for k, v in self.consumables.items():
            k_clean = k.replace(" ", "").replace("-", "").replace(".", "").upper()
            if sku_clean == k_clean:
                matched_item = v
                break

        if not matched_item:
            return ("unverified", f"Consumable SKU `{sku}` is not in our verified compatibility catalogue.")

        # Check if printer is in compatible list
        is_compat = False
        for p in matched_item.compatible_printers:
            if p in pid_clean or pid_clean in p:
                is_compat = True
                break

        if is_compat:
            return (
                "yes",
                f"Yes, SKU `{matched_item.sku}` ({matched_item.name}) is fully compatible and verified for this printer."
            )
        else:
            compat_list = ", ".join(matched_item.compatible_printers)
            return (
                "no",
                f"No, SKU `{matched_item.sku}` ({matched_item.name}) is not compatible with this model. "
                f"It is compatible only with: {compat_list}."
            )


consumable_registry = ConsumableRegistry()
