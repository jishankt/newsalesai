"""
Dynamic Consumables & Product Cards Engine for Kepler Tech LLC.
Zero hardcoding: all data, images, specifications, and compatibility links
are dynamically resolved directly from data/products.json via catalog_tool_executor.
"""

import os
import re
from typing import List, Dict, Optional, Any
from agent.tool_executor import catalog_tool_executor
from rag.retriever import rag_retriever

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "products.json")

# Backward-compatible proxy for legacy imports
VERIFIED_PRINTER_MAPPING = {}


class ConsumablesEngine:
    def __init__(self, catalog_path: str = PRODUCTS_FILE):
        self.catalog_path = catalog_path
        self.executor = catalog_tool_executor

    def identify_printer_key(self, query: str) -> Optional[str]:
        """Dynamically identifies hardware printer model code or token from user text."""
        STOP_WORDS = {
            "the", "printer", "scanner", "inks", "ink", "consumables", "consumable",
            "for", "with", "what", "need", "want", "buy", "get", "to", "a", "an", "some", "me", "give",
            "epson", "citizen", "surecolor", "workforce",
            "cartridge", "cartridges", "tank", "box", "maintenance",
            "yellow", "cyan", "magenta", "black", "matte", "photo", "grey", "gray", "violet", "orange", "green", "red", "color", "colours", "colors"
        }
        tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9\-]+", query) if len(t) >= 2]
        clean = [t for t in tokens if t not in STOP_WORDS]
        if clean:
            # Check if any token matches a hardware product in catalog first
            for t in clean:
                p = rag_retriever.get_by_sku(t) or rag_retriever.get_by_name(t)
                if p:
                    p_cat = p.get("category", "").lower()
                    if any(hw_kw in p_cat for hw_kw in ["printer", "scanner", "large format", "business"]):
                        return str(p.get("sku") or p.get("name"))
            # Fallback to any product match
            for t in clean:
                p = rag_retriever.get_by_sku(t) or rag_retriever.get_by_name(t)
                if p:
                    return str(p.get("sku") or p.get("name"))
            return clean[0]
        return None

    def find_matching_hardware(self, query: str, limit: int = 4) -> List[Dict[str, Any]]:
        """Finds genuine hardware items from the catalog matching the query."""
        res = self.executor.execute_tool("search_catalog", {"query": query, "category": "Printer", "limit": limit})
        cards = res.get("product_cards", [])
        if not cards:
            # Try search across all hardware
            res = self.executor.execute_tool("search_catalog", {"query": query, "limit": limit})
            cards = [c for c in res.get("product_cards", []) if c.get("card_type") == "hardware"]
        return cards

    def get_printer_consumables(self, printer_query: str, consumable_filter: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """
        Dynamically finds genuine compatible consumables for a given printer or scanner
        using the catalog relationship graph.
        """
        res = self.executor.execute_tool(
            "get_compatible_consumables",
            {"printer_identifier": printer_query, "limit": limit}
        )
        from routes.consumables_route import sort_consumables_inks_first
        cards = sort_consumables_inks_first(res.get("consumable_cards", []))
        if consumable_filter:
            cf_low = consumable_filter.lower()
            filtered = [c for c in cards if cf_low in c.get("badge", "").lower() or cf_low in c.get("name", "").lower()]
            if filtered:
                return filtered
        return cards

    def rank_candidates_from_state(self, state, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Ranks genuine catalog hardware candidates dynamically based on canonical conversation state.
        """
        search_terms = []
        cat_filter = None

        if state.category == "scanner":
            cat_filter = "Scanner"
            st = state.requirements.get("scanner_type")
            if st == "document_sheetfed":
                search_terms.append("DS-770 DS-790WN DS-870 DS-970 DS-900WN high speed network duplex document scanner")
            elif st == "flatbed_a3":
                search_terms.append("DS-32000 DS-30000 DS-60000 DS-70000 12000XL A3 large format flatbed scanner")
            elif st == "business":
                search_terms.append("DS-70 DS-80W DS-1630 DS-1660W DS-310 DS-410 compact business scanner")
            else:
                search_terms.append("document scanner")

        elif state.category == "photo_booth":
            cat_filter = "Printer"
            search_terms.append("Citizen photo printer CX CY CX-02 CY-02")

        elif state.category == "photo_fine_art":
            cat_filter = "Printer"
            search_terms.append("Epson SureColor P photo fine art printer P700 P900 P7500 P9500")

        elif state.category == "technical_cad":
            cat_filter = "Printer"
            size = state.requirements.get("print_size", "")
            scan = "MFP scanner T5400M T5700DM" if state.requirements.get("scan_required") else "plotter T3100 T5100"
            search_terms.append(f"Epson SureColor T CAD {size} {scan}")

        else:
            search_terms.append("Epson professional printer")

        query_str = " ".join(search_terms)
        res = self.executor.execute_tool(
            "search_catalog",
            {"query": query_str, "category": cat_filter, "limit": limit}
        )
        return res.get("product_cards", [])

    def _format_card(self, prod: dict, card_type: str = "hardware") -> dict:
        """Formats product into clean card."""
        return self.executor.format_card(prod, card_type=card_type)


# Singleton engine instance
consumables_engine = ConsumablesEngine()
