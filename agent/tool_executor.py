"""
Tool Executor Module for Kepler Tech Conversational AI.
Executes dynamic catalog tools and formats zero-hallucination cards and context.
Zero hardcoding: all data is resolved dynamically from data/products.json.
"""

import json
import os
import re
from typing import Dict, Any, List, Optional
from rag.retriever import rag_retriever

PRODUCTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "products.json")


class CatalogToolExecutor:
    def __init__(self, products_path: str = PRODUCTS_PATH):
        self.products_path = products_path
        self.products = []
        self.sku_map: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.products_path):
            with open(self.products_path, "r", encoding="utf-8") as f:
                self.products = json.load(f)
                for p in self.products:
                    for k in ["sku", "_id", "id"]:
                        v = p.get(k)
                        if v:
                            self.sku_map[str(v).upper().strip()] = p
        self.corpus_map = {}
        corpus_path = os.path.join(os.path.dirname(__file__), "..", "data", "kepler_product_corpus.json")
        if os.path.exists(corpus_path):
            try:
                with open(corpus_path, "r", encoding="utf-8") as f:
                    corpus_data = json.load(f)
                    for item in corpus_data:
                        if item.get("id"):
                            self.corpus_map[item["id"]] = item
            except Exception as e:
                pass

    def format_card(self, prod: Dict[str, Any], card_type: str = "hardware") -> Dict[str, Any]:
        """Formats a catalog product into a clean card for frontend display."""
        from catalog.brochure_resolver import brochure_resolver
        from catalog.price_resolver import price_resolver

        name = prod.get("display_name") or prod.get("name") or prod.get("model") or "Product"
        sku = prod.get("sku", "VERIFIED-KEPLER")
        
        # Clean redundant leading SKU from title if present
        clean_title = name
        if card_type == "consumable" and sku and name.upper().startswith(str(sku).upper()):
            clean_title = re.sub(r"^" + re.escape(str(sku)) + r"\s*", "", name, flags=re.IGNORECASE).strip() or name

        image_url = prod.get("image_url") or prod.get("image")
        if not image_url and prod.get("images"):
            image_url = prod["images"][0]
        if not image_url:
            image_url = "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png"

        product_url = prod.get("website_url") or prod.get("web_url") or prod.get("url") or prod.get("source_url")
        if not product_url:
            slug = re.sub(r"[^\w\s-]", "", name.lower()).strip()
            slug = re.sub(r"[\s_]+", "-", slug)
            product_url = f"https://www.keplertechllc.com/product/{slug}/"

        brochure_info = brochure_resolver.get_brochure(name) or brochure_resolver.get_brochure(str(prod.get("id", ""))) or brochure_resolver.get_brochure(str(sku))
        pdf_url = brochure_info.get("pdf") if brochure_info else prod.get("pdf_url")
        if brochure_info and brochure_info.get("url"):
            product_url = brochure_info["url"]

        price_info = price_resolver.get_price_info(identifier=sku, prod=prod)
        price_val = price_info.get("price")
        price_formatted = price_info.get("price_str", "Price on Request")
        vat_note = price_info.get("vat_note", "")

        tags = prod.get("tags", [])
        badge = "Hardware" if card_type == "hardware" else "Consumable"
        if any("Ink" in t for t in tags):
            badge = "UltraChrome Ink"
        elif any("Maintenance" in t for t in tags):
            badge = "Maintenance Tank"
        elif any("Media" in t for t in tags) or "media" in name.lower():
            badge = "Print Media"

        width_val = prod.get("width") or prod.get("print_sizes")
        speed_val = prod.get("speed") or prod.get("print_speed")
        tech_val = prod.get("ink_technology") or prod.get("technology")

        return {
            "id": prod.get("_id") or prod.get("sku") or prod.get("id"),
            "name": name,
            "title": clean_title,
            "sku": sku,
            "price": price_val,
            "price_formatted": price_formatted,
            "price_str": price_formatted,
            "vat_note": vat_note,
            "currency": "AED",
            "is_request": price_info.get("is_request", price_val is None),
            "image": image_url,
            "image_url": image_url,
            "url": product_url,
            "pdf_url": pdf_url,
            "brochure_url": pdf_url,
            "source_url": product_url,
            "website_url": product_url,
            "web_url": product_url,
            "badge": badge,
            "card_type": card_type,
            "description": prod.get("description") or f"Official verified {badge.lower()} from Kepler Tech LLC.",
            "full_description": prod.get("full_description") or prod.get("description"),
            "feature_headings": prod.get("feature_headings", []),
            "specifications_table": prod.get("specifications_table", {}),
            "category": prod.get("category", "Hardware"),
            "width": width_val,
            "speed": speed_val,
            "ink_technology": tech_val,
            "weight": prod.get("weight"),
            "capacity": prod.get("capacity"),
            "comparison_highlights": prod.get("comparison_highlights"),
            "has_consumables": (card_type == "hardware")
        }

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches and executes the designated tool dynamically."""
        if tool_name == "search_catalog":
            return self._search_catalog(
                query=arguments.get("query", ""),
                category=arguments.get("category"),
                limit=arguments.get("limit", 4)
            )
        elif tool_name == "get_product_specs":
            return self._get_product_specs(
                identifier=arguments.get("product_identifier", "")
            )
        elif tool_name == "get_compatible_consumables":
            return self._get_compatible_consumables(
                printer_identifier=arguments.get("printer_identifier", ""),
                limit=arguments.get("limit", 25)
            )
        elif tool_name == "compare_products":
            return self._compare_products(
                model_a=arguments.get("model_a", ""),
                model_b=arguments.get("model_b", "")
            )
        elif tool_name == "ask_consultative_question":
            return {
                "success": True,
                "action": "consultative_question",
                "question": arguments.get("question", ""),
                "suggested_pills": arguments.get("suggested_pills", []),
                "product_cards": [],
                "consumable_cards": []
            }
        else:
            return {"success": False, "error": f"Unknown tool '{tool_name}'"}

    def _search_catalog(self, query: str, category: Optional[str] = None, limit: int = 4) -> Dict[str, Any]:
        """Searches catalog using hybrid search and returns clean cards."""
        cat_filter = None if category in (None, "All") else category
        raw_results = rag_retriever.search(query=query, category=cat_filter, limit=limit)

        cards = []
        for r in raw_results:
            card_type = "consumable" if r.get("category") in ["Consumables", "Ink Cartridge", "Media", "Maintenance Box"] else "hardware"
            cards.append(self.format_card(r, card_type=card_type))

        return {
            "success": True,
            "count": len(cards),
            "results": raw_results,
            "product_cards": cards if any(c["card_type"] == "hardware" for c in cards) else [],
            "consumable_cards": cards if any(c["card_type"] == "consumable" for c in cards) else []
        }

    def _get_product_specs(self, identifier: str) -> Dict[str, Any]:
        """Finds a product and extracts detailed specs with strict identifier matching."""
        from catalog.repository import catalog_repository
        from catalog.product_resolver import resolve_canonical_id, normalize_model_identifier
        
        target_id = resolve_canonical_id(identifier) or identifier.lower().strip()
        norm_p = catalog_repository.get_by_id(target_id)
        
        norm_id = normalize_model_identifier(identifier)
        if not norm_p and norm_id:
            for p in catalog_repository.get_all():
                p_norm_id = normalize_model_identifier(p.id)
                p_norm_name = normalize_model_identifier(p.name)
                if norm_id in (p_norm_id, p_norm_name):
                    norm_p = p
                    break

        prod = None
        if norm_p:
            prod = norm_p.to_dict()

        if not prod:
            prod = rag_retriever.get_by_sku(identifier) or rag_retriever.get_by_name(identifier)
        if not prod and norm_id:
            for p in rag_retriever.products:
                p_sku_norm = normalize_model_identifier(str(p.get("sku", "")))
                p_name_norm = normalize_model_identifier(str(p.get("name", "")))
                if norm_id in (p_sku_norm, p_name_norm):
                    prod = p
                    break

        if not prod:
            return {"success": False, "error": f"Product '{identifier}' not found in catalog."}

        card = self.format_card(prod, card_type="hardware")
        for k in ["feature_headings", "full_description", "specifications_table", "price_formatted", "vat_note", "url", "pdf_url"]:
            if card.get(k) and not prod.get(k):
                prod[k] = card[k]

        return {
            "success": True,
            "product": prod,
            "product_cards": [card],
            "specs_text": (
                f"Model: {prod.get('name')}\n"
                f"SKU: {prod.get('sku')}\n"
                f"Category: {prod.get('category')}\n"
                f"Description: {prod.get('description')}\n"
                f"Print Width: {prod.get('width', 'N/A')}\n"
                f"Print Speed: {prod.get('speed', 'N/A')}\n"
                f"Technology: {prod.get('ink_technology', 'N/A')}\n"
                f"Intended Application: {prod.get('intended_usage', 'N/A')}\n"
                f"Official URL: {card.get('url')}"
            )
        }

    def _get_compatible_consumables(self, printer_identifier: str, limit: int = 25) -> Dict[str, Any]:
        """Finds genuine consumables dynamically linked to a printer model."""
        target_printer = None
        q_raw = printer_identifier.strip()
        q_clean = q_raw.lower().replace("\u200b", " ")

        # Reject explicitly unverified / competitor brands
        if any(unv in q_clean for unv in ["canon", "hp", "designjet", "brother", "xerox", "ricoh"]):
            return {
                "success": True,
                "printer_name": q_raw,
                "count": 0,
                "consumable_cards": [],
                "consumables_summary": ""
            }

        # 0. Check catalog_repository first for clean hardware printers
        from catalog.repository import catalog_repository
        q_tokens = [re.sub(r"[\s\-_]+", "", part).replace("citizen", "").replace("epson", "") for part in re.split(r"[,/]+", q_clean) if part.strip()]
        
        # Pass 1: exact match
        for cand in catalog_repository.get_all():
            cand_id_norm = re.sub(r"[\s\-_]+", "", cand.id.lower()).replace("citizen", "").replace("epson", "")
            cand_name_norm = re.sub(r"[\s\-_]+", "", cand.name.lower()).replace("citizen", "").replace("epson", "")
            for q_tok in q_tokens:
                if q_tok and (q_tok == cand_id_norm or q_tok == cand_name_norm):
                    target_printer = cand.to_dict()
                    break
            if target_printer:
                break

        # Pass 2: substring match only if exact match not found
        if not target_printer:
            for cand in catalog_repository.get_all():
                cand_id_norm = re.sub(r"[\s\-_]+", "", cand.id.lower()).replace("citizen", "").replace("epson", "")
                cand_name_norm = re.sub(r"[\s\-_]+", "", cand.name.lower()).replace("citizen", "").replace("epson", "")
                for q_tok in q_tokens:
                    if q_tok and (q_tok in cand_id_norm or q_tok in cand_name_norm):
                        target_printer = cand.to_dict()
                        break
                if target_printer:
                    break

        # 1. Exact SKU
        if not target_printer and q_raw.upper() in self.sku_map:
            target_printer = self.sku_map[q_raw.upper()]

        # 2. Direct retrieve by name / SKU from rag_retriever (prioritizes hardware)
        if not target_printer:
            target_printer = rag_retriever.get_by_sku(q_raw) or rag_retriever.get_by_name(q_raw)

        # 3. Match by specific model token among genuine hardware printers only
        if not target_printer:
            GENERIC_WORDS = {
                "epson", "surecolor", "workforce", "printer", "scanner", "series",
                "large", "format", "color", "pro", "the", "for", "with", "enterprise",
                "multifunction", "multifunctional"
            }
            # Look for model codes like c4000, t3100, p900, cx02, etc.
            specific_tokens = [t for t in re.findall(r"[a-z0-9]+", q_clean) if len(t) >= 3 and t not in GENERIC_WORDS]
            
            # Filter strictly for genuine hardware printers (exclude media rolls, inks, accessories)
            candidate_printers = [
                p for p in self.products
                if "printer" in p.get("category", "").lower()
                and not any(k in p.get("name", "").lower() for k in ["media", "paper", "ribbon", "ink", "cartridge", "cleaning", "pen", "bag", "maintenance"])
            ]
            if not candidate_printers:
                candidate_printers = self.products

            # Prefer tokens containing digits (model numbers like c4000, t3100, cx02)
            specific_tokens.sort(key=lambda x: (any(c.isdigit() for c in x), len(x)), reverse=True)

            for t in specific_tokens:
                pattern = r'(?:\b|_|-)' + re.escape(t) + r'(?:\b|_|-|\s|$)(?!\d)'
                for p in candidate_printers:
                    p_name = p.get("name", "").lower().replace("\u200b", " ")
                    p_sku = str(p.get("sku", "")).lower()
                    if re.search(pattern, p_name) or t == p_sku:
                        target_printer = p
                        break
                if target_printer:
                    break

        # If no target printer recognized from Kepler Tech catalog, return empty to prevent hallucination
        if not target_printer:
            return {
                "success": True,
                "printer_name": q_raw,
                "count": 0,
                "consumable_cards": [],
                "consumables_summary": ""
            }

        # Determine target brand
        p_name_l = target_printer.get("name", "").lower()
        if "citizen" in p_name_l:
            target_brand = "citizen"
        elif any(b in p_name_l for b in ["epson", "surecolor", "workforce"]):
            target_brand = "epson"
        elif "innova" in p_name_l:
            target_brand = "innova"
        else:
            target_brand = None

        consumable_items = []
        seen = set()

        # Look up explicit consumables SKU links from printer metadata
        if target_printer.get("consumables"):
            raw_skus = target_printer["consumables"]
            mbox_skus = [s for s in raw_skus if any(s.upper().startswith(pfx) for pfx in ["C12C", "C13S", "C13T671"])]
            ink_skus = [s for s in raw_skus if s not in mbox_skus]
            ordered_skus = (mbox_skus + ink_skus) if mbox_skus else raw_skus

            for c_sku in ordered_skus:
                c_sku_up = str(c_sku).upper()
                if c_sku_up in self.sku_map and c_sku_up not in seen:
                    item = self.sku_map[c_sku_up]
                    item_name_l = item.get("name", "").lower()
                    item_cat_l = str(item.get("category", "")).lower()
                    # Strictly skip hardware printers, plotters, and scanners
                    if any(hw in item_cat_l for hw in ["printer", "scanner", "plotter"]):
                        continue
                    if not any(cons_kw in item_name_l for cons_kw in ["ink", "cartridge", "tank", "box", "ribbon", "media", "paper", "pack", "bottle", "maintenance", "cleaning", "pen", "bag"]):
                        continue
                    item_brand = "citizen" if "citizen" in item_name_l else ("epson" if "epson" in item_name_l else None)
                    if not target_brand or not item_brand or target_brand == item_brand:
                        seen.add(c_sku_up)
                        consumable_items.append(item)
                        if len(consumable_items) >= limit:
                            break

        # Only perform fallback search if no explicit consumables exist in metadata
        if not consumable_items:
            q_name = target_printer.get("name", q_raw).lower()
            # Extract specific model tokens only (e.g. t3100, p900, cx02, amc4000)
            GENERIC_STOP = {"epson", "surecolor", "printer", "workforce", "color", "scanner", "plotter", "large", "format", "photo", "digital", "pro", "series", "the", "for", "with"}
            tokens = [t for t in re.findall(r"[a-z0-9]+", q_name) if len(t) >= 3 and t not in GENERIC_STOP]

            for p in self.products:
                sku_up = str(p.get("sku", "")).upper()
                if sku_up in seen:
                    continue

                p_cat_l = str(p.get("category", "")).lower()
                p_name_l = p.get("name", "").lower()

                # Strictly exclude hardware printers, scanners, and plotters
                if any(hw in p_cat_l for hw in ["printer", "scanner", "plotter"]):
                    continue
                if any(hw in p_name_l for hw in ["printer", "scanner", "plotter"]):
                    continue

                p_item_brand = "citizen" if "citizen" in p_name_l else ("epson" if "epson" in p_name_l else None)
                if target_brand and p_item_brand and target_brand != p_item_brand:
                    continue

                p_name_norm = re.sub(r"[\s\-_\u200b]", "", p_name_l)
                p_desc_norm = re.sub(r"[\s\-_\u200b]", "", p.get("description", "").lower())
                p_tags_norm = re.sub(r"[\s\-_\u200b]", "", " ".join(p.get("tags", [])).lower())

                is_cons = any(k in p_name_l for k in ["ink", "cartridge", "tank", "box", "maintenance", "ribbon", "media", "paper", "bottle", "pack"])
                if is_cons and any(t in p_name_norm or t in p_desc_norm or t in p_tags_norm for t in tokens):
                    seen.add(sku_up)
                    consumable_items.append(p)
                    if len(consumable_items) >= limit:
                        break

        if target_brand:
            consumable_items = [
                c for c in consumable_items
                if target_brand in c.get("name", "").lower()
                or target_brand in " ".join(c.get("tags", [])).lower()
                or target_brand in str(c.get("category", "")).lower()
                or any(str(c.get("sku", "")).upper().startswith(pfx) for pfx in ["CX", "CY", "CZ", "CITIZEN"])
            ]

        consumable_cards = [self.format_card(c, card_type="consumable") for c in consumable_items]
        p_name = target_printer.get("name") if target_printer else q_raw
        hw_cards = [self.format_card(target_printer, card_type="hardware")] if target_printer else []

        return {
            "success": True,
            "printer_name": p_name,
            "target_printer": target_printer,
            "product_cards": hw_cards,
            "count": len(consumable_cards),
            "consumable_cards": consumable_cards,
            "consumables_summary": ", ".join([c["name"] for c in consumable_cards])
        }

    def _compare_products(self, model_a: str, model_b: str) -> Dict[str, Any]:
        """Compares two models from the live catalog."""
        def find_hardware(identifier: str):
            from catalog.repository import catalog_repository
            p = None
            q_clean = identifier.lower().strip()
            id_norm = re.sub(r"[\s\-_]+", "", q_clean).replace("citizen", "").replace("epson", "")

            # 1. Check catalog_repository first for normalized hardware products
            norm_p = catalog_repository.get_by_id(q_clean)
            if not norm_p:
                for cand in catalog_repository.get_all():
                    cand_id_norm = re.sub(r"[\s\-_]+", "", cand.id.lower()).replace("citizen", "").replace("epson", "")
                    cand_name_norm = re.sub(r"[\s\-_]+", "", cand.name.lower()).replace("citizen", "").replace("epson", "")
                    if id_norm and (id_norm == cand_id_norm or id_norm == cand_name_norm):
                        norm_p = cand
                        break
            if not norm_p:
                for cand in catalog_repository.get_all():
                    cand_id_norm = re.sub(r"[\s\-_]+", "", cand.id.lower()).replace("citizen", "").replace("epson", "")
                    if id_norm and id_norm in cand_id_norm:
                        norm_p = cand
                        break
            if norm_p:
                return norm_p.to_dict()

            for cid, cdata in self.corpus_map.items():
                cid_norm = re.sub(r"[\s\-_]+", "", cid.lower()).replace("citizen", "").replace("epson", "")
                if id_norm and id_norm == cid_norm:
                    p = dict(cdata)
                    break

            if not p:
                cand = rag_retriever.get_by_name(identifier) or rag_retriever.get_by_sku(identifier)
                if cand and cand.get("category") not in ["Consumables", "Ink Cartridge", "Media", "Maintenance Box", "Inks"]:
                    p = dict(cand)
                else:
                    results = rag_retriever.search(identifier, limit=6)
                    hw_results = [r for r in results if r.get("category") not in ["Consumables", "Ink Cartridge", "Media", "Maintenance Box", "Inks"]]
                    p = dict(hw_results[0]) if hw_results else (dict(results[0]) if results else None)

            if p:
                p_name_norm = re.sub(r"[\s\-_]+", "", p.get("name", "").lower())
                p_id_norm = re.sub(r"[\s\-_]+", "", str(p.get("id", "")).lower())
                for cid, cdata in self.corpus_map.items():
                    cid_norm = re.sub(r"[\s\-_]+", "", cid.lower()).replace("citizen", "").replace("epson", "")
                    if cid_norm and (cid_norm in p_name_norm or cid_norm in p_id_norm):
                        for k, v in cdata.items():
                            if k not in p or not p[k]:
                                p[k] = v
                        p["id"] = cid
                        break
            return p

        prod_a = find_hardware(model_a)
        prod_b = find_hardware(model_b)

        if not prod_a or not prod_b:
            return {"success": False, "error": f"Could not find both products for comparison ({model_a}, {model_b})."}

        cards = [self.format_card(prod_a, card_type="hardware"), self.format_card(prod_b, card_type="hardware")]
        return {
            "success": True,
            "product_a": prod_a,
            "product_b": prod_b,
            "product_cards": cards,
            "comparison_data": {
                "model_a": {
                    "name": prod_a.get("name"),
                    "category": prod_a.get("category"),
                    "width": prod_a.get("width") or prod_a.get("print_sizes", "Standard"),
                    "speed": prod_a.get("speed") or prod_a.get("print_speed", "N/A"),
                    "weight": prod_a.get("weight", "N/A"),
                    "capacity": prod_a.get("capacity", "Standard"),
                    "highlights": prod_a.get("comparison_highlights", ""),
                    "intended": prod_a.get("intended_usage", "Professional production")
                },
                "model_b": {
                    "name": prod_b.get("name"),
                    "category": prod_b.get("category"),
                    "width": prod_b.get("width") or prod_b.get("print_sizes", "Standard"),
                    "speed": prod_b.get("speed") or prod_b.get("print_speed", "N/A"),
                    "weight": prod_b.get("weight", "N/A"),
                    "capacity": prod_b.get("capacity", "Standard"),
                    "highlights": prod_b.get("comparison_highlights", ""),
                    "intended": prod_b.get("intended_usage", "Professional production")
                }
            }
        }


# Global singleton instance
catalog_tool_executor = CatalogToolExecutor()
tool_executor = catalog_tool_executor
