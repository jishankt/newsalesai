"""
Hard Eligibility Engine for Kepler Tech Catalog.
Enforces binary eligibility filtering:
  - Critical mismatches act as strict gates (FAILED -> excluded).
  - Unknown specifications are explicitly marked UNKNOWN (never assumed True or False).
  - True matches are marked MATCHED.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from catalog.schema import NormalizedProduct


@dataclass
class AssessmentResult:
    product: NormalizedProduct
    is_eligible: bool
    matched: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None


class EligibilityEngine:
    def assess(self, product: NormalizedProduct, requirements: Dict[str, Any]) -> AssessmentResult:
        return self.assess_product(product, requirements)

    def assess_product(self, product: NormalizedProduct, requirements: Dict[str, Any]) -> AssessmentResult:
        """
        Assesses whether a product satisfies all critical customer requirements.
        """
        matched = []
        failed = []
        unknown = []
        is_eligible = True
        rejection_reason = None

        specs = product.verified

        # ── 0. Hardware Type Gate ───────────────────────────────────────────
        if product.category in ("media_paper", "software", "consumable"):
            return AssessmentResult(
                product=product,
                is_eligible=False,
                failed=["hardware_type"],
                rejection_reason=f"Product is {product.category}, not a printing/scanning hardware device."
            )

        # ── 1. Print Size Gate ───────────────────────────────────────────────
        req_size = requirements.get("print_size")
        if req_size and product.category != "scanner":
            import re
            m_metric = re.search(r"\b(\d+(?:\.\d+)?)\s*(cm|m|meter|metre|metter|mm)\b", str(req_size).lower())
            if m_metric:
                val = float(m_metric.group(1))
                unit = m_metric.group(2)
                mm = val * 1000 if unit in ("m", "meter", "metre", "metter") else (val * 10 if unit == "cm" else val)
                if mm >= 841:
                    req_size = "A0"
                elif mm >= 594:
                    req_size = "A1"
                elif mm >= 420:
                    req_size = "A2"
                elif mm >= 297:
                    req_size = "A3+"
                elif mm >= 210:
                    req_size = "A4"

            supported_sizes = set(
                (product.supported_print_sizes or (specs.supported_print_sizes if specs else []) or [])
            )
            supported_sizes_lower = {str(s).strip().lower().replace("×", "x").replace('"', '').replace("inches", "").replace("inch", "").strip() for s in supported_sizes}

            # Check for photo dimension patterns (e.g. 4x6, 6x8, 5x7, 6x9, 8x10, 8x12, 4.5x8)
            photo_matches = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:x|×)\s*(\d+(?:\.\d+)?)\b", str(req_size).lower())
            if photo_matches:
                all_matched = True
                failed_sizes = []
                p_tech = ((specs.ink_technology if specs else None) or getattr(product, "technology", None) or "").lower()
                is_dye_sub = "dye" in p_tech or "sublimation" in p_tech or product.category in ("photo_booth", "promotional_dye_sub") or "citizen" in product.id.lower()

                for w_str, h_str in photo_matches:
                    target_pair1 = f"{w_str}x{h_str}".replace(" ", "")
                    target_pair2 = f"{h_str}x{w_str}".replace(" ", "")
                    
                    if target_pair1 in supported_sizes_lower or target_pair2 in supported_sizes_lower:
                        continue
                    
                    if (target_pair1 in ("2x6", "6x2") or target_pair2 in ("2x6", "6x2")) and product.id in ("citizen-cx-02", "citizen-cy-02"):
                        continue
                    
                    # Width alone must NEVER prove dye-sub media compatibility
                    if is_dye_sub:
                        all_matched = False
                        failed_sizes.append(target_pair1)
                    else:
                        # Non-dye-sub printers with no explicit photo media specs: check width
                        w_val = float(w_str)
                        h_val = float(h_str)
                        min_dim_mm = min(w_val, h_val) * 25.4
                        if specs.max_width_mm is not None and specs.max_width_mm >= min_dim_mm:
                            continue
                        all_matched = False
                        failed_sizes.append(target_pair1)

                if all_matched:
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Product does not support required photo print size(s): {', '.join(failed_sizes)}."

            elif req_size in ("A0", "36-inch"):
                if "a0" in supported_sizes_lower or "36-inch" in supported_sizes_lower or (specs.max_width_mm is not None and specs.max_width_mm >= 914):
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Maximum print width ({specs.max_width_label or specs.max_width_mm}) is smaller than required A0 (36-inch)."
            elif req_size in ("A1", "24-inch"):
                if "a1" in supported_sizes_lower or "24-inch" in supported_sizes_lower or (specs.max_width_mm is not None and specs.max_width_mm >= 610):
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Maximum print width ({specs.max_width_label or specs.max_width_mm}) is smaller than required A1 (24-inch)."
            elif req_size in ("A2+", "A2", "17-inch"):
                # A2 is 420mm (17 inches). Wide format roll/sheet printers with width >= 420mm support A2.
                if "a2" in supported_sizes_lower or "17-inch" in supported_sizes_lower or (specs.max_width_mm is not None and specs.max_width_mm >= 420):
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Product maximum width ({specs.max_width_label or specs.max_width_mm}) does not support A2 (17-inch) prints."
            elif req_size in ("A3+", "A3", "13-inch"):
                if "a3" in supported_sizes_lower or "a3+" in supported_sizes_lower or "13-inch" in supported_sizes_lower or (specs.max_width_mm is not None and specs.max_width_mm >= 329):
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Maximum print width ({specs.max_width_label or specs.max_width_mm}) is smaller than required A3 (13-inch)."
            elif req_size in ("A4", "A4 Desktop", "a4"):
                if "a4" in supported_sizes_lower or (specs.max_width_mm is not None and specs.max_width_mm >= 210) or (specs.max_width_label and "a4" in specs.max_width_label.lower()):
                    matched.append("print_size")
                else:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Maximum print width ({specs.max_width_label or specs.max_width_mm}) is smaller than required A4."
            elif any(s in str(req_size).lower() for s in ["compact desktop", "compact", "small", "desktop"]):
                # Compact desktop: Max 17 inches (432mm), e.g. P700 (13"), P900 (17"), CX-02, CZ-01
                # SC-P7500 (24", 610mm) and SC-P9500 (44", 1118mm) are floor-standing production large-format units!
                if specs.max_width_mm is not None and specs.max_width_mm > 432:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Product width ({specs.max_width_label or specs.max_width_mm}) is a large-format production unit, not a compact desktop."
                else:
                    matched.append("print_size")
            elif any(s in str(req_size).lower() for s in ["large format", "large-format", "large", "wide format", "production"]):
                # Large format: At least 24 inches (610mm), e.g. SC-P7500 (24"), SC-P9500 (44"), T3100 (24"), T5100 (36"), T5400M (36"), T5700D (36")
                # Compact desktop units like P700 (13") and P900 (17") must be rejected when large format is requested!
                if specs.max_width_mm is not None and specs.max_width_mm < 610:
                    failed.append("print_size")
                    is_eligible = False
                    rejection_reason = f"Product width ({specs.max_width_label or specs.max_width_mm}) is a compact desktop model, not large format (24\"+ required)."
                else:
                    matched.append("print_size")

        # ── 1b. Printing Technology Gate (Hard Constraint) ───────────────────
        req_tech = requirements.get("printing_technology")
        if req_tech:
            tech_lower = req_tech.lower()
            p_tech = ((specs.ink_technology if specs else None) or getattr(product, "technology", None) or "").lower()
            if "dye_sub" in tech_lower or "dye-sub" in tech_lower or "sublimation" in tech_lower:
                if "dye" in p_tech or "sublimation" in p_tech or product.category in ("photo_booth", "promotional_dye_sub"):
                    matched.append("printing_technology")
                else:
                    failed.append("printing_technology")
                    is_eligible = False
                    rejection_reason = f"Product uses {p_tech or 'inkjet'}, not dye-sublimation technology."
            elif "inkjet" in tech_lower or "pigment" in tech_lower:
                if "piezo" in p_tech or "precisioncore" in p_tech or "pigment" in p_tech or "ink" in p_tech or product.category in ("photo_fine_art", "technical_cad", "office_enterprise"):
                    matched.append("printing_technology")
                else:
                    failed.append("printing_technology")
                    is_eligible = False
                    rejection_reason = f"Product uses {p_tech or 'thermal transfer'}, not archival pigment inkjet technology."



        # ── 2. Scanner Gate (Strict logic) ───────────────────────────────────
        req_scan = requirements.get("scan_required")
        if req_scan is not None:
            is_scan_needed = req_scan is True or str(req_scan).lower() in ("true", "yes", "1")
            is_print_only = req_scan is False or str(req_scan).lower() in ("false", "no", "0")
            if is_scan_needed:
                if specs.has_scanner is True:
                    matched.append("scan_required")
                else:
                    failed.append("scan_required")
                    is_eligible = False
                    rejection_reason = "Product does not have an integrated scanner (customer requires scanning)."
            elif is_print_only:
                # Customer explicitly does NOT want a scanner (print-only requested)
                if specs.has_scanner is False or specs.has_scanner is None:
                    matched.append("scan_required")
                else:
                    failed.append("scan_required")
                    is_eligible = False
                    rejection_reason = "Product includes an integrated scanner (customer specified print only / no scanner)."

        # ── 2b. Scanner Type Gate ────────────────────────────────────────────
        req_scanner_type = requirements.get("scanner_type")
        if req_scanner_type and product.category == "scanner":
            p_name_lower = (product.name or "").lower()
            p_desc_lower = ((product.description or "") + " " + (product.comparison_highlights or "")).lower()
            is_flatbed_prod = "flatbed" in p_name_lower or "flatbed" in p_desc_lower or "12000xl" in product.id.lower()
            if req_scanner_type == "flatbed":
                if is_flatbed_prod:
                    matched.append("scanner_type")
                else:
                    failed.append("scanner_type")
                    is_eligible = False
                    rejection_reason = "Product is a sheetfed document scanner, not an A3 flatbed scanner."
            elif req_scanner_type == "sheetfed":
                if not is_flatbed_prod or "sheet-fed" in p_desc_lower or "sheetfed" in p_name_lower or "ds-1630" in product.id.lower():
                    matched.append("scanner_type")
                else:
                    failed.append("scanner_type")
                    is_eligible = False
                    rejection_reason = "Product is a specialized graphics flatbed scanner, not a sheetfed document scanner."

        # ── 3. Application Match ─────────────────────────────────────────────
        req_app = requirements.get("application")
        if req_app:
            if any(req_app.lower() in app.lower() for app in specs.applications):
                matched.append("application")

        # ── 4. Brand Gate ────────────────────────────────────────────────────
        req_brand = requirements.get("brand")
        if req_brand:
            p_brand = (product.brand or "").lower()
            p_name = (product.name or "").lower()
            if req_brand.lower() in p_brand or req_brand.lower() in p_name:
                matched.append("brand")
            else:
                failed.append("brand")
                is_eligible = False
                rejection_reason = f"Product brand ({product.brand}) does not match requested brand ({req_brand})."


        return AssessmentResult(
            product=product,
            is_eligible=is_eligible,
            matched=matched,
            failed=failed,
            unknown=unknown,
            rejection_reason=rejection_reason
        )

    def filter_candidates(self, products: List[NormalizedProduct], requirements: Dict[str, Any]) -> List[AssessmentResult]:
        results = []
        for p in products:
            res = self.assess_product(p, requirements)
            if res.is_eligible:
                results.append(res)
        return results


eligibility_engine = EligibilityEngine()
