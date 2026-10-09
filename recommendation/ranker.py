"""
Deterministic Product Ranker.
Scores candidate products based on explicit Python rules, never by LLM intuition.
Application match: 30
Print size match: 25
Scanner match: 20
Usage / Volume: 15
Optional features: 10
"""
from typing import List, Dict, Any, Tuple
from recommendation.eligibility import AssessmentResult
from catalog.schema import NormalizedProduct


class ProductRanker:
    def rank_candidates(self, assessments: List[AssessmentResult], requirements: Dict[str, Any], raw_message: str = "") -> List[Tuple[NormalizedProduct, float, Dict[str, Any]]]:
        """
        Ranks eligible candidate products using dynamic scoring based on customer stated priorities:
        use case, volume, portability, speed, and preferred features.
        """
        msg_l = (raw_message or "").lower()
        req_keys_str = " ".join(str(k) + ":" + str(v) for k, v in requirements.items()).lower()
        combined_text = f"{msg_l} {req_keys_str}"

        # ── Detect Customer Priorities Dynamically ───────────────────────────
        # Use only the raw message for priority detection to avoid false matches
        # on requirement key names (e.g., 'daily_volume' should not trigger volume priority)
        priority_text = msg_l
        is_portability_priority = any(k in priority_text for k in ["portable", "portability", "compact", "lightweight", "light", "travel", "carry", "mobile", "small footprint", "transport", "flight case", "limited space"])
        is_speed_priority = any(k in priority_text for k in ["speed", "fast", "faster", "fastest", "quick", "seconds", "throughput", "rapid"])
        is_volume_priority = any(k in priority_text for k in ["high volume", "high-volume", "700", "500", "600", "800", "busy", "capacity", "unattended", "continuous", "heavy duty", "production"])
        is_quality_priority = any(k in priority_text for k in ["quality", "image quality", "resolution", "fine art", "600 dpi", "color", "skin tone", "archival"])

        # Base weights total exactly 100.0
        base_weights = {
            "use_case": 25.0,
            "volume": 20.0,
            "portability": 15.0,
            "speed": 15.0,
            "preferred_features": 15.0,
            "size_fit": 10.0,
        }
        weights = dict(base_weights)

        # Resolve overlapping priorities explicitly and normalize
        active_priorities = []
        if is_portability_priority:
            active_priorities.append("portability")
        if is_speed_priority:
            active_priorities.append("speed")
        if is_volume_priority:
            active_priorities.append("volume")
        if is_quality_priority:
            active_priorities.append("use_case")

        if active_priorities:
            bonus = 24.0 / len(active_priorities)
            for p_key in active_priorities:
                weights[p_key] += bonus
            non_p = [k for k in weights if k not in active_priorities]
            reduction = 24.0 / len(non_p)
            for np_key in non_p:
                weights[np_key] = max(5.0, weights[np_key] - reduction)

        # Explicit normalization ensuring weights always total 100.0
        total_w = sum(weights.values())
        weights = {k: round((v / total_w) * 100.0, 2) for k, v in weights.items()}
        diff = round(100.0 - sum(weights.values()), 2)
        if diff != 0.0:
            lead_key = max(weights.keys(), key=lambda k: weights[k])
            weights[lead_key] = round(weights[lead_key] + diff, 2)

        ranked = []
        for item in assessments:
            p = item.product
            specs = p.verified
            p_name_l = p.name.lower()
            p_desc_l = ((p.description or "") + " " + (p.comparison_highlights or "") + " " + " ".join(specs.applications or [])).lower()

            score_factors = {}
            score = 0.0

            # 1. Use Case Alignment
            req_app = str(requirements.get("application") or "")
            req_cat = str(requirements.get("category") or "")
            use_case_pts = 0.0
            if "photo booth" in combined_text or "booth" in combined_text or "event" in combined_text:
                if p.category == "photo_booth":
                    use_case_pts = 100.0
                elif "dye-sub" in p_desc_l:
                    use_case_pts = 80.0
                else:
                    use_case_pts = 30.0
            elif "fine art" in combined_text or "gallery" in combined_text or "studio" in combined_text:
                if p.category == "photo_fine_art":
                    use_case_pts = 100.0
                elif p.category == "photo_booth" and p.id == "citizen-cx-02w":
                    use_case_pts = 85.0
                else:
                    use_case_pts = 50.0
            elif "cad" in combined_text or "technical" in combined_text:
                if p.category == "technical_cad":
                    # Standard single-roll plotters are the default CAD recommendation
                    # Production dual-roll plotters rank lower unless volume/speed is prioritized
                    vol_val = requirements.get("event_volume") or requirements.get("daily_volume")
                    has_cad_volume = vol_val in ("medium", "moderate", "mid", "high", "large", "production") or is_volume_priority or is_speed_priority
                    if p.id in ("epson-t5700d",) and not has_cad_volume:
                        use_case_pts = 80.0  # Production plotter without production need
                    else:
                        use_case_pts = 100.0
                else:
                    use_case_pts = 20.0
            elif "scanner" in combined_text or p.category == "scanner":
                req_st = requirements.get("scanner_type")
                if req_st == "sheetfed":
                    if p.id in ("epson-ds-530ii", "epson-ds-800wn", "epson-ds-900wn"):
                        use_case_pts = 100.0
                    elif "flatbed" in p_name_l:
                        use_case_pts = 30.0
                    else:
                        use_case_pts = 80.0
                elif req_st == "flatbed":
                    if "12000xl" in p.id.lower() or "flatbed" in p_name_l:
                        use_case_pts = 100.0
                    else:
                        use_case_pts = 30.0
                else:
                    use_case_pts = 90.0
            else:
                use_case_pts = 80.0
            score_factors["use_case"] = round(use_case_pts * (weights["use_case"] / 100.0), 1)
            score += score_factors["use_case"]

            # 2. Volume Alignment
            vol_val = requirements.get("event_volume") or requirements.get("daily_volume")
            exact_v = requirements.get("exact_daily_volume")
            cat = p.category or ""
            vol_pts = 50.0

            if cat == "technical_cad":
                is_high_vol = vol_val in ("high", "large", "production") or (isinstance(vol_val, (int, float)) and vol_val >= 50) or (isinstance(exact_v, (int, float)) and exact_v >= 50)
                is_med_vol = vol_val in ("medium", "moderate", "mid") or (isinstance(vol_val, (int, float)) and 10 <= vol_val < 50) or (isinstance(exact_v, (int, float)) and 10 <= exact_v < 50)
                is_low_vol = vol_val in ("low", "small", "light") or (isinstance(vol_val, (int, float)) and vol_val < 10) or (isinstance(exact_v, (int, float)) and exact_v < 10)
            else:
                is_high_vol = vol_val in ("high", "large", "production") or (isinstance(vol_val, (int, float)) and vol_val >= 200) or (isinstance(exact_v, (int, float)) and exact_v >= 200)
                is_med_vol = vol_val in ("medium", "moderate", "mid") or (isinstance(vol_val, (int, float)) and 50 <= vol_val < 200) or (isinstance(exact_v, (int, float)) and 50 <= exact_v < 200)
                is_low_vol = vol_val in ("low", "small", "light") or (isinstance(vol_val, (int, float)) and vol_val < 50) or (isinstance(exact_v, (int, float)) and exact_v < 50)

            if is_high_vol:
                if cat == "technical_cad":
                    vol_pts = 100.0 if "t5700" in p.id else (85.0 if "t5400" in p.id else 40.0)
                else:
                    if p.id in ("citizen-cy-02", "epson-sc-t5700d", "epson-t5700d", "epson-sc-p9500", "epson-am-c4000") or "c4000" in p.id or "production" in p_name_l:
                        vol_pts = 100.0
                    elif p.id in ("citizen-cx-02", "epson-am-c550") or "c550" in p.id:
                        vol_pts = 75.0
                    elif p.id == "citizen-cz-01":
                        vol_pts = 40.0
                    else:
                        vol_pts = 70.0
            elif is_med_vol:
                if cat == "technical_cad":
                    vol_pts = 100.0 if "t5400" in p.id else (80.0 if "t5700" in p.id else (60.0 if "t5100" in p.id else 50.0))
                else:
                    if p.id in ("citizen-cx-02", "citizen-cx-02w", "epson-am-c550", "epson-am-c4000") or "c550" in p.id or "c4000" in p.id:
                        vol_pts = 100.0
                    else:
                        vol_pts = 70.0
            elif is_low_vol:
                if cat == "technical_cad":
                    vol_pts = 100.0 if ("t5100" in p.id or "t3100" in p.id) else (60.0 if "t5400" in p.id else 40.0)
                else:
                    if p.id in ("citizen-cz-01", "epson-sc-t3100", "epson-t3100", "epson-p700"):
                        vol_pts = 100.0
                    elif p.id in ("citizen-cx-02", "epson-am-c550") or "c550" in p.id:
                        vol_pts = 95.0
                    elif "c4000" in p.id:
                        vol_pts = 85.0
                    else:
                        vol_pts = 50.0
            elif is_volume_priority:
                if p.id == "citizen-cy-02" or "production" in p_name_l or "t5700" in p.id:
                    vol_pts = 100.0
                elif p.id in ("citizen-cx-02", "citizen-cx-02w", "epson-am-c550") or "c550" in p.id or "t5400" in p.id:
                    vol_pts = 70.0
                else:
                    vol_pts = 40.0
            else:
                vol_pts = 70.0
            score_factors["volume"] = round(vol_pts * (weights["volume"] / 100.0), 1)
            score += score_factors["volume"]

            # 3. Portability Alignment
            port_pts = 50.0
            if p.id == "citizen-cz-01":
                port_pts = 100.0  # 5.8 kg ultra-compact
            elif p.id == "citizen-cx-02":
                port_pts = 80.0   # 12 kg portable
            elif p.id == "citizen-cx-02w":
                port_pts = 65.0   # 14 kg
            elif p.id == "citizen-cy-02":
                port_pts = 45.0   # 13.8 kg high-capacity
            elif p.id in ("epson-sc-p700", "epson-ds-530ii", "epson-am-c550", "epson-sc-t3100"):
                port_pts = 70.0   # compact desktop
            else:
                port_pts = 30.0   # large floor-standing
            score_factors["portability"] = round(port_pts * (weights["portability"] / 100.0), 1)
            score += score_factors["portability"]

            # 4. Speed Alignment
            speed_pts = 50.0
            if p.id == "citizen-cx-02":
                speed_pts = 95.0  # 9.8s high-speed 4x6, 15.6s 6x8
            elif p.id == "citizen-cy-02":
                speed_pts = 85.0  # 12.4s high-speed 4x6
            elif p.id == "citizen-cz-01":
                speed_pts = 70.0  # 18.8s 4x6
            elif p.id == "citizen-cx-02w":
                speed_pts = 70.0  # 33.4s 8x10
            elif p.id in ("epson-sc-t5700d", "epson-t5700d", "epson-am-c4000"):
                # Production speed premium only when speed is actually prioritized
                speed_pts = 95.0 if is_speed_priority else 65.0
            else:
                speed_pts = 60.0
            score_factors["speed"] = round(speed_pts * (weights["speed"] / 100.0), 1)
            score += score_factors["speed"]

            # 5. Preferred Features Alignment
            feat_pts = 50.0
            if any(k in combined_text for k in ["ribbon rewind", "rewind"]):
                feat_pts = 100.0 if p.id in ("citizen-cx-02", "citizen-cx-02w") else 20.0
            elif any(k in combined_text for k in ["gloss", "matte", "finishing", "luster"]):
                feat_pts = 100.0 if p.category in ("photo_booth", "photo_fine_art") else 40.0
            elif any(k in combined_text for k in ["grey calibration", "gray calibration"]):
                feat_pts = 100.0 if p.id == "citizen-cx-02w" else 30.0
            elif any(k in combined_text for k in ["dual roll", "two rolls"]):
                feat_pts = 100.0 if p.id == "epson-sc-t5700d" else 20.0
            elif any(k in combined_text for k in ["heat-free", "line head"]):
                feat_pts = 100.0 if "epson-am-c" in p.id else 30.0
            else:
                feat_pts = 70.0
            score_factors["preferred_features"] = round(feat_pts * (weights["preferred_features"] / 100.0), 1)
            score += score_factors["preferred_features"]

            # 6. Size Fit (Exact vs Over-width)
            size_pts = 80.0
            if "print_size" in item.matched:
                size_pts = 100.0
            score_factors["size_fit"] = round(size_pts * (weights["size_fit"] / 100.0), 1)
            score += score_factors["size_fit"]

            score_factors["applied_weights"] = dict(weights)
            ranked.append((p, round(score, 1), score_factors))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked


product_ranker = ProductRanker()
