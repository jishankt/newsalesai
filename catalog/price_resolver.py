"""
Verified Price Resolver for Kepler Tech Conversational AI.
Loads verified list prices from data/verified_prices.json and attaches
official standard rates (in AED) to all product and consumable cards.
"""

import json
import os
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("catalog.price_resolver")

PRICES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "verified_prices.json")


class PriceResolver:
    def __init__(self, json_path: str = PRICES_PATH):
        self.json_path = json_path
        self.prices: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self.prices = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load {self.json_path}: {e}")

    def get_price_info(self, identifier: Optional[str] = None, prod: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Resolves verified price info for a product or consumable.
        Returns dict with:
          - price: float or None
          - currency: "AED"
          - price_str: formatted string (e.g. "AED 4,385.00" or "Price on Request")
          - vat_note: "(Excl. VAT)" or ""
          - is_request: bool
        """
        candidates = []
        if identifier:
            candidates.append(str(identifier).strip())
        if prod:
            for k in ["id", "sku", "_id", "name", "title", "model"]:
                v = prod.get(k)
                if v:
                    candidates.append(str(v).strip())

        # Check if item is a consumable, media, paper, ink, or accessory
        is_consumable = False
        if prod:
            cat = str(prod.get("category", "")).lower()
            name_l = str(prod.get("name", "")).lower()
            if any(k in cat for k in ["media", "paper", "ink", "cartridge", "consumable", "maintenance", "accessory", "bag", "pen"]) or \
               any(k in name_l for k in ["media", "paper", "ribbon", "cleaning pen", "ink pack", "maintenance box", "carry bag", "bag"]):
                is_consumable = True

        # Check website price fetcher for hardware printers first
        if not is_consumable:
            try:
                from catalog.website_price_fetcher import website_price_fetcher
                wp_info = website_price_fetcher.get_price(identifier=identifier, prod=prod)
                if wp_info and (wp_info.get("price") or wp_info.get("is_cached")):
                    return wp_info
            except Exception as e:
                logger.debug(f"WebsitePriceFetcher lookup failed: {e}")

        # Check against verified prices database
        PRINTER_KEYS = [
            "citizen-cx-02", "citizen-cy-02", "citizen-cz-01", "citizen-cx-02w",
            "epson-t3100", "epson-t5100", "epson-am-c4000", "epson-am-c550",
            "epson-sc-t3100", "epson-sc-t5100", "epson-sc-p700", "epson-sc-p900",
            "epson-p700", "epson-p900", "epson-sc-f100", "epson-f100", "epson-sc-f500",
            "epson-wf-c5890-dwf", "epson-wf-c5890", "epson-wf-c878r-dwf", "epson-wf-c878r",
            "epson-wf-c879r-dwf", "epson-wf-c879r"
        ]

        for c in candidates:
            c_norm = re.sub(r"[\s\-_]+", "", c.lower())
            
            # 1. Exact ID match in verified prices
            if c.lower() in self.prices:
                item = self.prices[c.lower()]
                # If item is consumable, don't match printer prices
                if is_consumable and c.lower() in PRINTER_KEYS:
                    continue
                return self._build_info(item)

            # 1b. Normalized exact key match (handles e.g. "cx2w812" -> "cx2w 812", "c13t47a100")
            for pid, item in self.prices.items():
                pid_norm = re.sub(r"[\s\-_]+", "", pid.lower())
                if c_norm == pid_norm:
                    if is_consumable and pid in PRINTER_KEYS:
                        continue
                    return self._build_info(item)

            # Consumables should never match hardware printer model patterns
            if is_consumable:
                continue

            # 2. Normalized match for hardware
            for pid, item in self.prices.items():
                pid_norm = re.sub(r"[\s\-_]+", "", pid.lower())
                if c_norm == pid_norm or c_norm in pid_norm or pid_norm in c_norm:
                    return self._build_info(item)
                
                # Check specific model tokens
                if pid == "citizen-cx-02" and ("cx02" in c_norm and "w" not in c_norm):
                    return self._build_info(item)
                elif pid == "citizen-cy-02" and "cy02" in c_norm:
                    return self._build_info(item)
                elif pid == "citizen-cz-01" and "cz01" in c_norm:
                    return self._build_info(item)
                elif pid == "citizen-cx-02w" and ("cx02w" in c_norm or "cx-02w" in c.lower()):
                    return self._build_info(item)
                elif pid in ("epson-p700", "epson-sc-p700") and "p700" in c_norm and "7000" not in c_norm and "7500" not in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-p900-roll", "epson-sc-p900-roll") and "p900" in c_norm and "roll" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-p900", "epson-sc-p900") and "p900" in c_norm and "9000" not in c_norm and "9500" not in c_norm and "roll" not in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-t3100", "epson-sc-t3100") and "t3100" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-t5100", "epson-sc-t5100") and "t5100" in c_norm and "m" not in c_norm:
                    return self._build_info(item)
                elif pid == "epson-t5400m" and ("t5400" in c_norm or "t5100m" in c_norm):
                    return self._build_info(item)
                elif pid == "epson-t5700d" and "t5700" in c_norm:
                    return self._build_info(item)
                elif pid == "epson-am-c4000" and "c4000" in c_norm:
                    return self._build_info(item)
                elif pid == "epson-am-c550" and "c550" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-sc-f100", "epson-f100") and "f100" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-sc-f500", "epson-f500") and "f500" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-wf-c5890-dwf", "epson-wf-c5890") and "c5890" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-wf-c878r-dwf", "epson-wf-c878r") and "c878" in c_norm:
                    return self._build_info(item)
                elif pid in ("epson-wf-c879r-dtwf", "epson-wf-c879r-dwf", "epson-wf-c879r") and "c879" in c_norm:
                    return self._build_info(item)
                elif pid == "epson-p7500" and ("p7500" in c_norm or "p9500" in c_norm):
                    return self._build_info(item)

        # Fallback to prod dict if available
        if prod:
            p_val = prod.get("price")
            if p_val is not None:
                try:
                    price_flt = float(p_val)
                    # Media/consumables should not inherit scraped printer prices (>= 2500 AED)
                    if is_consumable and price_flt >= 2500:
                        price_flt = 0.0
                    if price_flt > 0:
                        return {
                            "price": price_flt,
                            "currency": "AED",
                            "price_str": f"AED {price_flt:,.2f}",
                            "vat_note": "(Excl. VAT)",
                            "is_request": False,
                        }
                except (ValueError, TypeError):
                    pass

        return {
            "price": None,
            "currency": "AED",
            "price_str": "Price on Request",
            "vat_note": "",
            "is_request": True,
        }

    def _build_info(self, item: Dict[str, Any]) -> Dict[str, Any]:
        p = item.get("price", 0.0)
        p_str = item.get("price_str")
        is_request = (p <= 0.0) or (p_str == "Price on Request")
        if not p_str:
            p_str = f"AED {p:,.2f}" if not is_request else "Price on Request"
        
        return {
            "price": p if not is_request else None,
            "currency": item.get("currency", "AED"),
            "price_str": p_str,
            "vat_note": "(Excl. VAT)" if not is_request else "",
            "is_request": is_request,
            "url": item.get("url", "")
        }


price_resolver = PriceResolver()
