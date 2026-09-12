"""
Deterministic Catalogue Filter for Kepler Tech SalesAI.
Filters and ranks products from the 41 approved catalogue entries.
Enforces:
1. catalogue_verified == True
2. active == True
3. Approved catalogue membership
4. Main category
5. Subcategory match
6. Mandatory hard requirements (paper_size, print_width, photo sizes, colour_mode, scanner, etc.)
7. Optional hard requirements (e.g. dual_roll, spectro if required)
8. Deduplication / configuration grouping (SC-P900, SC-P7500, SC-P9500)
9. Soft ranking (ordering only, never removing eligible items)
10. Complete matching list return (return ranked_products)
"""
import logging
from typing import Dict, List, Any, Optional, Tuple
from catalog.catalogue_loader import catalogue_loader, APPROVED_CATALOGUES

logger = logging.getLogger("catalog:filter")

SUBCATEGORY_LABELS = {
    "a4_colour_multifunction": ("Office Enterprise", "A4 Colour Multifunction"),
    "a3_workforce_pro_multifunction": ("Office Enterprise", "A3 WorkForce Pro Multifunction"),
    "a3_enterprise_multifunction": ("Office Enterprise", "A3 Enterprise Multifunction"),
    "technical_24_print_only": ("Technical Large Format", "24-inch Print-Only"),
    "technical_36_print_only": ("Technical Large Format", "36-inch Print-Only"),
    "technical_36_multifunction": ("Technical Large Format", "36-inch Multifunction"),
    "technical_44_print_only": ("Technical Large Format", "44-inch Print-Only"),
    "technical_44_multifunction": ("Technical Large Format", "44-inch Multifunction"),
    "photo_13_desktop": ("Photography & Fine Art", "13-inch Desktop Photo"),
    "photo_17_desktop": ("Photography & Fine Art", "17-inch Desktop Photo"),
    "photo_24_professional": ("Photography & Fine Art", "24-inch Professional Photo"),
    "photo_44_professional": ("Photography & Fine Art", "44-inch Professional Photo"),
    "photo_64_production": ("Photography & Fine Art", "64-inch Production Photo"),
    "citizen_4_inch": ("Citizen Photo", "4-inch Compact Photo"),
    "citizen_6_inch": ("Citizen Photo", "6-inch Event Photo"),
    "citizen_8_inch": ("Citizen Photo", "8-inch Wide Event Photo"),
    "dye_sublimation_desktop": ("Dye Sublimation", "Desktop Dye-Sub Printer"),
}

# Explicit configuration relationship groupings: (model_family, base_id, variant_id, variant_trigger_key)
CONFIG_GROUPS = {
    "SC-P900": {
        "base_id": "epson-sc-p900",
        "variant_id": "epson-sc-p900-roll",
        "trigger": "roll_printing_required",
        "config_name": "Roll Adapter",
        "all_configs": ["Standard", "Roll Adapter"]
    },
    "SC-P7500": {
        "base_id": "epson-sc-p7500",
        "variant_id": "epson-sc-p7500-spectro",
        "trigger": "spectro_required",
        "config_name": "Spectro",
        "all_configs": ["Standard", "Spectro"]
    },
    "SC-P9500": {
        "base_id": "epson-sc-p9500",
        "variant_id": "epson-sc-p9500-spectro",
        "trigger": "spectro_required",
        "config_name": "Spectro",
        "all_configs": ["Standard", "Spectro"]
    }
}


