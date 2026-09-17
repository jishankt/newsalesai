"""
Website Price Fetcher & Cache Manager for Kepler Tech Conversational AI.
Extracts verified prices directly from keplertechllc.com using Schema.org JSON-LD
and WooCommerce product offers. Maintains a persistent local cache for fast sub-millisecond
chat responses, with on-demand and background refresh capabilities.
"""

import json
import os
import re
import logging
import urllib.request
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("catalog.website_price_fetcher")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CACHE_FILE = os.path.join(DATA_DIR, "website_prices_cache.json")
CATALOGUE_FILE = os.path.join(DATA_DIR, "catalogue_products.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 KeplerTechAI/1.0"
}


class WebsitePriceFetcher:
    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} entries from {self.cache_file}")
            except Exception as e:
                logger.error(f"Failed to load website price cache: {e}")
                self.cache = {}
        else:
            self.cache = {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.cache)} entries to {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to save website price cache: {e}")

    @staticmethod
    def extract_price_from_html(html: str) -> Tuple[Optional[float], str]:
        """
        Extracts price from product page HTML.
        Prioritizes Schema.org JSON-LD '@type': 'Product' offers to ensure
        we only get the main product's direct purchase rate, avoiding related items.
        """
        if not html:
            return None, "empty_html"

        # 1. Schema.org JSON-LD
        ld_matches = re.findall(r"<script type=\"application/ld\+json\">(.*?)</script>", html, re.DOTALL)
        for m in ld_matches:
            try:
                data = json.loads(m)
                items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [data])
                for it in items:
                    if isinstance(it, dict) and it.get("@type") == "Product":
                        offers = it.get("offers")
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict) and "price" in offers:
                            try:
                                p_val = float(offers["price"])
                                if p_val > 0:
                                    return p_val, "schema_product"
                            except (ValueError, TypeError):
                                pass
            except Exception:
                pass

        return None, "quote_only"

    def fetch_live_price(self, url: str, timeout: int = 8) -> Tuple[Optional[float], str]:
        """Fetches product page from Kepler Tech website and extracts the price."""
        if not url or not url.startswith("http"):
            return None, "invalid_url"

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                return self.extract_price_from_html(html)
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP Error {e.code} fetching {url}")
            return None, f"http_error_{e.code}"
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None, f"error_{str(e)[:40]}"

    def get_price(self, identifier: Optional[str] = None, prod: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retrieves pricing information for a given product or SKU.
        Returns:
            price: float or None
            currency: "AED"
            price_str: "AED X,XXX.00" or "Price on Request"
            vat_note: "(Excl. VAT)" or ""
            is_request: bool (True if not listed on site / quote-only)
            status: "published_on_site" | "quote_only"
            url: product website URL
        """
        candidates = []
        if identifier:
            candidates.append(str(identifier).strip())
        if prod:
            for k in ["id", "_id", "sku", "model", "name", "title"]:
                v = prod.get(k)
                if v:
                    candidates.append(str(v).strip())

        # Check in cache
        for c in candidates:
            c_lower = c.lower()
            c_norm = re.sub(r"[\s\-_]+", "", c_lower)

            # Direct key match
            if c_lower in self.cache:
                entry = self.cache[c_lower]
                return self._format_entry(entry, prod)

            # Normalized key match
            for k, entry in self.cache.items():
                k_norm = re.sub(r"[\s\-_]+", "", k.lower())
                if (c_norm == k_norm or 
                    (len(c_norm) >= 4 and c_norm in k_norm) or 
                    (len(k_norm) >= 4 and k_norm in c_norm) or
                    (c_norm.startswith("epson") and k_norm.startswith("epson") and c_norm.replace("sc", "") == k_norm.replace("sc", ""))):
                    return self._format_entry(entry, prod)

        # Fallback to product dictionary URL if provided and not in cache
        url = None
        if prod:
            url = prod.get("website_url") or prod.get("product_url") or prod.get("url")

        return {
            "price": None,
            "currency": "AED",
            "price_str": "Price on Request",
            "vat_note": "",
            "is_request": True,
            "status": "quote_only",
            "is_cached": False,
            "url": url or "https://www.keplertechllc.com/",
        }

    def _format_entry(self, entry: Dict[str, Any], prod: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        price = entry.get("price")
        url = entry.get("url")
        if not url and prod:
            url = prod.get("website_url") or prod.get("product_url") or prod.get("url")

        if price is not None and float(price) > 0:
            p_val = float(price)
            return {
                "price": p_val,
                "currency": entry.get("currency", "AED"),
                "price_str": f"AED {p_val:,.2f}",
                "vat_note": "(Excl. VAT)",
                "is_request": False,
                "status": "published_on_site",
                "is_cached": True,
                "url": url or "https://www.keplertechllc.com/",
            }
        else:
            return {
                "price": None,
                "currency": entry.get("currency", "AED"),
                "price_str": "Price on Request",
                "vat_note": "",
                "is_request": True,
                "status": "quote_only",
                "is_cached": True,
                "url": url or "https://www.keplertechllc.com/",
            }

    def sync_all_catalogue_prices(self):
        """Scrapes and populates the cache for all products in data/catalogue_products.json."""
        if not os.path.exists(CATALOGUE_FILE):
            logger.error(f"Catalogue file not found: {CATALOGUE_FILE}")
            return

        with open(CATALOGUE_FILE, "r", encoding="utf-8") as f:
            products = json.load(f)

        logger.info(f"Syncing prices for {len(products)} catalogue products...")
        from concurrent.futures import ThreadPoolExecutor

        def sync_one(p):
            pid = p.get("id")
            url = p.get("website_url") or p.get("product_url")
            price, method = self.fetch_live_price(url)
            return pid, {
                "price": price,
                "currency": "AED",
                "price_str": f"AED {price:,.2f}" if price else "Price on Request",
                "vat_note": "(Excl. VAT)" if price else "",
                "status": "published_on_site" if price else "quote_only",
                "method": method,
                "url": url or ""
            }

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(sync_one, products))

        for pid, data in results:
            self.cache[pid] = data
            # Also add model aliases
            p_obj = next((p for p in products if p.get("id") == pid), None)
            if p_obj:
                if p_obj.get("model"):
                    self.cache[p_obj["model"].lower()] = data
                if p_obj.get("name"):
                    self.cache[p_obj["name"].lower()] = data

        self._save_cache()
        logger.info(f"Completed price sync. Total cache entries: {len(self.cache)}")


website_price_fetcher = WebsitePriceFetcher()
