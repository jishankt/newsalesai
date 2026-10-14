"""
RAG Retriever Module for Kepler Tech Product Corpus.
Dynamically indexes all 792 verified products in data/products.json without hardcoding.
Combines exact SKU / lexical token matching with TF-IDF semantic similarity and NLP entity boosting.
"""

import json
import os
import re
from typing import List, Dict, Optional, Any
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PRODUCTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "products.json")
CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "kepler_product_corpus.json")
CATALOGUE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "catalogue_products.json")
VERIFIED_PRICES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "verified_prices.json")
WEBSITE_PRICES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "website_prices_cache.json")
VERIFIED_BROCHURES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "verified_brochures.json")
COMPLETE_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sheets", "complete_training_corpus.json")

# Confidence thresholds for retrieval gating
EXACT_MATCH_THRESHOLD = 0.95       # Treat as a definitive match
PRODUCT_SEARCH_THRESHOLD = 0.35    # Minimum score for hardware product queries
UNKNOWN_QUERY_THRESHOLD = 0.20     # Below this — return empty (unknown / off-topic)


class RagRetriever:
    def __init__(self, products_path: str = PRODUCTS_PATH, corpus_path: str = CORPUS_PATH, catalogue_path: str = CATALOGUE_PATH):
        self.products_path = products_path
        self.corpus_path = corpus_path
        self.catalogue_path = catalogue_path
        self.products: List[Dict[str, Any]] = []
        self.sku_index: Dict[str, Dict[str, Any]] = {}
        self.doc_texts: List[str] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self._load_and_index()

    @staticmethod
    def _load_json_map(path: str) -> Dict[str, Any]:
        """Safely loads a JSON file as a dict, returns empty dict on failure."""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_and_index(self):
        """Loads products.json, merges catalogue_products.json specifications, verified pricing,
        brochure URLs, and complete training corpus datasheet specs; then builds the TF-IDF index."""
        raw_products = []
        if os.path.exists(self.products_path):
            with open(self.products_path, "r", encoding="utf-8") as f:
                raw_products = json.load(f)

        # ── NEW: Load verified pricing & brochure reference maps ──────────────
        verified_prices_map: Dict[str, Any] = self._load_json_map(VERIFIED_PRICES_PATH)
        website_prices_map: Dict[str, Any] = self._load_json_map(WEBSITE_PRICES_PATH)
        verified_brochures_map: Dict[str, Any] = self._load_json_map(VERIFIED_BROCHURES_PATH)

        # ── NEW: Build id-keyed lookup from complete_training_corpus.json ─────
        complete_corpus_map: Dict[str, Any] = {}
        complete_corpus_token_map: Dict[str, Any] = {}
        raw_corpus_list = self._load_json_map(COMPLETE_CORPUS_PATH)
        if isinstance(raw_corpus_list, list):
            for entry in raw_corpus_list:
                cid = str(entry.get("id", "")).lower().strip()
                if cid:
                    complete_corpus_map[cid] = entry
                title_tokens = re.findall(r"[a-z0-9]{3,}", str(entry.get("title", "")).lower())
                for tok in title_tokens:
                    if tok not in {"epson", "citizen", "surecolor", "printer", "photo"}:
                        complete_corpus_token_map[tok] = entry

        # Merge additional rich specification fields from kepler_product_corpus if available
        corpus_lookup = {}
        corpus_token_lookup = {}
        if os.path.exists(self.corpus_path):
            try:
                with open(self.corpus_path, "r", encoding="utf-8") as cf:
                    for cp in json.load(cf):
                        norm_k = re.sub(r"[^a-z0-9]", "", cp.get("name", "").lower())
                        corpus_lookup[norm_k] = cp
                        for tok in re.findall(r"[a-z0-9]{3,}", cp.get("name", "").lower()):
                            if tok not in {"epson", "surecolor", "workforce", "printer", "technical", "plotter", "large", "format"}:
                                corpus_token_lookup[tok] = cp
            except Exception:
                pass

        # Load verified catalogue products (datasheets, components, exact speeds, dimensions, memory, DPI)
        catalogue_lookup_by_id = {}
        catalogue_lookup_by_norm = {}
        catalogue_token_lookup = {}
        catalogue_items = []
        if os.path.exists(self.catalogue_path):
            try:
                with open(self.catalogue_path, "r", encoding="utf-8") as cat_f:
                    catalogue_items = json.load(cat_f)
                    for cp in catalogue_items:
                        cid = str(cp.get("id", "")).strip().lower()
                        cname = cp.get("display_name") or cp.get("name") or ""
                        norm_cname = re.sub(r"[^a-z0-9]", "", cname.lower())
                        if cid:
                            catalogue_lookup_by_id[cid] = cp
                        if norm_cname:
                            catalogue_lookup_by_norm[norm_cname] = cp
                        for tok in re.findall(r"[a-z0-9]{3,}", cname.lower()):
                            if tok not in {"epson", "surecolor", "workforce", "printer", "technical", "plotter", "large", "format", "multifunction", "scanner"}:
                                catalogue_token_lookup[tok] = cp
            except Exception:
                pass

        self.products = []
        self.sku_index = {}
        self.doc_texts = []
        seen_catalogue_ids = set()

        for p in raw_products:
            prod = dict(p)
            norm_name = re.sub(r"[^a-z0-9]", "", prod.get("name", "").lower())

            # ── NEW: Merge verified price data ────────────────────────────────
            prod_id_key = str(prod.get("_id") or prod.get("id") or "").lower().strip()
            p_price_info = (
                verified_prices_map.get(prod_id_key)
                or website_prices_map.get(prod_id_key)
            )
            if not p_price_info:
                # Try matching by normalized name fragment
                for k, v in verified_prices_map.items():
                    k_norm = re.sub(r"[^a-z0-9]", "", k)
                    if k_norm and (k_norm in norm_name or norm_name in k_norm):
                        p_price_info = v
                        break
            if p_price_info and p_price_info.get("price") and not prod.get("price"):
                prod["price"] = float(p_price_info["price"])
                prod["price_str"] = p_price_info.get("price_str") or f"AED {float(p_price_info['price']):,.2f}"
                prod["currency"] = p_price_info.get("currency", "AED")
                prod["vat_note"] = p_price_info.get("vat_note", "(Excl. VAT)")

            # ── NEW: Merge brochure / PDF URL ─────────────────────────────────
            b_info = verified_brochures_map.get(prod_id_key)
            if b_info and b_info.get("pdf") and not prod.get("brochure_url"):
                prod["brochure_url"] = b_info["pdf"]
                prod["pdf_url"] = b_info["pdf"]

            # ── NEW: Merge rich datasheet specs from complete_training_corpus ──
            corpus_entry = complete_corpus_map.get(prod_id_key)
            if not corpus_entry:
                for tok in re.findall(r"[a-z0-9]{3,}", prod.get("name", "").lower()):
                    if tok in complete_corpus_token_map:
                        corpus_entry = complete_corpus_token_map[tok]
                        break
            if corpus_entry:
                for field in ["dimensions", "weight", "dpi", "memory", "print_speed",
                               "yield_capacity", "consumables_detailed", "brochure_url"]:
                    if corpus_entry.get(field) and not prod.get(field):
                        prod[field] = corpus_entry[field]
                # Also pull price_aed if price not yet set
                if corpus_entry.get("price_aed") and not prod.get("price"):
                    pa = float(corpus_entry["price_aed"])
                    prod["price"] = pa
                    prod["price_str"] = f"AED {pa:,.2f}"
                    prod["currency"] = "AED"
                    prod["vat_note"] = "(Excl. VAT)"

            # 1. Match from corpus
            extra = corpus_lookup.get(norm_name)
            if not extra:
                for tok in re.findall(r"[a-z0-9]{3,}", prod.get("name", "").lower()):
                    if tok in corpus_token_lookup:
                        extra = corpus_token_lookup[tok]
                        break

            if extra:
                for k in ["width", "speed", "ink_technology", "intended_usage", "comparison_highlights"]:
                    if k in extra and not prod.get(k):
                        prod[k] = extra[k]

            # 2. Match from verified catalogue products (datasheet specs)
            cat_entry = None
            prod_id_low = str(prod.get("_id") or prod.get("id") or "").lower()
            if prod_id_low in catalogue_lookup_by_id:
                cat_entry = catalogue_lookup_by_id[prod_id_low]
            elif norm_name in catalogue_lookup_by_norm:
                cat_entry = catalogue_lookup_by_norm[norm_name]
            else:
                for norm_c, cp in catalogue_lookup_by_norm.items():
                    if norm_c and (norm_c in norm_name or norm_name in norm_c):
                        cat_entry = cp
                        break
                if not cat_entry:
                    for tok in re.findall(r"[a-z0-9]{3,}", prod.get("name", "").lower()):
                        if tok in catalogue_token_lookup:
                            cat_entry = catalogue_token_lookup[tok]
                            break

            if cat_entry:
                seen_catalogue_ids.add(str(cat_entry.get("id", "")).lower())
                # Copy rich component and specification attributes
                for field in [
                    "dpi", "memory", "dimensions", "weight", "print_speed",
                    "supported_print_sizes", "applications", "pattern_and_finishing",
                    "colour_specification", "cartridge_sizes", "consumable_volume",
                    "yield_capacity", "recommended_monthly_min", "recommended_monthly_max",
                    "brochure_url", "product_url", "functions", "paper_size", "max_width_inches"
                ]:
                    if cat_entry.get(field) and not prod.get(field):
                        prod[field] = cat_entry[field]

                if not prod.get("speed") and cat_entry.get("print_speed"):
                    prod["speed"] = cat_entry["print_speed"]
                if not prod.get("ink_technology") and cat_entry.get("colour_specification"):
                    prod["ink_technology"] = cat_entry["colour_specification"]
                if not prod.get("consumables") and cat_entry.get("consumables"):
                    prod["consumables"] = cat_entry["consumables"]

            prod.setdefault("width", "")
            prod.setdefault("speed", "")
            prod.setdefault("ink_technology", "")
            prod.setdefault("intended_usage", "")

            sku = str(prod.get("sku", "")).strip()
            if sku:
                self.sku_index[sku.upper()] = prod
            prod_id = str(prod.get("_id") or prod.get("id") or "").strip()
            if prod_id:
                self.sku_index[prod_id.upper()] = prod

            # Build rich document string for indexing
            name = prod.get("name", "")
            cat = prod.get("category", "")
            desc = prod.get("description", "")
            tags = " ".join(prod.get("tags", [])) if isinstance(prod.get("tags"), list) else str(prod.get("tags", ""))
            intended = prod.get("intended_usage", "")
            highlights = prod.get("comparison_highlights", "")
            width = prod.get("width", "")
            speed = prod.get("speed", "") or prod.get("print_speed", "")
            ink = prod.get("ink_technology", "") or prod.get("colour_specification", "")
            dpi = prod.get("dpi", "")
            mem = prod.get("memory", "")
            dims = prod.get("dimensions", "")
            wt = prod.get("weight", "")
            apps = ", ".join(prod.get("applications", [])) if isinstance(prod.get("applications"), list) else str(prod.get("applications", ""))
            finishing = prod.get("pattern_and_finishing", "")
            sizes = ", ".join(prod.get("supported_print_sizes", [])) if isinstance(prod.get("supported_print_sizes"), list) else str(prod.get("supported_print_sizes", ""))
            price_str = prod.get("price_str", "")
            brochure = prod.get("brochure_url", "") or prod.get("pdf_url", "")

            doc_parts = [
                f"Name: {name}",
                f"SKU: {sku}",
                f"Category: {cat}",
                f"Description: {desc}",
                f"Tags: {tags}",
                f"Width: {width}",
                f"Speed: {speed}",
                f"Ink: {ink}",
                f"DPI: {dpi}",
                f"Memory: {mem}",
                f"Dimensions: {dims}",
                f"Weight: {wt}",
                f"Applications: {apps} {intended}",
                f"Paper Sizes: {sizes}",
                f"Finishing: {finishing}",
                f"Highlights: {highlights}",
                f"Price: {price_str}",
                f"Brochure: {brochure}",
            ]
            doc_str = " | ".join([part for part in doc_parts if not part.endswith(":")])
            self.products.append(prod)
            self.doc_texts.append(doc_str)

        # 3. Add any catalogue products not represented in raw_products (e.g. Scanners or specific configurations)
        for cat_p in catalogue_items:
            cid = str(cat_p.get("id", "")).lower()
            if cid not in seen_catalogue_ids:
                seen_catalogue_ids.add(cid)
                c_prod = {
                    "_id": cat_p.get("id"),
                    "id": cat_p.get("id"),
                    "sku": cat_p.get("id"),
                    "name": cat_p.get("display_name") or cat_p.get("name"),
                    "category": cat_p.get("main_category", "Hardware"),
                    "description": f"Verified {cat_p.get('display_name')} from Kepler Tech LLC.",
                    "tags": [cat_p.get("brand", "Epson"), cat_p.get("model_family", ""), cat_p.get("main_category", "")],
                    "image_url": cat_p.get("image_url", ""),
                    "website_url": cat_p.get("product_url", ""),
                    "consumables": cat_p.get("consumables", []),
                    "speed": cat_p.get("print_speed", ""),
                    "print_speed": cat_p.get("print_speed", ""),
                    "dpi": cat_p.get("dpi", ""),
                    "memory": cat_p.get("memory", ""),
                    "dimensions": cat_p.get("dimensions", ""),
                    "weight": cat_p.get("weight", ""),
                    "width": f"{cat_p.get('max_width_inches', '')} inches" if cat_p.get("max_width_inches") else "",
                    "ink_technology": cat_p.get("colour_specification", ""),
                    "colour_specification": cat_p.get("colour_specification", ""),
                    "supported_print_sizes": cat_p.get("supported_print_sizes", []),
                    "applications": cat_p.get("applications", []),
                    "pattern_and_finishing": cat_p.get("pattern_and_finishing", ""),
                    "brochure_url": cat_p.get("brochure_url", ""),
                    "product_url": cat_p.get("product_url", "")
                }
                cid_up = cat_p["id"].upper()
                self.sku_index[cid_up] = c_prod
                self.products.append(c_prod)
                doc_str = f"Name: {c_prod['name']} | SKU: {c_prod['sku']} | Category: {c_prod['category']} | Speed: {c_prod['speed']} | DPI: {c_prod['dpi']} | Memory: {c_prod['memory']} | Dimensions: {c_prod['dimensions']} | Weight: {c_prod['weight']}"
                self.doc_texts.append(doc_str)

        # 4. Index Verified Delivery & Shipping Policy Documents
        delivery_policy_path = os.path.join(os.path.dirname(__file__), "..", "data", "delivery_policy.json")
        if os.path.exists(delivery_policy_path):
            try:
                with open(delivery_policy_path, "r", encoding="utf-8") as dpf:
                    dp_data = json.load(dpf)
                    uae_zone = dp_data.get("zones", {}).get("UAE", {})
                    uae_doc = {
                        "_id": "policy-delivery-uae",
                        "id": "policy-delivery-uae",
                        "sku": "POLICY-DELIVERY-UAE",
                        "name": "Kepler Tech UAE Delivery Policy",
                        "display_name": "Kepler Tech UAE Delivery & Shipping Policy",
                        "category": "Policy",
                        "description": (
                            f"Delivery across all UAE Emirates (Dubai, Abu Dhabi, Sharjah, Ajman, RAK, Fujairah, Umm Al Quwain, Al Ain): "
                            f"{uae_zone.get('fee', 'Flat AED 10')}. Dispatch timeline: {uae_zone.get('timing', '1 to 2 business days')}. "
                            f"Heavy printers and large-format plotters include {uae_zone.get('installation', 'free on-site delivery, uncrating, and certified engineer installation')}."
                        ),
                        "tags": ["delivery", "shipping", "fee", "uae", "dubai", "abu dhabi", "sharjah", "aed 10", "installation", "timeline"],
                        "fee": uae_zone.get("fee", "Flat AED 10 across all Emirates"),
                        "timing": uae_zone.get("timing", "1 to 2 business days"),
                        "installation": uae_zone.get("installation", ""),
                    }
                    self.products.append(uae_doc)
                    self.doc_texts.append(
                        f"Policy: UAE Delivery & Shipping | Fee: {uae_doc['fee']} | Destination: Dubai, Abu Dhabi, Sharjah, Ajman, UAE | "
                        f"Timing: {uae_doc['timing']} | Installation: {uae_doc['installation']} | Courier: Insured courier or Kepler technical fleet"
                    )

                    oman_zone = dp_data.get("zones", {}).get("OMAN", {})
                    gcc_zone = dp_data.get("zones", {}).get("GCC_OTHER", {})
                    gcc_doc = {
                        "_id": "policy-delivery-gcc",
                        "id": "policy-delivery-gcc",
                        "sku": "POLICY-DELIVERY-GCC",
                        "name": "Kepler Tech Oman & GCC Shipping Policy",
                        "display_name": "Kepler Tech Oman & GCC Shipping Policy",
                        "category": "Policy",
                        "description": (
                            f"Oman and GCC delivery (Saudi Arabia, Qatar, Bahrain, Kuwait): Dispatched in 1 to 2 business days from Dubai. "
                            f"Shipping fee is calculated at checkout based on weight and country. Customer pays local import duties and VAT."
                        ),
                        "tags": ["delivery", "shipping", "oman", "gcc", "saudi", "qatar", "bahrain", "kuwait", "customs", "export"],
                        "timing": "1 to 2 business days dispatch",
                        "fee": "Calculated at checkout based on package weight and destination",
                    }
                    self.products.append(gcc_doc)
                    self.doc_texts.append(
                        f"Policy: Oman and GCC Delivery & Shipping | Destinations: Oman, Saudi Arabia, Qatar, Bahrain, Kuwait | "
                        f"Fee: Calculated at checkout by weight | Timing: 1 to 2 business days | Customs: Recipient pays destination customs duty and VAT"
                    )

                    pickup_data = dp_data.get("pickup", {})
                    pickup_doc = {
                        "_id": "policy-pickup-sameday",
                        "id": "policy-pickup-sameday",
                        "sku": "POLICY-PICKUP-SAMEDAY",
                        "name": "Kepler Tech Showroom Store Pickup & Same-Day Dubai Delivery",
                        "display_name": "Kepler Tech Store Pickup & Same-Day Dubai Delivery",
                        "category": "Policy",
                        "description": (
                            f"Free store pickup at Kepler Tech LLC Showroom: {pickup_data.get('location', 'D79 Khalid Bin Waleed Rd, Dubai')}. "
                            f"Ready for collection in 1 to 2 business days. "
                            f"Same-day emergency delivery across Dubai may be arranged upon request with our sales desk for in-stock consumables and equipment."
                        ),
                        "tags": ["store pickup", "collection", "showroom", "same day", "dubai", "emergency delivery", "free pickup"],
                        "fee": "Free Store Pickup",
                        "location": pickup_data.get("location", ""),
                    }
                    self.products.append(pickup_doc)
                    self.doc_texts.append(
                        f"Policy: Local Store Pickup & Same-Day Delivery | Fee: Free store pickup | "
                        f"Location: {pickup_doc['location']} | Timing: Ready in 1-2 business days | "
                        f"Same-day emergency delivery: Available across Dubai on request for in-stock items"
                    )

                    ret_data = dp_data.get("returns", {})
                    canc_data = dp_data.get("cancellation", {})
                    returns_doc = {
                        "_id": "policy-returns-cancellation",
                        "id": "policy-returns-cancellation",
                        "sku": "POLICY-RETURNS-CANCELLATION",
                        "name": "Kepler Tech Return, Cancellation & Warranty Policy",
                        "display_name": "Kepler Tech Return & Cancellation Policy",
                        "category": "Policy",
                        "description": (
                            f"Cancellation: {canc_data.get('window', 'Within 24 hours of placing order')}. "
                            f"Returns: {ret_data.get('window', 'Defective or incorrect items must be reported within 2 days of receipt in original unopened packaging')}. "
                            f"Refunds: Processed to original payment method in up to 45 days. Contact: sales@keplertech.ae."
                        ),
                        "tags": ["returns", "cancellation", "refund", "damaged", "warranty", "defective"],
                    }
                    self.products.append(returns_doc)
                    self.doc_texts.append(
                        f"Policy: Return, Refund and Order Cancellation | Cancellation window: 24 hours | "
                        f"Returns: Defective or damaged items reported within 2 days of receipt in unopened original packaging | "
                        f"Refund timeline: Up to 45 days to original payment method | Contact: sales@keplertech.ae"
                    )
            except Exception as e:
                import logging
                logging.getLogger("rag.retriever").warning(f"Failed to index delivery policy: {e}")

        if self.doc_texts:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=12000)
            self.tfidf_matrix = self.vectorizer.fit_transform(self.doc_texts)
            try:
                from rag.embeddings_engine import embeddings_engine
                self.embeddings_engine = embeddings_engine
                doc_ids = [str(p.get("_id") or p.get("id") or p.get("sku") or idx) for idx, p in enumerate(self.products)]
                self.embeddings_engine.load_or_build_index(doc_ids=doc_ids, doc_texts=self.doc_texts)
            except Exception as e:
                import logging
                logging.getLogger("rag.retriever").warning(f"Embeddings engine index init skipped: {e}")

    def search(self, query: str, category: Optional[str] = None, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Dynamically searches the full 792 catalog items using hybrid lexical + semantic search.
        Prioritizes hardware equipment over consumables when searching for equipment models.
        """
        if not self.products:
            return []

        q_clean = query.strip()
        q_upper = q_clean.upper()
        q_lower = q_clean.lower().replace("\u200b", " ")
        q_norm = re.sub(r"[^a-z0-9]", "", q_lower)

        # 1. Exact SKU match
        if q_upper in self.sku_index:
            target = dict(self.sku_index[q_upper])
            target["similarity_score"] = 1.0
            return [target]

        # 2. Model token exact / prefix match ONLY for dedicated short model queries (e.g. 'P700', 'DS-900WN', 'T3100', 'AM-C4000')
        tokens = [t for t in re.findall(r"[A-Za-z0-9\-]+", q_lower) if len(t) >= 3]
        if 1 <= len(tokens) <= 3 and not any(w in q_lower for w in ["recommend", "need", "best", "speed", "flatbed"]):
            exact_model_matches = []
            for p in self.products:
                p_name_clean = p.get("name", "").lower().replace("\u200b", " ")
                p_sku = str(p.get("sku", "")).lower()
                p_norm = re.sub(r"[^a-z0-9]", "", p_name_clean)
                
                # Check direct normalized equality with SKU or strict boundary matching on name
                pat_q = r'(?:\b|_|-)' + re.escape(q_norm) + r'(?:\b|_|-|\s|$)(?![0-9a-zA-Z])'
                if q_norm and (q_norm == p_sku or re.search(pat_q, p_name_clean) or re.search(pat_q, p_sku)):
                    exact_model_matches.append(p)
                    continue

                for t in tokens:
                    pattern = r'(?:\b|_|-)' + re.escape(t) + r'(?:\b|_|-|\s|$)(?![0-9a-zA-Z])'
                    if re.search(pattern, p_name_clean) or re.search(pattern, p_sku) or t == p_sku:
                        exact_model_matches.append(p)
                        break

            if exact_model_matches:
                if category:
                    cat_filtered = [p for p in exact_model_matches if category.lower() in p.get("category", "").lower()]
                    if cat_filtered:
                        exact_model_matches = cat_filtered
                else:
                    # Prioritize hardware over ink/maintenance boxes when query does NOT mention ink/consumables
                    query_wants_consumables = any(w in q_lower for w in ["ink", "cartridge", "ribbon", "maintenance", "box", "tank", "roll", "paper", "media"])
                    if not query_wants_consumables:
                        hw_matches = [p for p in exact_model_matches if any(hw_kw in p.get("category", "").lower() for hw_kw in ["printer", "scanner", "large format", "business"])]
                        if hw_matches:
                            exact_model_matches = hw_matches

                res = []
                seen_exact = set()
                for item in exact_model_matches:
                    norm = re.sub(r"[^a-z0-9]", "", item.get("name", "").lower())
                    if norm not in seen_exact:
                        seen_exact.add(norm)
                        d = dict(item)
                        d["similarity_score"] = 0.95
                        res.append(d)
                        if len(res) >= limit:
                            break
                if res:
                    return res

        # 3. Dense Neural Vector Similarity (Embeddings) + TF-IDF Lexical Similarity
        if not self.vectorizer or self.tfidf_matrix is None:
            return []

        query_vec = self.vectorizer.transform([query])
        tfidf_scores = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        dense_scores = np.zeros(len(self.products), dtype=np.float32)
        if getattr(self, "embeddings_engine", None) and self.embeddings_engine.embeddings is not None:
            try:
                dense_sims = self.embeddings_engine.compute_similarity(query, top_k=len(self.products))
                for doc_idx, sim in dense_sims:
                    if 0 <= doc_idx < len(dense_scores):
                        dense_scores[doc_idx] = sim
            except Exception:
                pass

        if dense_scores.max() > 0:
            d_max = float(dense_scores.max())
            norm_dense = dense_scores / d_max
            scores = (0.55 * norm_dense) + (0.45 * tfidf_scores)
        else:
            scores = np.array(tfidf_scores, dtype=np.float32)

        # Category and keyword boosting
        for idx, p in enumerate(self.products):
            p_cat = p.get("category", "").lower()
            p_name = p.get("name", "").lower()
            p_desc = p.get("description", "").lower()

            if category and category.lower() in p_cat:
                scores[idx] += 0.35

            # Boost if query keywords appear in product title
            for w in q_lower.split():
                if len(w) >= 3:
                    if re.search(rf"\b{re.escape(w)}\b", p_name):
                        scores[idx] += 0.20
                    elif re.search(rf"\b{re.escape(w)}\b", p_desc):
                        scores[idx] += 0.05

            p_width = str(p.get("width", "")).lower()

            # Specific width/drawing size boosting
            if ("24-inch" in q_lower or "a1" in q_lower or "24\"" in q_lower) and not ("36" in q_lower or "a0" in q_lower):
                if any(x in p_name for x in ["t3100", "24-inch", "24\""]) or "24" in p_width:
                    scores[idx] += 0.40
                elif any(x in p_name for x in ["t5100", "t5400", "36-inch", "36\""]) or "36" in p_width:
                    scores[idx] -= 0.30

            if ("36-inch" in q_lower or "a0" in q_lower or "36\"" in q_lower) and not ("24" in q_lower or "a1" in q_lower):
                if any(x in p_name for x in ["t5100", "t5400", "36-inch", "36\""]) or "36" in p_width:
                    scores[idx] += 0.40

            if "17-inch" in q_lower or "17\"" in q_lower or "10 colors" in q_lower:
                if "p900" in p_name or "p-900" in p_name or "c11ch37402dr" in str(p.get("sku", "")).lower():
                    scores[idx] += 0.45

        ranked_indices = np.argsort(scores)[::-1]
        results = []
        seen_names = set()

        for idx in ranked_indices:
            if scores[idx] <= 0:
                continue
            prod = dict(self.products[idx])
            norm = re.sub(r"[^a-z0-9]", "", prod.get("name", "").lower())
            if norm in seen_names:
                continue
            seen_names.add(norm)
            prod["similarity_score"] = round(float(scores[idx]), 3)
            results.append(prod)
            if len(results) >= limit:
                break

        return results

    def retrieve(self, query: str, nlp_context: dict = None, top_k: int = 3) -> list:
        """Backward-compatible RAG retriever method with NLP entity boosting and confidence gating."""
        cat = None
        if nlp_context and nlp_context.get("categories"):
            cat = nlp_context["categories"][0]
        results = self.search(query=query, category=cat, limit=top_k)
        # Apply UNKNOWN_QUERY_THRESHOLD gate: discard results below minimum confidence
        return [r for r in results if r.get("similarity_score", 0) >= UNKNOWN_QUERY_THRESHOLD]

    def get_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """Finds a product directly by SKU."""
        return self.sku_index.get(sku.strip().upper())

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Finds a product by name match with hardware prioritization and word-boundary token accuracy."""
        q_clean = name.strip().lower().replace("\u200b", " ")
        q_tokens = [t for t in re.findall(r"[a-z0-9]+", q_clean) if len(t) >= 2]
        if not q_tokens:
            return None

        GENERIC_STOP = {"epson", "surecolor", "workforce", "printer", "sc", "the", "for", "with", "series"}
        
        best_item = None
        best_score = -1

        for p in self.products:
            p_name = p.get("name", "").lower().replace("\u200b", " ")
            p_sku = str(p.get("sku", "")).lower()
            p_tokens = set(re.findall(r"[a-z0-9]+", p_name))
            p_cat = p.get("category", "").lower()
            is_hw = any(hw_kw in p_cat for hw_kw in ["printer", "scanner", "large format", "business", "photo printer"]) and not any(acc in p_cat for acc in ["accessory", "media", "ink", "bag"])

            score = 0
            all_specific_matched = True
            specific_count = 0

            for qt in q_tokens:
                if qt in GENERIC_STOP:
                    if qt in p_tokens:
                        score += 2
                else:
                    specific_count += 1
                    # Word boundary pattern preventing p900 from matching p9000, cx02 from matching cx02w
                    pattern = r'(?:\b|_|-)' + re.escape(qt) + r'(?:\b|_|-|\s|$)(?!\d|[a-z])'
                    if re.search(pattern, p_name) or qt == p_sku or qt in p_tokens:
                        score += 20
                    else:
                        all_specific_matched = False
                        break

            if all_specific_matched and (score > 0 or specific_count == 0):
                if is_hw:
                    score += 100
                if "bag" in p_name or "accessory" in p_cat:
                    score -= 50
                # Tie breaker: length similarity
                score -= abs(len(p_name) - len(q_clean)) * 0.05

                if score > best_score:
                    best_score = score
                    best_item = p

        return best_item

    def format_prompt_context(self, retrieved_items: list) -> str:
        """Formats retrieved product cards into a structured prompt block for LLM."""
        if not retrieved_items:
            return ""

        lines = ["--- VERIFIED CATALOG RETRIEVAL (LIVE CATALOG CONTEXT) ---"]
        for idx, item in enumerate(retrieved_items, start=1):
            name = item.get("name", "")
            sku = item.get("sku", "")
            score = item.get("similarity_score", 0)
            url = item.get("website_url") or item.get("web_url") or item.get("source_url", "")
            img = item.get("image_url") or item.get("image", "")
            lines.append(f"[{idx}] {name} (SKU: {sku} | Score: {score})")
            if item.get("category"):
                lines.append(f"    Category: {item['category']}")
            if item.get("description"):
                lines.append(f"    Description: {item['description']}")
            if item.get("width"):
                lines.append(f"    Print Width/Size: {item['width']}")
            if item.get("speed") or item.get("print_speed"):
                lines.append(f"    Speed: {item.get('speed') or item.get('print_speed')}")
            if item.get("ink_technology"):
                lines.append(f"    Technology: {item['ink_technology']}")
            if item.get("intended_usage"):
                lines.append(f"    Intended Use: {item['intended_usage']}")
            # ── NEW: verified pricing ─────────────────────────────────────────
            if item.get("price_str") or item.get("price"):
                price_label = item.get("price_str") or f"AED {float(item['price']):,.2f}"
                vat = item.get("vat_note", "(Excl. VAT)")
                lines.append(f"    Price: {price_label} {vat}")
            # ── NEW: datasheet / brochure PDF URL ─────────────────────────────
            brochure = item.get("brochure_url") or item.get("pdf_url", "")
            if brochure:
                lines.append(f"    Datasheet / Brochure PDF: {brochure}")
            # ── NEW: physical dimensions & weight ─────────────────────────────
            if item.get("dimensions"):
                lines.append(f"    Dimensions: {item['dimensions']}")
            if item.get("weight"):
                lines.append(f"    Weight: {item['weight']}")
            # ── NEW: resolution / DPI ─────────────────────────────────────────
            if item.get("dpi"):
                lines.append(f"    Resolution / DPI: {item['dpi']}")
            # ── NEW: memory ───────────────────────────────────────────────────
            if item.get("memory"):
                lines.append(f"    Memory: {item['memory']}")
            # ── NEW: consumables ──────────────────────────────────────────────
            if item.get("consumables_detailed"):
                try:
                    import json as _json
                    cons = item["consumables_detailed"]
                    if isinstance(cons, str):
                        cons = _json.loads(cons)
                    if isinstance(cons, list):
                        c_names = ", ".join(f"{c.get('sku','?')} ({c.get('name','')}) AED {c.get('price',0):,.2f}" for c in cons[:4])
                        lines.append(f"    Consumables: {c_names}")
                except Exception:
                    pass
            if url:
                lines.append(f"    Product URL: {url}")
            if img:
                lines.append(f"    Image: {img}")

        return "\n".join(lines)


# Global singleton instance
rag_retriever = RagRetriever()