class CatalogueFilter:
    def filter_products(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Convenience method accepting requirements dict."""
        cat = requirements.get("main_category") or requirements.get("category") or requirements.get("catalogue")
        sub = requirements.get("subcategory")
        cards, no_match = self.filter_and_rank(cat, sub, requirements)
        return {
            "ranked_products": cards,
            "no_match": no_match
        }

    def filter_and_rank(
        self,
        category: Optional[str],
        subcategory: Optional[str],
        requirements: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Applies hard filters and soft ranking to the 41 catalogue entries.
        Returns:
            (formatted_cards, no_match_dict_if_empty)
        """
        all_products = catalogue_loader.get_all()

        # 1-3. Basic validity
        valid_products = [
            p for p in all_products
            if p.get("catalogue_verified") is True
            and p.get("active") is True
            and p.get("catalogue") in APPROVED_CATALOGUES
        ]

        # 4. Main category filter
        if category:
            cat_l = category.lower()
            cat_filtered = [
                p for p in valid_products
                if p.get("main_category") == cat_l
                or p.get("catalogue") == cat_l
                or (cat_l in ("office_printer", "business_a4", "business_a3") and p.get("catalogue") in ("business_a4", "business_a3"))
                or (cat_l in ("photography_large_format", "photography_and_fine_art") and p.get("catalogue") == "photography_and_fine_art")
                or (cat_l in ("technical_large_format", "technical_cad") and p.get("catalogue") == "technical_large_format")
                or (cat_l in ("citizen_photo", "citizen") and p.get("catalogue") == "citizen_photo")
            ]
        else:
            cat_filtered = valid_products

        # 5. Subcategory filter
        if subcategory:
            filtered = [p for p in cat_filtered if p.get("subcategory") == subcategory]
        else:
            filtered = cat_filtered

        # 6. Mandatory Hard Requirements
        candidates = []
        blocking_reasons = []

        for p in filtered:
            is_match = True
            reasons = []

            # Print Width / Paper Size Gate
            req_width = requirements.get("print_width")
            if req_width is None and isinstance(requirements.get("paper_size"), (int, float)):
                req_width = float(requirements["paper_size"])
            elif req_width is None and str(requirements.get("paper_size", "")).lower() in ("a3+", "13-inch", "13"):
                req_width = 13
            elif req_width is None and str(requirements.get("paper_size", "")).lower() in ("a2", "a2+", "17-inch", "17"):
                req_width = 17

            if req_width is not None and p.get("max_width_inches") is not None:
                if p["max_width_inches"] != float(req_width):
                    is_match = False
                    reasons.append(f"print width {p['max_width_inches']}\" != required {req_width}\"")

            # Scanner Gate
            req_scan = requirements.get("scanner_required")
            if req_scan is not None:
                p_scan = bool(p.get("scanner_integrated"))
                if req_scan is True and not p_scan:
                    is_match = False
                    reasons.append("lacks integrated scanner")
                elif req_scan is False and p_scan:
                    is_match = False
                    reasons.append("includes scanner (print-only requested)")

            # Functions Gate (e.g. ["print", "scan", "copy"] or "multifunction")
            req_funcs = requirements.get("functions") or requirements.get("function")
            if req_funcs:
                if isinstance(req_funcs, str):
                    req_funcs_list = [req_funcs]
                else:
                    req_funcs_list = list(req_funcs)
                p_funcs = p.get("functions") or []
                for f in req_funcs_list:
                    f_l = f.lower()
                    if f_l in ("scan", "copy", "multifunction", "mfp") and not p.get("scanner_integrated"):
                        is_match = False
                        reasons.append(f"lacks {f} function")

            # Paper Size Gate (A4, A3, etc.)
            req_size = requirements.get("paper_size")
            if req_size and not isinstance(req_size, (int, float)):
                sz_lower = str(req_size).lower()
                p_sizes = [str(s).lower() for s in (p.get("supported_print_sizes") or [])]
                if sz_lower in ("a3", "tabloid"):
                    if p.get("paper_size") != "a3" and "a3" not in p_sizes and (p.get("max_width_inches") or 0) < 13:
                        is_match = False
                        reasons.append("does not support A3 size")
                elif sz_lower == "a4":
                    if p.get("paper_size") != "a4" and p.get("catalogue") != "business_a4":
                        is_match = False
                        reasons.append("does not support A4 size")

            # Explicit Product Line Gate (Priority: Hard filter never overridden by volume)
            req_prod_line = requirements.get("product_line") or requirements.get("series")
            if req_prod_line and req_prod_line != "unspecified":
                p_prod_line = p.get("product_line")
                if p_prod_line != req_prod_line:
                    is_match = False
                    reasons.append(f"product line '{p_prod_line}' != requested '{req_prod_line}'")

            # Photo Print Sizes Gate (Citizen)
            req_photo_size = requirements.get("print_size") or requirements.get("print_sizes")
            if req_photo_size and (p.get("main_category") == "citizen_photo" or p.get("catalogue") == "citizen_photo"):
                if isinstance(req_photo_size, (list, set, tuple)):
                    req_photo_sizes = list(req_photo_size)
                else:
                    req_photo_sizes = [str(req_photo_size)]
                p_photo_sizes = [pps.lower().replace(" ", "") for pps in (p.get("supported_print_sizes") or [])]
                for rps in req_photo_sizes:
                    rps_clean = str(rps).lower().replace(" ", "")
                    if not any(rps_clean in pps for pps in p_photo_sizes):
                        is_match = False
                        reasons.append(f"does not support photo size {rps}")

            # 7. Optional Hard Requirements explicitly requested
            if requirements.get("dual_roll_required") is True:
                if not p.get("dual_roll"):
                    is_match = False
                    reasons.append("lacks dual roll support")

            if requirements.get("spectro_required") is True:
                if not p.get("spectro"):
                    is_match = False
                    reasons.append("lacks spectrophotometer")

            if requirements.get("high_capacity_required") is True:
                if p.get("catalogue") == "citizen_photo" or p.get("main_category") == "citizen_photo":
                    if p.get("id") != "citizen-cy-02":
                        is_match = False
                        reasons.append("not high media capacity model")

            if is_match:
                candidates.append(p)
            else:
                blocking_reasons.extend(reasons)

        # ── Step 11: Handle No-Match Safely ─────────────────────────────────
        if not candidates:
            distinct_blocking = list(dict.fromkeys(blocking_reasons))[:3]
            relaxation_q = self._build_relaxation_question(category, requirements, distinct_blocking)
            no_match = {
                "type": "no_exact_match",
                "message": "I couldn’t find a catalogue printer matching all those requirements.",
                "cards": [],
                "blocking_requirements": distinct_blocking,
                "relaxation_question": relaxation_q
            }
            return [], no_match

        # ── 8. Deduplication / Configuration Grouping ───────────────────────
        deduped = self._group_configurations(candidates, requirements)

        # ── 9. Soft Ranking ─────────────────────────────────────────────────
        ranked_products = self._soft_rank(deduped, requirements)

        # ── Format Cards into Schema ────────────────────────────────────────
        cards = [self._format_card(p, subcategory or p.get("subcategory"), requirements) for p in ranked_products]

        return cards, None

    def _group_configurations(self, products: List[Dict[str, Any]], requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Groups related configuration entries (SC-P900, SC-P7500, SC-P9500)
        unless an explicit requirement demands the specific variant.
        """
        output = []
        skip_ids = set()

        for p in products:
            pid = p["id"]
            if pid in skip_ids:
                continue

            fam = p.get("model_family")
            if fam in CONFIG_GROUPS:
                cfg_info = CONFIG_GROUPS[fam]
                trigger_key = cfg_info["trigger"]
                is_trigger_active = bool(requirements.get(trigger_key))

                # Check if both base and variant are in the candidate set
                base_in_candidates = any(c["id"] == cfg_info["base_id"] for c in products)
                var_in_candidates = any(c["id"] == cfg_info["variant_id"] for c in products)

                if base_in_candidates and var_in_candidates:
                    if is_trigger_active:
                        # Prioritize variant
                        if pid == cfg_info["variant_id"]:
                            output.append(p)
                            skip_ids.add(cfg_info["base_id"])
                        else:
                            # Skip base, let variant be picked
                            continue
                    else:
                        # Prioritize base model with available_configurations field
                        if pid == cfg_info["base_id"]:
                            p_copy = dict(p)
                            p_copy["available_configurations"] = cfg_info["all_configs"]
                            output.append(p_copy)
                            skip_ids.add(cfg_info["variant_id"])
                        else:
                            continue
                else:
                    output.append(p)
            else:
                output.append(p)

        return output

    def _soft_rank(self, products: List[Dict[str, Any]], requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Soft-ranks products based on stated preferences (volume, dual-roll, etc.)
        Orders results without deleting any eligible item.
        """
        def score(p: Dict[str, Any]) -> int:
            s = 0
            # Preferred dual roll
            if requirements.get("dual_roll_required") and p.get("dual_roll"):
                s += 10
            # Preferred spectro
            if requirements.get("spectro_required") and p.get("spectro"):
                s += 10
            # Volume match
            daily_vol = requirements.get("daily_volume")
            if daily_vol:
                try:
                    vol_int = int(daily_vol)
                    monthly_est = vol_int * 25
                    p_min = p.get("recommended_monthly_min") or 0
                    p_max = p.get("recommended_monthly_max") or 100000
                    if p_min <= monthly_est <= p_max:
                        s += 5

                    # Office workload ranking
                    line = p.get("product_line")
                    if vol_int >= 150:
                        # Heavy / enterprise daily volume (>= 150 pages/day)
                        if line == "workforce_enterprise":
                            s += 15
                            if "550" in p.get("id", "") or "6000" in p.get("id", "") or "5000" in p.get("id", ""):
                                s += 5
                        elif line == "workforce_pro":
                            if monthly_est >= p_max:
                                s -= 5
                    elif vol_int < 100:
                        # Moderate / lower volume (< 100 pages/day)
                        if line == "workforce_pro":
                            s += 10
                except (ValueError, TypeError):
                    pass
            return s

        return sorted(products, key=score, reverse=True)

    def _format_card(self, p: Dict[str, Any], subcategory: Optional[str], requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Formats a catalogue product into the required Step 9 card payload."""
        sub_key = subcategory or p.get("subcategory") or ""
        cat_label, sub_label = SUBCATEGORY_LABELS.get(sub_key, (p.get("main_category", "").replace("_", " ").title(), sub_key.replace("_", " ").title()))

        # Match reasons (strictly requirements-based per Phase 12)
        match_reasons = []
        req_paper = str(requirements.get("paper_size", "")).lower()
        if "a3" in req_paper:
            match_reasons.append("Matches your requested A3 output")
        elif "a4" in req_paper:
            match_reasons.append("Matches your requested A4 output")

        req_width = requirements.get("print_width")
        if req_width is not None and p.get("max_width_inches") == float(req_width):
            match_reasons.append(f"Supports the requested {req_width:.0f}-inch width")

        req_scan = requirements.get("scanner_required")
        if req_scan is True and p.get("scanner_integrated"):
            match_reasons.append("Includes the integrated scanner you requested")
        elif req_scan is False and not p.get("scanner_integrated"):
            match_reasons.append("Print-only configuration as requested")

        req_line = requirements.get("product_line")
        if req_line == "workforce_pro" and "workforce_pro" in p.get("subcategory", ""):
            match_reasons.append("Belongs to the requested WorkForce Pro range")
        elif req_line == "workforce_enterprise" and "enterprise" in p.get("subcategory", ""):
            match_reasons.append("Belongs to the requested WorkForce Enterprise range")

        req_funcs = requirements.get("functions")
        if req_funcs and any(f in req_funcs for f in ["scan", "copy", "multifunction"]):
            if "Matches your requested A3 output" not in match_reasons and "Includes the integrated scanner you requested" not in match_reasons:
                match_reasons.append("Supports print, scan and copy")

        if requirements.get("dual_roll_required") is True and p.get("dual_roll"):
            match_reasons.append("Equipped with dual-roll media switching as requested")

        if requirements.get("spectro_required") is True and p.get("spectro"):
            match_reasons.append("Equipped with spectrophotometer for automated colour calibration")

        req_photo_sizes = requirements.get("print_sizes")
        if req_photo_sizes:
            sizes_list = [req_photo_sizes] if isinstance(req_photo_sizes, str) else list(req_photo_sizes)
            clean_s = " and ".join(sizes_list[:2])
            match_reasons.append(f"Supports your requested {clean_s} prints")

        if not match_reasons:
            match_reasons.append(f"Catalogue-certified model matching your {sub_label} requirements")

        # Key features
        key_features = []
        if p.get("colour_mode"):
            key_features.append(f"{p['colour_mode'].title()} printing")
        if p.get("functions"):
            key_features.append("/".join([f.title() for f in p["functions"]]))
        if p.get("source_catalogue"):
            key_features.append("Official Kepler Tech Catalogue Certified")

        return {
            "id": p["id"],
            "model": p["display_name"],
            "name": p["display_name"],
            "image_url": p.get("image_url") or "/static/images/printer-placeholder.svg",
            "product_url": p.get("product_url") or "https://www.keplertechllc.com/",
            "category": cat_label,
            "subcategory": sub_label,
            "configuration": p.get("configuration"),
            "available_configurations": p.get("available_configurations", []),
            "match_reasons": match_reasons,
            "key_features": key_features,
            "actions": [
                "View details",
                "Compare",
                "Select"
            ]
        }

    def _build_relaxation_question(self, category: str, requirements: Dict[str, Any], blocking: List[str]) -> str:
        """Constructs exactly one helpful relaxation question."""
        if category == "technical_large_format":
            if requirements.get("print_width") == 44 and requirements.get("scanner_required") is True:
                return "Would a 36-inch multifunction model like the SC-T5100M or SC-T5700DM work, or is 44-inch output mandatory?"
            if requirements.get("print_width") == 24 and requirements.get("scanner_required") is True:
                return "All 24-inch technical models are dedicated print-only. Would a 36-inch multifunction model (SC-T5100M) work for your space?"
            return "Would a 36-inch model work, or is 44-inch output mandatory?"

        if category == "citizen_photo":
            return "Would a 6-inch model (CX-02) work, or is the 8×10/8×12 format mandatory?"

        if category == "office_printer":
            req_line = requirements.get("product_line")
            if req_line == "workforce_pro":
                return "No WorkForce Pro model meets all those exact specifications. Would you like to consider the WorkForce Enterprise series or relax other requirements?"
            elif req_line == "workforce_enterprise":
                return "No WorkForce Enterprise model meets all those exact specifications. Would you like to consider the WorkForce Pro series or relax other requirements?"
            if str(requirements.get("paper_size", "")).lower() == "a3" and requirements.get("scanner_required") is False:
                return "All approved A3 office models in our catalogue are multifunction printers with integrated scanning and copying. Would a multifunction A3 model like the WF-C878R DWF work, or would you prefer a dedicated A4 print-only printer?"
            return "Would an A4 colour multifunction printer meet your requirements, or is A3 printing mandatory?"

        return "Would you be open to relaxing the size or multifunction requirement to view available catalogue options?"


catalogue_filter = CatalogueFilter()
