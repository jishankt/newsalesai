"""
Kepler Tech Inkjet Media Registry.
Authoritative verified registry of Innova Art, Olmec, Korejet, and Epson Media.
Direct links to https://www.keplertechllc.com.
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MediaProduct:
    sku: str
    name: str
    family_code: str
    brand: str  # "Innova Art", "Olmec", "Korejet", "Epson"
    category: str  # "fine_art", "photo", "canvas", "signage", "technical"
    surface_finish: str
    weight_gsm: Optional[int]
    format_type: str  # "roll" or "sheet"
    size_label: str
    width_inches: Optional[float]
    ink_compatibility: List[str]
    compatible_printers: List[str]
    url: str
    image_url: str


class MediaRegistry:
    def __init__(self, json_path: Optional[str] = None):
        self.products: List[MediaProduct] = []
        self.sku_map: Dict[str, MediaProduct] = {}
        self.family_map: Dict[str, List[MediaProduct]] = {}
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.json_path = json_path or os.path.join(base_dir, "data", "media_products.json")
        self._initialize()

    def _initialize(self):
        if not os.path.exists(self.json_path):
            return
        with open(self.json_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        for r in records:
            p = MediaProduct(
                sku=r.get("sku", ""),
                name=r.get("name", ""),
                family_code=r.get("family_code", ""),
                brand=r.get("brand", ""),
                category=r.get("category", ""),
                surface_finish=r.get("surface_finish", ""),
                weight_gsm=r.get("weight_gsm"),
                format_type=r.get("format_type", "roll"),
                size_label=r.get("size_label", ""),
                width_inches=r.get("width_inches"),
                ink_compatibility=r.get("ink_compatibility", []),
                compatible_printers=r.get("compatible_printers", []),
                url=r.get("url", ""),
                image_url=r.get("image_url", ""),
            )
            self.products.append(p)
            sku_clean = p.sku.upper().strip()
            if sku_clean:
                self.sku_map[sku_clean] = p
            fam_clean = p.family_code.upper().strip()
            if fam_clean:
                self.family_map.setdefault(fam_clean, []).append(p)

    def get_by_sku(self, sku: str) -> Optional[MediaProduct]:
        sku_clean = (sku or "").upper().strip()
        if sku_clean in self.sku_map:
            return self.sku_map[sku_clean]
        for k, v in self.sku_map.items():
            if sku_clean.replace("-", "").replace(" ", "") == k.replace("-", "").replace(" ", ""):
                return v
        return None

    def get_by_category(self, category: str, limit: int = 20) -> List[MediaProduct]:
        cat_low = (category or "").lower().strip()
        if cat_low in ("fine_art", "fine art", "art", "cotton", "rag"):
            c_key = "fine_art"
        elif cat_low in ("photo", "photo paper", "luster", "gloss"):
            c_key = "photo"
        elif cat_low in ("canvas", "canvases", "gallery wrap"):
            c_key = "canvas"
        elif cat_low in ("signage", "wallpaper", "eco-solvent", "eco solvent"):
            c_key = "signage"
        elif cat_low in ("technical", "cad", "proofing"):
            c_key = "technical"
        else:
            c_key = cat_low

        matches = [p for p in self.products if p.category == c_key]
        return matches[:limit]

    def get_for_printer(self, printer_id: str, category: Optional[str] = None, limit: int = 15) -> List[MediaProduct]:
        pid = (printer_id or "").lower().strip()
        results = []
        for p in self.products:
            if any(pid in cp or cp in pid for cp in p.compatible_printers):
                if category and p.category != category:
                    continue
                results.append(p)
        return results[:limit]

    def get_by_format_or_width(
        self,
        width_inches: Optional[float] = None,
        format_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 6
    ) -> List[MediaProduct]:
        cat_low = (category or "").lower().strip()
        if cat_low in ("all", "general", "general_roll", "rolls", "any", "none"):
            cat_low = ""
        results = []
        for p in self.products:
            if cat_low and p.category != cat_low:
                continue
            if width_inches is not None:
                if p.width_inches != width_inches and f"{int(width_inches)}" not in p.size_label:
                    continue
            if format_type is not None:
                if p.format_type != format_type:
                    continue
            results.append(p)

        if len(results) < limit and cat_low:
            for p in self.products:
                if p in results:
                    continue
                if width_inches is not None and (p.width_inches == width_inches or f"{int(width_inches)}" in p.size_label):
                    results.append(p)
                elif format_type is not None and p.format_type == format_type:
                    results.append(p)
                if len(results) >= limit:
                    break
        return results[:limit]

    def search_media(self, query: str, limit: int = 10) -> List[MediaProduct]:
        q_low = (query or "").lower().strip()
        tokens = [t for t in q_low.split() if len(t) >= 2]
        scored = []
        for p in self.products:
            text = f"{p.name} {p.sku} {p.family_code} {p.brand} {p.category} {p.surface_finish}".lower()
            score = sum(1 for t in tokens if t in text)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]


media_registry = MediaRegistry()
