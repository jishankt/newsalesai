"""
Deterministic Universal Reference Resolver for Kepler Tech SalesAI.

Resolves conversational references:
- Pronouns & Demonstratives: "it", "this", "that", "this one", "that one"
- Ordinals & Indices: "first one", "second one", "third one", "first printer", "second printer"
- Alternatives & Rejections: "not this one", "other one", "the other model", "show another"
- History & Continuity: "previous one", "last one", "the model you showed", "the printer before"
- Attribute References: "the one with scanner", "without scanner", "the wider one", "the 36-inch one"
- Brand References: "the Epson one", "the Citizen one"
- Price References: "the cheaper one" (strictly when verified price evidence exists)

Uses active_product, displayed_product_ids, candidate_products, compared_products,
and recent history deterministically.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from catalog.catalogue_loader import catalogue_loader


class ReferenceResolutionResult:
    def __init__(
        self,
        resolved_products: List[Dict[str, Any]],
        mapping: Dict[str, str],
        is_rejection: bool = False,
        is_alternative_request: bool = False,
        rejected_product: Optional[Dict[str, Any]] = None,
        needs_clarification: bool = False,
        clarification_question: Optional[str] = None,
    ):
        self.resolved_products = resolved_products
        self.mapping = mapping
        self.is_rejection = is_rejection
        self.is_alternative_request = is_alternative_request
        self.rejected_product = rejected_product
        self.needs_clarification = needs_clarification
        self.clarification_question = clarification_question

    def __getitem__(self, index):
        p = self.resolved_products[index]
        return p.get("id") if isinstance(p, dict) else str(p)

    def __len__(self):
        return len(self.resolved_products)

    def __iter__(self):
        for p in self.resolved_products:
            yield p.get("id") if isinstance(p, dict) else str(p)

    @property
    def product_ids(self) -> List[str]:
        return [p.get("id") if isinstance(p, dict) else str(p) for p in self.resolved_products if p]


class ReferenceResolver:
    """Deterministic reference resolution engine."""

    REJECTION_PATTERNS = [
        re.compile(r"\b(?:not\s+this\s+one|not\s+that\s+one|not\s+this|not\s+that|reject\s+this)\b", re.I),
        re.compile(r"\b(?:show\s+(?:the\s+)?other(?:\s+one|\s+model|\s+printer)?|show\s+another|another\s+one)\b", re.I),
        re.compile(r"\b(?:dont\s+want\s+this|don't\s+want\s+this|dont\s+like\s+this|don't\s+like\s+this)\b", re.I),
    ]

    @classmethod
    def _to_prod_dict(cls, item: Any) -> Optional[Dict[str, Any]]:
        if not item:
            return None
        if isinstance(item, dict):
            return item
        if isinstance(item, str):
            prod = catalogue_loader.get_by_id(item)
            if not prod and item.startswith("epson-") and not item.startswith("epson-sc-"):
                prod = catalogue_loader.get_by_id(item.replace("epson-", "epson-sc-"))
            if not prod:
                clean_item = item.lower().replace("-", "").replace(" ", "").replace("_", "")
                for p in catalogue_loader.load_and_validate():
                    clean_id = p.get("id", "").lower().replace("-", "").replace(" ", "").replace("_", "")
                    if clean_item in clean_id or clean_id in clean_item:
                        prod = p
                        break
            if not prod:
                try:
                    from rag.retriever import rag_retriever
                    rp = rag_retriever.get_by_id(item) or rag_retriever.get_by_sku(item)
                    if rp:
                        prod = rp
                except Exception:
                    pass
            if prod:
                res_prod = dict(prod)
                res_prod["id"] = item
                return res_prod
            # Do NOT guess or infer scanner or dimensions from model suffix
            return {"id": item, "name": item}
        if hasattr(item, "id"):
            prod = catalogue_loader.get_by_id(item.id)
            return prod if prod else {"id": item.id, "name": getattr(item, "name", item.id)}
        return None

    @classmethod
    def extract_requested_attributes(cls, text: str) -> List[str]:
        text_l = text.lower()
        attrs = []
        if any(w in text_l for w in ["scan", "scanner", "scanning"]):
            attrs.append("scanner")
        if any(w in text_l for w in ["wifi", "wi-fi", "wireless", "network"]):
            attrs.append("wifi")
        if any(w in text_l for w in ["ink", "cartridge", "consumable", "ribbon"]):
            attrs.append("compatible_ink")
        if any(w in text_l for w in ["speed", "ppm", "fast", "seconds", "sec"]):
            attrs.append("speed")
        if any(w in text_l for w in ["price", "cost", "how much", "quote"]):
            attrs.append("price")
        if any(w in text_l for w in ["dimension", "dimensions", "size", "weight"]):
            attrs.append("dimensions")
        if any(w in text_l for w in ["resolution", "dpi"]):
            attrs.append("resolution")
        if any(w in text_l for w in ["warranty", "guarantee"]):
            attrs.append("warranty")
        if any(w in text_l for w in ["paper", "media", "roll"]):
            attrs.append("paper_handling")
        return attrs

    @classmethod
    def is_topic_switch(cls, text: str) -> bool:
        text_l = text.lower()
        return bool(re.search(r"\b(?:forget\s+(?:this|that)|never\s*mind|switch\s+to|now\s+i\s+need|actually\s+now|start\s+over|different\s+printer)\b", text_l))

    @classmethod
    def _get_product_width(cls, p: Dict[str, Any]) -> int:
        w = p.get("width") or p.get("print_width") or p.get("max_width_inches")
        if w is not None:
            try:
                return int(float(w))
            except (ValueError, TypeError):
                pass
        psz = str(p.get("paper_size") or "")
        pid = str(p.get("id") or "")
        if "36" in psz or re.search(r"t5\d{2}", pid):
            return 36
        if "24" in psz or re.search(r"t3\d{2}", pid):
            return 24
        if "44" in psz:
            return 44
        if "64" in psz or "65" in psz:
            return 64
        return 0

    @classmethod
    def resolve_references(
        cls,
        text: str,
        state: Any,
        existing_mentioned: Optional[List[Dict[str, Any]]] = None,
    ) -> ReferenceResolutionResult:
        """
        Resolves customer references to concrete catalogue product dictionaries.
        """
        if not text:
            return ReferenceResolutionResult([], {})

        text_l = text.lower().strip()
        mapping: Dict[str, str] = {}
        resolved_prods: List[Dict[str, Any]] = []

        # Determine reference source lists from state
        active_prod = cls._to_prod_dict(getattr(state, "active_product", None))
        displayed_ids = getattr(state, "displayed_product_ids", []) or []
        seen_disp = set()
        displayed_prods = []
        for pid in displayed_ids:
            p = cls._to_prod_dict(pid)
            if p and p.get("id") and p["id"] not in seen_disp:
                displayed_prods.append(p)
                seen_disp.add(p["id"])

        candidate_prods_raw = getattr(state, "candidate_products", []) or []
        seen_cand = set()
        candidate_prods = []
        for cp in candidate_prods_raw:
            p = cls._to_prod_dict(cp)
            if p and p.get("id") and p["id"] not in seen_cand:
                candidate_prods.append(p)
                seen_cand.add(p["id"])

        compared_ids = getattr(state, "compared_product_ids", []) or []
        compared_prods_raw = getattr(state, "compared_products", []) or []
        if not compared_prods_raw and compared_ids:
            compared_prods_raw = compared_ids
        seen_comp = set()
        compared_prods = []
        for cp in compared_prods_raw:
            p = cls._to_prod_dict(cp)
            if p and p.get("id") and p["id"] not in seen_comp:
                compared_prods.append(p)
                seen_comp.add(p["id"])

        # Ordered pool of context products: active product takes precedence, then compared, displayed, candidates
        context_pool: List[Dict[str, Any]] = []
        seen_pids = set()
        for p in ([active_prod] if active_prod else []) + compared_prods + displayed_prods + candidate_prods:
            if p and p.get("id") and p["id"] not in seen_pids:
                context_pool.append(p)
                seen_pids.add(p["id"])

        # ── 1. Rejection / Alternative Requests ──────────────────────────────
        is_rejection = any(pat.search(text_l) for pat in cls.REJECTION_PATTERNS)
        is_alternative = bool(re.search(r"\b(?:other\s+one|other\s+model|the\s+other|another\s+model|another\s+one|show\s+another)\b", text_l))
        rejected_prod = None

        if is_rejection:
            rejected_prod = active_prod
            # Find alternative from displayed or candidate products
            alt_prod = None
            for p in context_pool:
                if active_prod and p.get("id") != active_prod.get("id"):
                    alt_prod = p
                    break
            if alt_prod:
                resolved_prods.append(alt_prod)
                pname = alt_prod.get("display_name") or alt_prod.get("name") or alt_prod.get("id")
                mapping["other one"] = pname
            return ReferenceResolutionResult(
                resolved_products=resolved_prods,
                mapping=mapping,
                is_rejection=True,
                is_alternative_request=True,
                rejected_product=rejected_prod,
            )

        # ── 2. Ordinal Resolution ("first one", "second one", "3rd printer") ───
        first_match = bool(re.search(r"\b(?:the\s+)?(?:1st|first)\s*(?:one|printer|model)?\b", text_l))
        second_match = bool(re.search(r"\b(?:the\s+)?(?:2nd|second)\s*(?:one|printer|model)?\b", text_l))
        third_match = bool(re.search(r"\b(?:the\s+)?(?:3rd|third)\s*(?:one|printer|model)?\b", text_l))

        # Filter candidates by current category if active to prevent cross-category leakage
        current_cat = getattr(state, "category", None)
        def _cat_match(p):
            if not current_cat or not p:
                return True
            pcat = (p.get("main_category") or p.get("category") or "").lower()
            pbrand = (p.get("brand") or "").lower()
            if "citizen" in current_cat or "photo_booth" in current_cat:
                return "citizen" in pcat or pbrand == "citizen"
            if "technical" in current_cat or "cad" in current_cat:
                return "technical" in pcat or "cad" in pcat or pbrand == "epson"
            if "photo" in current_cat:
                return "photo" in pcat or pbrand in ("epson", "citizen")
            return True

        valid_compared = [p for p in compared_prods if _cat_match(p)]
        valid_displayed = [p for p in displayed_prods if _cat_match(p)]
        valid_candidate = [p for p in candidate_prods if _cat_match(p)]

        ordered_list = valid_compared or valid_displayed or valid_candidate

        needs_clarification = False
        clarification_question = None

        if first_match and len(ordered_list) >= 1:
            p = ordered_list[0]
            if p not in resolved_prods:
                resolved_prods.append(p)
                pname = p.get("display_name") or p.get("name") or p.get("id")
                mapping["first one"] = pname
                mapping["first printer"] = pname

        if second_match:
            if len(ordered_list) >= 2:
                p = ordered_list[1]
                if p not in resolved_prods:
                    resolved_prods.append(p)
                    pname = p.get("display_name") or p.get("name") or p.get("id")
                    mapping["second one"] = pname
                    mapping["second printer"] = pname
            else:
                needs_clarification = True
                clarification_question = "Which second model did you mean? There is only one printer currently in our conversation."

        if third_match and len(ordered_list) >= 3:
            p = ordered_list[2]
            if p not in resolved_prods:
                resolved_prods.append(p)
                pname = p.get("display_name") or p.get("name") or p.get("id")
                mapping["third one"] = pname

        last_match = bool(re.search(r"\b(?:the\s+)?(?:last|final)\s*(?:one|printer|model)?\b", text_l))
        if last_match and ordered_list:
            p = ordered_list[-1]
            if p not in resolved_prods:
                resolved_prods.append(p)
                pname = p.get("display_name") or p.get("name") or p.get("id")
                mapping["last one"] = pname
                mapping["last printer"] = pname

        # "These two" / "both" resolution
        both_match = bool(re.search(r"\b(?:these\s+two|both\s+(?:of\s+them|models|printers|machines)\b|the\s+two\s+models|difference\s+between\s+these\s+two)\b", text_l))
        if not both_match and re.search(r"\bboth\b", text_l) and not re.search(r"\bboth\s+(?:investment|cost|options?|features?|specs?|aspects?|ways?|cases?)\b", text_l):
            both_match = True
        if both_match:
            if len(ordered_list) >= 2:
                for p in ordered_list[:2]:
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                p0 = ordered_list[0].get("display_name") or ordered_list[0].get("id")
                p1 = ordered_list[1].get("display_name") or ordered_list[1].get("id")
                mapping["these two"] = f"{p0} and {p1}"
                mapping["both"] = f"{p0} and {p1}"
            elif (active_prod and active_prod.get("id") in ("epson-sc-p900", "epson-sc-p900-roll")) or (getattr(state, "active_product_id", None) in ("epson-sc-p900", "epson-sc-p900-roll")):
                p_cut = cls._to_prod_dict("epson-sc-p900")
                p_roll = cls._to_prod_dict("epson-sc-p900-roll")
                if p_cut and p_roll:
                    if p_cut not in resolved_prods:
                        resolved_prods.append(p_cut)
                    if p_roll not in resolved_prods:
                        resolved_prods.append(p_roll)
                    mapping["these two"] = "SC-P900 standard cut-sheet and roll-adapter configurations"
                    mapping["both"] = "SC-P900 standard cut-sheet and roll-adapter configurations"

        # ── 3. Attribute References ("the one with scanner", "without scanner") ─
        if re.search(r"\b(?:the\s+one\s+with\s+scanner|scanner\s+one|model\s+with\s+scanner|which\s+one\s+scanner)\b", text_l):
            for p in context_pool:
                has_scan = p.get("has_scanner") or "scan" in p.get("functions", []) or "scan" in (p.get("summary") or "").lower()
                if has_scan:
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the one with scanner"] = pname
                    break

        if re.search(r"\b(?:the\s+one\s+without\s+scanner|without\s+scan|print\s+only\s+one)\b", text_l):
            for p in context_pool:
                has_scan = p.get("has_scanner") or "scan" in p.get("functions", [])
                if not has_scan:
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the one without scanner"] = pname
                    break

        # ── 4. Dimension / Width References ("the 36-inch one", "the wider one") ─
        if re.search(r"\b(?:the\s+)?36[\s-]*(?:inch|in|\")\s*(?:one|model|printer)?\b", text_l):
            for p in context_pool:
                w = cls._get_product_width(p)
                if w == 36:
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the 36-inch one"] = pname
                    break

        if re.search(r"\b(?:the\s+)?24[\s-]*(?:inch|in|\")\s*(?:one|model|printer)?\b", text_l):
            for p in context_pool:
                w = cls._get_product_width(p)
                if w == 24:
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the 24-inch one"] = pname
                    break

        if re.search(r"\b(?:the\s+)?wider\s*(?:one|model|printer)?\b", text_l):
            widths = []
            for p in context_pool:
                w = cls._get_product_width(p)
                widths.append((w, p))
            if widths:
                widths.sort(key=lambda x: x[0], reverse=True)
                widest_p = widths[0][1]
                if widest_p not in resolved_prods:
                    resolved_prods.append(widest_p)
                    pname = widest_p.get("display_name") or widest_p.get("name") or widest_p.get("id")
                    mapping["the wider one"] = pname

        # ── 5. Brand References ("the Epson one", "the Citizen one") ──────────
        if re.search(r"\b(?:the\s+)?citizen\s*(?:one|printer|model)?\b", text_l):
            for p in context_pool:
                if (p.get("brand") or "").lower() == "citizen":
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the Citizen one"] = pname
                    break

        if re.search(r"\b(?:the\s+)?epson\s*(?:one|printer|model)?\b", text_l):
            for p in context_pool:
                if (p.get("brand") or "").lower() == "epson":
                    if p not in resolved_prods:
                        resolved_prods.append(p)
                        pname = p.get("display_name") or p.get("name") or p.get("id")
                        mapping["the Epson one"] = pname
                    break

        # ── 6. Price References ("the cheaper one") ───────────────────────────
        if re.search(r"\b(?:the\s+)?(?:cheaper|lowest\s+price|more\s+affordable)\s*(?:one|model|printer)?\b", text_l):
            from catalog.price_resolver import price_resolver
            priced = []
            for p in context_pool:
                info = price_resolver.get_price_info(prod=p)
                if not info.get("is_request") and info.get("price"):
                    priced.append((info["price"], p))
            if len(priced) >= 2:
                priced.sort(key=lambda x: x[0])
                cheapest_p = priced[0][1]
                if cheapest_p not in resolved_prods:
                    resolved_prods.append(cheapest_p)
                    pname = cheapest_p.get("display_name") or cheapest_p.get("name") or cheapest_p.get("id")
                    mapping["the cheaper one"] = pname

        # ── 7. Deictic Demonstratives ("this", "this one", "that", "that one", "it") ──
        # In comparisons like "compare this with first one", "this" refers to active_product
        deictic_match = bool(re.search(r"\b(?:this|this\s+one|that|that\s+one|it)\b", text_l))
        if deictic_match:
            if active_prod:
                if active_prod not in resolved_prods:
                    resolved_prods.insert(0, active_prod)
                pname = active_prod.get("display_name") or active_prod.get("name") or active_prod.get("id")
                for term in ["this", "this one", "that", "that one", "it"]:
                    mapping[term] = pname
            elif len(ordered_list) >= 2 and not resolved_prods:
                needs_clarification = True
                p0 = ordered_list[0].get("display_name") or ordered_list[0].get("id")
                p1 = ordered_list[1].get("display_name") or ordered_list[1].get("id")
                clarification_question = f"Could you clarify which model you mean—the {p0} or the {p1}?"

        # ── 8. Previous / Last Model Continuity ───────────────────────────────
        if re.search(r"\b(?:previous\s+one|last\s+one|last\s+printer|model\s+you\s+showed|the\s+one\s+before)\b", text_l):
            history = getattr(state, "history_turns", []) or []
            found_prev = None
            for turn in reversed(history):
                # Search previous turn products
                prev_pid = turn.get("product_id") or turn.get("active_product_id")
                if prev_pid and (not active_prod or prev_pid != active_prod.get("id")):
                    found_prev = catalogue_loader.get_by_id(prev_pid)
                    if found_prev:
                        break
            if not found_prev and len(displayed_prods) >= 2 and active_prod:
                # Fallback to second displayed
                for dp in displayed_prods:
                    if dp.get("id") != active_prod.get("id"):
                        found_prev = dp
                        break
            if found_prev and found_prev not in resolved_prods:
                resolved_prods.append(found_prev)
                pname = found_prev.get("display_name") or found_prev.get("name") or found_prev.get("id")
                mapping["previous one"] = pname
                mapping["last printer"] = pname

        return ReferenceResolutionResult(
            resolved_products=resolved_prods,
            mapping=mapping,
            is_rejection=is_rejection,
            is_alternative_request=is_alternative,
            rejected_product=rejected_prod,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
        )

    @classmethod
    def resolve_comparison_targets(cls, text: str, state: Any) -> List[str]:
        """
        Resolves products being compared from conversational text and state context.
        E.g. 'compare this with first one', 'T5100 vs T5700D', 'Citizen CX-02 and CY-02'
        """
        res = cls.resolve_references(text, state)
        target_ids: List[str] = []
        for p in res.resolved_products:
            pid = p.get("id") if isinstance(p, dict) else str(p)
            if pid and pid not in target_ids:
                target_ids.append(pid)
        return target_ids


reference_resolver = ReferenceResolver()
