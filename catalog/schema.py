"""
Normalized Product Schema for Kepler Tech Catalog.
Strictly enforces:
  null != false
  null: Unknown / not verified in catalog
  false: Verified not present / not supported
  true: Verified supported
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class VerifiedSpecs:
    max_width_mm: Optional[int] = None
    max_width_label: Optional[str] = None  # e.g., "36 inch / A0"
    has_scanner: Optional[bool] = None     # True = has scanner, False = verified no scanner, None = unknown
    resolution: Optional[str] = None       # e.g., "2400 x 1200 dpi"
    speed: Optional[str] = None            # e.g., "A1 CAD print in 31 seconds" or "55 ppm"
    speed_ppm: Optional[int] = None
    ink_technology: Optional[str] = None   # e.g., "UltraChrome XD2"
    connectivity: List[str] = field(default_factory=list)  # e.g., ["Wi-Fi", "Ethernet", "USB"]
    applications: List[str] = field(default_factory=list)  # e.g., ["CAD", "Architecture", "GIS"]
    cartridge_capacities: Optional[str] = None
    media_handling: Optional[str] = None
    footprint: Optional[str] = None
    dimensions: Optional[str] = None
    weight: Optional[str] = None
    warranty: Optional[str] = None
    duplex: Optional[bool] = None
    supported_print_sizes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_width_mm": self.max_width_mm,
            "max_width_label": self.max_width_label,
            "has_scanner": self.has_scanner,
            "resolution": self.resolution,
            "speed": self.speed,
            "speed_ppm": self.speed_ppm,
            "ink_technology": self.ink_technology,
            "connectivity": list(self.connectivity),
            "applications": list(self.applications),
            "cartridge_capacities": self.cartridge_capacities,
            "media_handling": self.media_handling,
            "footprint": self.footprint,
            "dimensions": self.dimensions,
            "weight": self.weight,
            "warranty": self.warranty,
            "duplex": self.duplex,
            "supported_print_sizes": list(self.supported_print_sizes),
        }


@dataclass
class ProductSource:
    website_url: Optional[str] = None
    source_type: str = "kepler_catalog"
    verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "website_url": self.website_url,
            "source_type": self.source_type,
            "verified": self.verified,
        }


@dataclass
class NormalizedProduct:
    id: str
    brand: str
    model: str
    name: str
    category: str = "technical_cad"  # technical_cad, photo_fine_art, office_enterprise, scanner, photo_booth, consumable
    entity_type: str = "printer"  # printer, scanner, consumable, media, accessory, software
    canonical_id: Optional[str] = None
    display_name: Optional[str] = None
    product_url: Optional[str] = None
    datasheet_url: Optional[str] = None
    structured_specs: Dict[str, Any] = field(default_factory=dict)
    sku: Optional[str] = None
    verified: VerifiedSpecs = field(default_factory=VerifiedSpecs)
    source: ProductSource = field(default_factory=ProductSource)
    price: Optional[float] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    full_description: Optional[str] = None
    feature_headings: List[str] = field(default_factory=list)
    specifications_table: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    consumables: List[str] = field(default_factory=list)
    comparison_highlights: Optional[str] = None
    supported_print_sizes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        img = self.image_url or "https://www.keplertechllc.com/wp-content/uploads/2023/05/Kepler-Logo-.png"
        src_url = self.source.website_url or "https://www.keplertechllc.com/"
        real_sku = self.sku or self.id
        price_str = f"AED {self.price:,.2f}" if (self.price is not None and self.price > 0) else "Price on Request"
        vat_note = "(Excl. VAT)" if (self.price is not None and self.price > 0) else ""
        sizes = self.supported_print_sizes or self.verified.supported_print_sizes or []
        return {
            "id": self.id,
            "canonical_id": self.canonical_id or self.id,
            "entity_type": self.entity_type,
            "display_name": self.display_name or self.name,
            "sku": real_sku,
            "brand": self.brand,
            "model": self.model,
            "name": self.name,
            "category": self.category,
            "verified": self.verified.to_dict(),
            "source": self.source.to_dict(),
            "product_url": self.product_url or src_url,
            "datasheet_url": self.datasheet_url,
            "structured_specs": dict(self.structured_specs),
            "price": self.price,
            "price_formatted": price_str,
            "price_str": price_str,
            "vat_note": vat_note,
            "currency": "AED",
            "stock": self.stock,
            "image_url": img,
            "image": img,
            "url": src_url,
            "source_url": src_url,
            "website_url": src_url,
            "web_url": src_url,
            "description": self.description,
            "full_description": self.full_description or self.description,
            "feature_headings": list(self.feature_headings),
            "specifications_table": dict(self.specifications_table),
            "tags": list(self.tags),
            "consumables": list(self.consumables),
            "comparison_highlights": self.comparison_highlights,
            "supported_print_sizes": list(sizes),
            "width": self.verified.max_width_label,
            "print_sizes": self.verified.max_width_label,
            "speed": getattr(self.verified, "speed", None),
            "print_speed": getattr(self.verified, "speed", None),
            "dimensions": self.verified.dimensions,
            "weight": self.verified.weight,
            "capacity": self.verified.cartridge_capacities,
            "roll_capacity": self.verified.cartridge_capacities,
            "ink_technology": self.verified.ink_technology,
            "has_scanner": self.verified.has_scanner,
        }

