"""
Catalogue Loader & Fail-Closed Integrity Enforcer.
Loads data/catalogue_products.json and enforces:
- Exactly 41 approved catalogue entries.
- Unique product IDs.
- Valid approved catalogues.
- Never falls back to website-only models for product recommendations.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger("catalog:loader")

APPROVED_CATALOGUES = {
    "business_a4": "BUSINESS A4 PRINTERS_CATALOG.pdf",
    "business_a3": "BUSINESS A3 PRINTERS_CATALOG.pdf",
    "technical_large_format": "TECHNICAL LARGE FORMAT PRINTERS_CATALOG.pdf",
    "photography_and_fine_art": "LARGE FORMAT PRINTERS FOR PHOTOGRAPHY_CATALOG.pdf",
    "citizen_photo": "CITIZEN PHOTO PRINTERS_CATALOG.pdf",
    "dye_sublimation": "DYE SUBLIMATION PRINTERS_CATALOG.pdf",
    "scanners": "PROFESSIONAL SCANNERS_CATALOG.pdf",
}

APPROVED_CATEGORIES = {
    "office_printer",
    "technical_large_format",
    "photography_large_format",
    "citizen_photo",
    "dye_sublimation",
    "scanners",
}

APPROVED_PRODUCT_LINES = {
    "workforce_pro",
    "workforce_enterprise",
    "surecolor_t",
    "surecolor_p",
    "surecolor_f",
    "citizen",
    "workforce_scanner",
    "expression",
}

EXPECTED_CATALOGUE_COUNT = 72


class CatalogueIntegrityError(Exception):
    """Raised when the catalogue fails integrity validation."""
    pass


class CatalogueLoader:
    def __init__(self, catalogue_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent / "data"
        self.catalogue_path = Path(catalogue_path) if catalogue_path else base_dir / "catalogue_products.json"
        self.products: List[Dict] = []
        self.products_by_id: Dict[str, Dict] = {}
        self.approved_ids: Set[str] = set()
        self.load_and_validate()

    def load_and_validate(self):
        """Loads and asserts startup integrity check for exactly 41 approved catalogue entries."""
        if not self.catalogue_path.exists():
            raise CatalogueIntegrityError(f"Catalogue file not found at {self.catalogue_path}")

        try:
            with open(self.catalogue_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CatalogueIntegrityError(f"Failed to parse catalogue JSON: {e}")

        if not isinstance(data, list):
            raise CatalogueIntegrityError("Catalogue data must be a list of product entries.")

        if len(data) != EXPECTED_CATALOGUE_COUNT:
            raise CatalogueIntegrityError(
                f"Catalogue integrity check failed: expected exactly {EXPECTED_CATALOGUE_COUNT} entries, found {len(data)}"
            )

        seen_ids = set()
        active_count = 0

        for p in data:
            pid = p.get("id")
            if not pid or pid in seen_ids:
                raise CatalogueIntegrityError(f"Duplicate or missing product ID: '{pid}'")
            seen_ids.add(pid)

            cat = p.get("catalogue")
            if cat not in APPROVED_CATALOGUES:
                raise CatalogueIntegrityError(f"Product '{pid}' has invalid catalogue '{cat}'")

            source_pdf = p.get("source_catalogue")
            if source_pdf != APPROVED_CATALOGUES[cat]:
                raise CatalogueIntegrityError(
                    f"Product '{pid}' source catalogue '{source_pdf}' does not match expected '{APPROVED_CATALOGUES[cat]}'"
                )

            if p.get("catalogue_verified") is not True:
                raise CatalogueIntegrityError(f"Product '{pid}' must have catalogue_verified=True")

            prod_line = p.get("product_line")
            if prod_line not in APPROVED_PRODUCT_LINES:
                raise CatalogueIntegrityError(
                    f"Product '{pid}' has invalid or missing product_line '{prod_line}'"
                )

            if p.get("active") is True:
                active_count += 1

        if active_count != EXPECTED_CATALOGUE_COUNT:
            raise CatalogueIntegrityError(
                f"Expected exactly {EXPECTED_CATALOGUE_COUNT} active entries, found {active_count}"
            )

        # Normalize: ensure every product has `name` and `model` fields so
        # downstream code doing p.get("name") or p.get("model") never gets None.
        for p in data:
            if not p.get("name"):
                p["name"] = p.get("display_name") or p.get("model_family") or p.get("id") or "Unknown"
            if not p.get("model"):
                p["model"] = p.get("model_family") or p.get("display_name") or p.get("id") or "Unknown"

        self.products = data
        self.products_by_id = {p["id"]: p for p in data}
        self.approved_ids = set(self.products_by_id.keys())
        logger.info(f"CatalogueLoader initialized with {len(self.products)} verified catalogue products.")
        return self.products

    def get_all(self) -> List[Dict]:
        return list(self.products)

    def get_by_id(self, product_id: str) -> Optional[Dict]:
        return self.products_by_id.get(product_id)

    def get_by_category(self, category: str) -> List[Dict]:
        cat_lower = category.lower().replace("-", "_").replace(" ", "_")
        matches = []
        for p in self.products:
            c = str(p.get("category") or p.get("main_category") or p.get("catalogue") or "").lower()
            if cat_lower in c or c in cat_lower:
                matches.append(p)
        return matches

    def is_approved_id(self, product_id: str) -> bool:
        return product_id in self.approved_ids


catalogue_loader = CatalogueLoader()
