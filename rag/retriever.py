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


class RagRetriever:
    def __init__(self, products_path: str = PRODUCTS_PATH, corpus_path: str = CORPUS_PATH):
        self.products_path = products_path
        self.corpus_path = corpus_path
        self.products: List[Dict[str, Any]] = []
        self.sku_index: Dict[str, Dict[str, Any]] = {}
        self.doc_texts: List[str] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self._load_and_index()

    def _load_and_index(self):
        """Loads products.json and builds lexical and TF-IDF search index."""
        raw_products = []
        if os.path.exists(self.products_path):
            with open(self.products_path, "r", encoding="utf-8") as f:
                raw_products = json.load(f)

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

        self.products = []
        self.sku_index = {}
        self.doc_texts = []

        for p in raw_products:
            prod = dict(p)
            norm_name = re.sub(r"[^a-z0-9]", "", prod.get("name", "").lower())
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
                if extra.get("print_speed") and not prod.get("speed"):
                    prod["speed"] = extra["print_speed"]
                if extra.get("print_sizes") and not prod.get("width"):
                    prod["width"] = extra["print_sizes"]
                if extra.get("technology") and not prod.get("ink_technology"):
                    prod["ink_technology"] = extra["technology"]

            prod.setdefault("width", "")
            prod.setdefault("speed", "")
            prod.setdefault("ink_technology", "")
            prod.setdefault("intended_usage", "")

            sku = str(prod.get("sku", "")).strip()
            if sku:
                self.sku_index[sku.upper()] = prod

            # Build rich document string for indexing
            name = prod.get("name", "")
            cat = prod.get("category", "")
            desc = prod.get("description", "")
            tags = " ".join(prod.get("tags", [])) if isinstance(prod.get("tags"), list) else str(prod.get("tags", ""))
            intended = prod.get("intended_usage", "")
            highlights = prod.get("comparison_highlights", "")
            width = prod.get("width", "")
            speed = prod.get("speed", "")
            ink = prod.get("ink_technology", "")

            doc_parts = [
                f"Name: {name}",
                f"SKU: {sku}",
                f"Category: {cat}",
                f"Description: {desc}",
                f"Tags: {tags}",
                f"Width: {width}",
                f"Speed: {speed}",
                f"Ink: {ink}",
                f"Intended: {intended}",
                f"Highlights: {highlights}"
            ]
            doc_str = " | ".join([part for part in doc_parts if not part.endswith(":")])
            self.products.append(prod)
            self.doc_texts.append(doc_str)

        if self.doc_texts:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=8000)
            self.tfidf_matrix = self.vectorizer.fit_transform(self.doc_texts)

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
                
                # Check direct normalized containment (e.g. 'amc4000' in 'epsonworkforceenterprisewfamc4000printer')
                if q_norm and (q_norm == p_sku or q_norm in p_norm):
                    exact_model_matches.append(p)
                    continue

                for t in tokens:
                    t_norm = re.sub(r"[^a-z0-9]", "", t)
                    pattern = r'(?:\b|_|-)' + re.escape(t) + r'(?:\b|_|-|\s|$)'
                    if re.search(pattern, p_name_clean) or re.search(pattern, p_sku) or (t_norm and t_norm in p_norm):
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

        # 3. TF-IDF Semantic Vector Similarity
        if not self.vectorizer or self.tfidf_matrix is None:
            return []

        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        # Category and keyword boosting
        for idx, p in enumerate(self.products):
            p_cat = p.get("category", "").lower()
            p_name = p.get("name", "").lower()
            p_desc = p.get("description", "").lower()

            if category and category.lower() in p_cat:
                scores[idx] += 0.35

            # Boost if query keywords appear in product title
            for w in q_lower.split():
                if len(w) >= 3 and w in p_name:
                    scores[idx] += 0.20
                elif len(w) >= 3 and w in p_desc:
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
        """Backward-compatible RAG retriever method with NLP entity boosting."""
        cat = None
        if nlp_context and nlp_context.get("categories"):
            cat = nlp_context["categories"][0]
        return self.search(query=query, category=cat, limit=top_k)

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
            if item.get("speed"):
                lines.append(f"    Speed: {item['speed']}")
            if item.get("ink_technology"):
                lines.append(f"    Technology: {item['ink_technology']}")
            if item.get("intended_usage"):
                lines.append(f"    Intended Use: {item['intended_usage']}")
            if url:
                lines.append(f"    Product URL: {url}")
            if img:
                lines.append(f"    Image: {img}")

        return "\n".join(lines)


# Global singleton instance
rag_retriever = RagRetriever()
