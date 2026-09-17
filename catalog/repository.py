"""
Catalog Repository & Normalizer.
Loads and unifies raw catalog data into NormalizedProduct models with strict 3-valued logic.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from catalog.schema import NormalizedProduct, VerifiedSpecs, ProductSource

logger = logging.getLogger("catalog:repository")


class CatalogRepository:
    def __init__(self, corpus_path: Optional[str] = None, products_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent / "data"
        self.corpus_path = Path(corpus_path) if corpus_path else base_dir / "kepler_product_corpus.json"
        self.products_path = Path(products_path) if products_path else base_dir / "products.json"
        
        self.products_by_id: Dict[str, NormalizedProduct] = {}
        self.products_by_category: Dict[str, List[NormalizedProduct]] = {}
        self._load_and_normalize()

    def _load_and_normalize(self):
        """Loads and normalizes all products into canonical models."""
        # 1. Load kepler_product_corpus.json if available
        if self.corpus_path.exists():
            try:
                with open(self.corpus_path, "r", encoding="utf-8") as f:
                    corpus_data = json.load(f)
                    for item in corpus_data:
                        norm = self._normalize_corpus_item(item)
                        if norm:
                            self.products_by_id[norm.id] = norm
            except Exception as e:
                logger.error(f"Error loading corpus {self.corpus_path}: {e}")

        # 2. Enrich and link with high-res verified images and URLs from products.json
        if self.products_path.exists():
            try:
                with open(self.products_path, "r", encoding="utf-8") as f:
                    products_data = json.load(f)
                    for item in products_data:
                        sku = str(item.get("sku") or item.get("_id") or "").upper()
                        name_l = item.get("name", "").lower()
                        img = item.get("image_url") or item.get("image")
                        web_url = item.get("website_url") or item.get("web_url")
                        consumables = item.get("consumables", [])

                        # Match against normalized products
                        for p in self.products_by_id.values():
                            p_match = False
                            if p.id in ("epson-am-c4000",) and ("am-c4000" in name_l or "am-c400" in name_l):
                                p_match = True
                            elif p.id in ("epson-am-c550",) and ("am-c550" in name_l):
                                p_match = True
                            elif p.id in ("epson-t3100",) and ("t3100" in name_l or "t3100" in sku.lower()):
                                p_match = True
                            elif p.id in ("epson-t5100",) and ("t5100" in name_l or "t5100" in sku.lower()):
                                p_match = True
                            elif p.id in ("epson-t5100m",) and ("t5100m" in name_l or "t5100m" in sku.lower()):
                                p_match = True
                            elif p.id in ("epson-t5400m",) and ("t5400m" in name_l or "t5400" in name_l or "t5400m" in sku.lower()):
                                p_match = True
                            elif p.id in ("epson-t5700d",) and ("t5700" in name_l or "t3700" in name_l):
                                p_match = True
                            elif p.id in ("epson-p700",) and ("p700" in name_l and "7000" not in name_l and "7500" not in name_l):
                                p_match = True
                            elif p.id in ("epson-p900",) and ("p900" in name_l and "9000" not in name_l and "9500" not in name_l):
                                p_match = True
                            elif p.id == "epson-p7500" and "p7500" in name_l:
                                p_match = True
                            elif p.id == "epson-p9500" and "p9500" in name_l:
                                p_match = True
                            elif p.id in ("citizen-cx-02",) and ("cx-02" in name_l or "cx02" in name_l):
                                p_match = True
                            elif p.id in ("citizen-cy-02",) and ("cy-02" in name_l or "cy02" in name_l):
                                p_match = True
                            elif p.id in ("epson-sc-f100", "epson-f100") and ("f100" in name_l):
                                p_match = True
                            elif p.id in ("epson-sc-f500", "epson-f500") and ("f500" in name_l):
                                p_match = True

                            if p_match:
                                if sku and not p.sku and not sku.startswith("EPSON-"):
                                    p.sku = sku
                                if img and not p.image_url:
                                    p.image_url = img
                                if web_url and not p.source.website_url:
                                    p.source.website_url = web_url
                                if consumables and not p.consumables:
                                    p.consumables = consumables
            except Exception as e:
                logger.error(f"Error enriching products {self.products_path}: {e}")

        # Explicit verified media, identity, and structured specifications for catalog items
        VERIFIED_HARDWARE_MEDIA = {
            "epson-am-c4000": {
                "sku": "C11CJ43402BY",
                "entity_type": "printer",
                "canonical_id": "epson-am-c4000",
                "display_name": "Epson WorkForce Enterprise AM-C4000 MFP",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/06/WorkForce-Enterprise%E2%80%8B-AM-C4000%E2%80%8B.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-workforce-enterprise-am-c4000-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/06/Epson-WorkForce-Enterprise-WF-AM-C4000-Printer-Datasheet.pdf",
                "consumables": ["C13T08H100", "C13T08H200", "C13T08H300", "C13T08H400", "C12C937181"],
                "supported_print_sizes": ["a4", "a3", "a3+"]
            },
            "epson-am-c550": {
                "sku": "C11CJ92401",
                "entity_type": "printer",
                "canonical_id": "epson-am-c550",
                "display_name": "Epson WorkForce AM-C550 A4 Multifunction Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2025/01/Epson-WorkForce-AM-C550-A4-Color-Multifunction-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-wf-am-c550-a4-multifunction-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2025/01/Epson-WorkForce-AM-C550-A4-Color-Multifunction-Printer.pdf",
                "consumables": ["C13T08Q140", "C13T08Q240", "C13T08Q340", "C13T08Q440", "C12C937201"],
                "supported_print_sizes": ["a4"]
            },
            "epson-t3100": {
                "sku": "C11CF11301A0",
                "entity_type": "printer",
                "canonical_id": "epson-t3100",
                "display_name": "Epson SureColor SC-T3100 Wireless Technical Plotter",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/08/Epson-SureColor-SC-T3100-%E2%80%93-Wireless-Printer-With-Stand.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-t3100-wireless-printer-with-stand/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/08/Epson-SureColor-SC-T3100-Printer-Datasheet.pdf",
                "consumables": ["C13S210057", "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440", "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "24-inch"]
            },
            "epson-t5100": {
                "sku": "C11CF12301A0",
                "entity_type": "printer",
                "canonical_id": "epson-t5100",
                "display_name": "Epson SureColor SC-T5100 36\" Large Format Plotter",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/08/Epson-SureColor-SC-T5100-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-t5100-large-format-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/08/Epson-SureColor-SC-T5100-Printer-datasheet.pdf",
                "consumables": ["C13S210057", "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440", "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "a0", "36-inch"]
            },
            "epson-t5100m": {
                "sku": "C11CJ54301A1",
                "entity_type": "printer",
                "canonical_id": "epson-t5100m",
                "display_name": "Epson SureColor SC-T5100M Plotter Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2026/01/SC-T5100M.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-t5100m-plotter-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2026/01/Epson-SureColor-SC-T5100M-MFP-Brochure.pdf",
                "consumables": ["C13S210057", "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440", "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "a0", "36-inch"]
            },
            "epson-t5400m": {
                "sku": "C11CH65301A1",
                "entity_type": "printer",
                "canonical_id": "epson-t5400m",
                "display_name": "Epson SureColor SC-T5400M MFP Plotter Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2024/04/Epson-SC-T5400M-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-sc-t5400m-mfp-plotter-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2024/04/Epson-SC-T5400M-Printer-Datasheet.pdf",
                "consumables": ["C13T699700", "C13T41R240", "C13T41R340", "C13T41R440", "C13T41R540", "C13T41F240", "C13T41F340", "C13T41F440", "C13T41F540", "C13T41E240", "C13T41E340", "C13T41E440", "C13T41E540"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "a0", "36-inch"]
            },
            "epson-t5700d": {
                "sku": "C11CH81301A0",
                "entity_type": "printer",
                "canonical_id": "epson-t5700d",
                "display_name": "Epson SureColor SC-T5700D Dual-Roll Technical Plotter",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2024/01/SC-T5700DM-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-sc-t5700d-technical-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2024/01/Epson-Sure-Color-SC-T5700D-Printer-Datasheet.pdf",
                "consumables": ["C13S210115", "C13S210116", "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00", "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "a0", "36-inch"]
            },
            "epson-p700": {
                "sku": "C11CH38401",
                "entity_type": "printer",
                "canonical_id": "epson-p700",
                "display_name": "Epson SureColor SC-P700 13\" Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P7000-Printer-1.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-p700-13-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Epson-SureColor-SC-P700-13-Photo-Printer-Datasheet.pdf",
                "consumables": ["C12C935711", "C13T46S100", "C13T46S200", "C13T46S300", "C13T46S400", "C13T46S500", "C13T46S600", "C13T46S700", "C13T46S800", "C13T46S900", "C13T46SD00"],
                "supported_print_sizes": ["a4", "a3", "a3+", "13-inch", "4x6", "5x7", "8x10"]
            },
            "epson-p900": {
                "sku": "C11CH37401",
                "entity_type": "printer",
                "canonical_id": "epson-p900",
                "display_name": "Epson SureColor SC-P900 17\" Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/04/Epson-P900-Printer-2.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p900-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Epson-SureColor-SC-P900-17-Photo-Printer-Datasheet.pdf",
                "consumables": ["C12C935711", "C13T47A100", "C13T47A800", "C13T47AD00", "C13T47A200", "C13T47A300", "C13T47A400", "C13T47A500", "C13T47A600", "C13T47A700", "C13T47A900"],
                "supported_print_sizes": ["a4", "a3", "a3+", "a2", "17-inch", "4x6", "5x7", "8x10", "8x12"]
            },
            "epson-p7500": {
                "sku": "C11CH12301A0",
                "entity_type": "printer",
                "canonical_id": "epson-p7500",
                "display_name": "Epson SureColor SC-P7500 24\" Large Format Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P7500-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p7500-large-format-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Epson-SureColor-SC-P7500-Datasheet.pdf",
                "consumables": ["C13T699700", "C13T44J240", "C13T44Q240", "C13T44J740", "C13T44Q740", "C13T44JB40", "C13T44QB40", "C13T44J940", "C13T44J840", "C13T44JA40", "C13T44QA40", "C13T44JD40", "C13T44QD40", "C13T44J640", "C13T44J440", "C13T44Q440"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "24-inch"]
            },
            "epson-p9500": {
                "sku": "C11CH13301A0",
                "entity_type": "printer",
                "canonical_id": "epson-p9500",
                "display_name": "Epson SureColor SC-P9500 44\" Large Format Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P7500-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p9500-large-format-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Epson-SureColor-SC-P9500-Datasheet.pdf",
                "consumables": ["C13T699700", "C13T44J240", "C13T44Q240", "C13T44J740", "C13T44Q740", "C13T44JB40", "C13T44QB40", "C13T44J940", "C13T44J840", "C13T44JA40", "C13T44QA40", "C13T44JD40", "C13T44QD40", "C13T44J640", "C13T44J440", "C13T44Q440"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "a0", "44-inch"]
            },
            "citizen-cx-02": {
                "sku": "CX02-PHOTO",
                "entity_type": "printer",
                "canonical_id": "citizen-cx-02",
                "display_name": "Citizen CX-02 Digital Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Citizen-CX-02-Photo-Printer-Dubai.webp",
                "website_url": "https://www.keplertechllc.com/product/citizen-cx-02-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Citizen-CX-02-Photo-Printer-Datasheet.pdf",
                "consumables": ["CX2.4x6", "CX2.6X8"],
                "supported_print_sizes": ["4x6", "5x7", "6x8", "6x9"],
                "structured_specs": {
                    "print_speed": {
                        "4x6": ["8.4 seconds", "9.8 seconds"],
                        "5x7": "14.2 seconds",
                        "6x8": "15.6 seconds",
                        "6x9": "20.8 seconds",
                        "status": "conflict",
                        "conflict_note": "The Kepler Tech product page lists both 8.4 seconds and 9.8 seconds for 4x6 printing without differentiating between standard and high-speed modes."
                    },
                    "max_width": {
                        "value": 6,
                        "unit": "inches",
                        "status": "inferred",
                        "note": "6 inches inferred from listed 6x8 and 6x9 media sizes; website does not provide a separate maximum-width field."
                    },
                    "technology": {
                        "value": "Dye sublimation thermal system with an overcoat",
                        "status": "verified"
                    },
                    "liquid_ink": {
                        "uses_liquid_ink": False,
                        "status": "inferred",
                        "note": "Dye-sublimation ribbon and paper media [VERIFIED]; therefore, it does not use conventional liquid-ink cartridges [INFERRED]."
                    },
                    "resolution": {
                        "options": ["300 dpi", "600 dpi"],
                        "status": "verified"
                    },
                    "print_modes": {
                        "options": ["High Speed", "High Quality"],
                        "status": "verified",
                        "note": "Exact 300x300 and 300x600 mode mapping is not confirmed on the Kepler Tech website."
                    },
                    "finishes": {
                        "options": ["Glossy", "Matte"],
                        "status": "conflict",
                        "conflict_note": "Product summary mentions Gloss, Luster, and Matte, but specification table lists only Glossy / Matte."
                    },
                    "ribbon_rewind": {
                        "supported": True,
                        "status": "verified",
                        "description": "Rewinds the unused half of the thermal ribbon when producing 4x6 prints on 6x8 media to eliminate consumable waste."
                    },
                    "capacity": {
                        "4x6": "400 sheets",
                        "5x7": "230 sheets per roll",
                        "6x8": "200 sheets per roll",
                        "6x9": "180 sheets per roll",
                        "status": "verified"
                    },
                    "weight": {
                        "product_weight": "12 kg",
                        "package_weight": "13.5 kg",
                        "status": "verified"
                    },
                    "dimensions": {
                        "product_dimensions": "27.5 x 36.6 x 17 cm",
                        "package_dimensions": "39 x 50 x 33.5 cm",
                        "status": "verified"
                    },
                    "interface": {
                        "value": "USB 2.0 full speed",
                        "status": "verified"
                    },
                    "media_compatibility": {
                        "CX2.4x6": "Verified genuine 4x6 media pack (Model: CX2-MS46-2PC, SKU: CX2.4x6).",
                        "CX2-MS46-2PC": "Verified genuine 4x6 media pack (Model: CX2-MS46-2PC, SKU: CX2.4x6).",
                        "CX2.6X8": "Verified genuine 6x8 media pack (Model: CX2-MS68, SKU: CX2.6X8)."
                    }
                }
            },
            "citizen-cy-02": {
                "sku": "CY02-PHOTO",
                "entity_type": "printer",
                "canonical_id": "citizen-cy-02",
                "display_name": "Citizen CY-02 Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/04/Citizen-CY-02-Photo-Printer.webp",
                "website_url": "https://www.keplertechllc.com/product/citizen-cy-02-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Citizen-CY-02-Photo-Printer-Datasheet.pdf",
                "consumables": ["CY-MS46", "CY-MS68"],
                "supported_print_sizes": ["4x6", "5x7", "6x8"],
                "structured_specs": {
                    "print_speed": {
                        "4x6": "12.4 seconds",
                        "5x7": "19.9 seconds",
                        "6x8": "21.9 seconds",
                        "status": "verified"
                    },
                    "max_width": {
                        "value": 6,
                        "unit": "inches",
                        "status": "inferred",
                        "note": "6 inches inferred from listed 6x8 media size."
                    },
                    "technology": {
                        "value": "Dye sublimation thermal system with overcoat",
                        "status": "verified"
                    },
                    "liquid_ink": {
                        "uses_liquid_ink": False,
                        "status": "inferred",
                        "note": "Dye-sublimation ribbon and paper media [VERIFIED]; therefore, it does not use conventional liquid-ink cartridges [INFERRED]."
                    },
                    "resolution": {
                        "options": ["300 dpi", "600 dpi"],
                        "status": "verified"
                    },
                    "print_modes": {
                        "options": ["High Speed", "High Quality"],
                        "status": "verified"
                    },
                    "finishes": {
                        "options": ["Glossy", "Matte"],
                        "status": "verified"
                    },
                    "ribbon_rewind": {
                        "supported": False,
                        "status": "verified"
                    },
                    "capacity": {
                        "4x6": "700 sheets per roll",
                        "5x7": "350 sheets per roll",
                        "6x8": "350 sheets per roll",
                        "status": "verified"
                    },
                    "weight": {
                        "product_weight": "13.8 kg",
                        "package_weight": "16.5 kg",
                        "status": "verified"
                    },
                    "dimensions": {
                        "product_dimensions": "32.2 x 35.1 x 28.1 cm",
                        "package_dimensions": "44 x 55 x 41.51 cm",
                        "status": "verified"
                    },
                    "interface": {
                        "value": "USB 2.0 full speed",
                        "status": "verified"
                    },
                    "media_compatibility": {
                        "CY-MS46": "Verified genuine 4x6 media pack (Model: CY-MS46, SKU: CY-MS46).",
                        "CY-MS68": "Verified genuine 6x8 media pack (Model: CY-MS68, SKU: CY-MS68)."
                    }
                }
            },
            "citizen-cz-01": {
                "sku": "CZ01-PHOTO",
                "entity_type": "printer",
                "canonical_id": "citizen-cz-01",
                "display_name": "Citizen CZ-01 Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/04/Citizen-CZ-01-Photo-Printer-600x600.webp",
                "website_url": "https://www.keplertechllc.com/product/citizen-cz-01-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Citizen-CZ-01-Photo-Printer-Datasheet.pdf",
                "consumables": ["CZ-MS46", "CZ-MS458"],
                "supported_print_sizes": ["4x4", "4x6", "4.5x4.5", "4.5x8"],
                "structured_specs": {
                    "print_speed": {
                        "4x4": "16.3 seconds",
                        "4x6": "18.8 seconds",
                        "4.5x4.5": "19.5 seconds",
                        "4.5x8": "23.1 seconds",
                        "status": "verified"
                    },
                    "max_width": {
                        "value": 4.5,
                        "unit": "inches",
                        "status": "inferred",
                        "note": "4.5 inches inferred from listed 4.5x8 media size."
                    },
                    "technology": {
                        "value": "Dye sublimation thermal system with overcoat",
                        "status": "verified"
                    },
                    "liquid_ink": {
                        "uses_liquid_ink": False,
                        "status": "inferred",
                        "note": "Dye-sublimation ribbon and paper media [VERIFIED]; therefore, it does not use conventional liquid-ink cartridges [INFERRED]."
                    },
                    "resolution": {
                        "options": ["300 dpi", "600 dpi"],
                        "status": "verified"
                    },
                    "print_modes": {
                        "options": ["High Speed", "High Quality"],
                        "status": "verified"
                    },
                    "finishes": {
                        "options": ["Glossy", "Matte", "Partial Matte"],
                        "status": "verified"
                    },
                    "capacity": {
                        "4x4": "150 sheets per roll",
                        "4x6": "150 sheets per roll",
                        "4.5x4.5": "110 sheets per roll",
                        "4.5x8": "110 sheets per roll",
                        "status": "verified"
                    },
                    "weight": {
                        "product_weight": "5.8 kg",
                        "package_weight": "8.5 kg",
                        "status": "verified"
                    },
                    "dimensions": {
                        "product_dimensions": "20.8 x 24.0 x 19.8 cm",
                        "package_dimensions": "30 x 34 x 30 cm",
                        "status": "verified"
                    },
                    "interface": {
                        "value": "USB 2.0 full speed",
                        "status": "verified"
                    },
                    "media_compatibility": {
                        "CZ-MS46": "Verified genuine 4x6 media pack (Model: CZ-MS46, SKU: CZ-MS46).",
                        "CZ-MS458": "Verified genuine 4.5x8 media pack (Model: CZ-MS458, SKU: CZ-MS458)."
                    }
                }
            },
            "citizen-cx-02w": {
                "sku": "CX02W-PHOTO",
                "entity_type": "printer",
                "canonical_id": "citizen-cx-02w",
                "display_name": "Citizen CX-02W 8\" Large Photo Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/04/Citizen-CX-02W-Photo-Printer-300x300.webp",
                "website_url": "https://www.keplertechllc.com/product/citizen-cx-02w-large-photo-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/05/Citizen-CX-02W-Large-Format-Photo-Printer-Datasheet.pdf",
                "consumables": ["CX2W 812"],
                "supported_print_sizes": ["8x10", "8x12", "a4"],
                "structured_specs": {
                    "print_speed": {
                        "8x12": "39.2 seconds",
                        "A4": "38.4 seconds",
                        "status": "verified"
                    },
                    "max_width": {
                        "value": 8,
                        "unit": "inches",
                        "status": "inferred",
                        "note": "8 inches inferred from 8x12 media size."
                    },
                    "technology": {
                        "value": "Dye sublimation thermal system with overcoat",
                        "status": "verified"
                    },
                    "liquid_ink": {
                        "uses_liquid_ink": False,
                        "status": "inferred",
                        "note": "Dye-sublimation ribbon and paper media [VERIFIED]; therefore, it does not use conventional liquid-ink cartridges [INFERRED]."
                    },
                    "resolution": {
                        "options": ["300 dpi", "600 dpi"],
                        "status": "verified"
                    },
                    "print_modes": {
                        "options": ["High Speed", "High Quality"],
                        "status": "verified"
                    },
                    "finishes": {
                        "options": ["Glossy", "Matte"],
                        "status": "verified"
                    },
                    "capacity": {
                        "8x12": "110 sheets per roll",
                        "status": "verified"
                    },
                    "weight": {
                        "product_weight": "14 kg (without paper and ribbon)",
                        "package_weight": "16.5 kg (without paper and ribbon)",
                        "status": "verified"
                    },
                    "dimensions": {
                        "product_dimensions": "32.2 x 36.6 x 17 cm",
                        "package_dimensions": "43 x 47 x 27 cm",
                        "status": "verified"
                    },
                    "interface": {
                        "value": "USB 2.0 full speed",
                        "status": "verified"
                    },
                    "media_compatibility": {
                        "CX2W 812": "Verified genuine 8x12 media pack (Model: CX2W 812, SKU: CX2W 812).",
                        "CX2.4x6": "Not compatible with CX-02W. CX2.4x6 is for the 6-inch CX-02, whereas CX-02W requires 8-inch wide media."
                    }
                }
            },
            "epson-sc-f100": {
                "sku": "C11CJ80301",
                "entity_type": "printer",
                "canonical_id": "epson-sc-f100",
                "display_name": "Epson SureColor SC-F100 Dye-Sublimation Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/07/Epson-F100.webp",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-f100-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2023/07/Epson-SureColor-SC-F100-Datasheet.pdf",
                "consumables": ["C13T49N100", "C13T49N200", "C13T49N300", "C13T49N400", "C13S210125"],
                "supported_print_sizes": ["a4"]
            },
            "epson-sc-f500": {
                "sku": "C11CJ17301A0",
                "entity_type": "printer",
                "canonical_id": "epson-sc-f500",
                "display_name": "Epson SureColor SC-F500 Dye-Sublimation Printer",
                "image_url": "https://www.keplertechllc.com/wp-content/uploads/2026/04/epson-SC-F500.jpg.jpeg",
                "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-f500-dye-sublimation-printer/",
                "datasheet_url": "https://www.keplertechllc.com/wp-content/uploads/2026/04/Epson-SureColor-SC-F500-Datasheet.pdf",
                "consumables": ["C13T49N100", "C13T49N200", "C13T49N300", "C13T49N400", "C13S210057"],
                "supported_print_sizes": ["a4", "a3", "a2", "a1", "24-inch"]
            }
        }

        for pid, media_info in VERIFIED_HARDWARE_MEDIA.items():
            if pid in self.products_by_id:
                prod = self.products_by_id[pid]
                if media_info.get("sku"):
                    prod.sku = media_info["sku"]
                if media_info.get("image_url"):
                    prod.image_url = media_info["image_url"]
                if media_info.get("website_url"):
                    prod.source.website_url = media_info["website_url"]
                    prod.product_url = media_info["website_url"]
                if media_info.get("datasheet_url"):
                    prod.datasheet_url = media_info["datasheet_url"]
                if media_info.get("canonical_id"):
                    prod.canonical_id = media_info["canonical_id"]
                if media_info.get("display_name"):
                    prod.display_name = media_info["display_name"]
                if media_info.get("entity_type"):
                    prod.entity_type = media_info["entity_type"]
                if media_info.get("structured_specs"):
                    prod.structured_specs = media_info["structured_specs"]
                if media_info.get("consumables"):
                    existing_c = prod.consumables or []
                    prod.consumables = list(dict.fromkeys(media_info["consumables"] + existing_c))
                if media_info.get("supported_print_sizes"):
                    prod.supported_print_sizes = list(media_info["supported_print_sizes"])
                    if prod.verified:
                        prod.verified.supported_print_sizes = list(media_info["supported_print_sizes"])
            else:
                brand_val = "Citizen" if "citizen" in pid else "Epson"
                cat_val = "photo_booth" if "citizen" in pid else ("promotional_dye_sub" if ("f100" in pid or "f500" in pid) else ("scanner" if "ds-" in pid else "technical_cad"))
                s_specs = media_info.get("structured_specs", {})
                w_val = s_specs.get("max_width", {}).get("value")
                w_mm_val = int(w_val * 25.4) if (w_val and s_specs.get("max_width", {}).get("unit") == "inches") else None
                w_lbl_val = f"{w_val} inches" if w_val else None
                if "cx-02w" in pid:
                    w_mm_val = 203
                    w_lbl_val = "8x10, 8x12 inches"
                elif "cx-02" in pid:
                    w_mm_val = 152
                    w_lbl_val = "4x6, 5x7, 6x8, 6x9 inches"
                elif "cy-02" in pid:
                    w_mm_val = 152
                    w_lbl_val = "4x6, 5x7, 6x8 inches"
                elif "cz-01" in pid:
                    w_mm_val = 114
                    w_lbl_val = "4x6, 4.5x8 inches"

                # Detect MFP / multifunction products that have an integrated scanner
                disp_name_l = (media_info.get("display_name") or pid).lower()
                if "mfp" in disp_name_l or "multifunction" in disp_name_l:
                    scanner_val = True
                elif pid in ("epson-t3100", "epson-t5100", "epson-t5700d") or "citizen" in pid:
                    scanner_val = False
                else:
                    scanner_val = None

                v_specs = VerifiedSpecs(
                    max_width_mm=w_mm_val,
                    max_width_label=w_lbl_val,
                    has_scanner=scanner_val,
                    ink_technology="Dye-Sublimation Thermal System with Overcoat" if "citizen" in pid else None,
                    applications=["Photo Booth", "Event Photography", "Studio"] if "citizen" in pid else [],
                    supported_print_sizes=list(media_info.get("supported_print_sizes", [])),
                )

                new_prod = NormalizedProduct(
                    id=pid,
                    canonical_id=media_info.get("canonical_id") or pid,
                    display_name=media_info.get("display_name") or pid,
                    entity_type=media_info.get("entity_type", "printer"),
                    product_url=media_info.get("website_url"),
                    datasheet_url=media_info.get("datasheet_url"),
                    structured_specs=s_specs,
                    brand=brand_val,
                    model=media_info.get("display_name") or pid,
                    name=media_info.get("display_name") or pid,
                    category=cat_val,
                    sku=media_info.get("sku", pid.upper()),
                    verified=v_specs,
                    source=ProductSource(website_url=media_info.get("website_url")),
                    image_url=media_info.get("image_url"),
                    consumables=media_info.get("consumables", []),
                    supported_print_sizes=list(media_info.get("supported_print_sizes", [])),
                )
                self.products_by_id[pid] = new_prod

        # 2b. Populate verified prices for all products
        from catalog.price_resolver import price_resolver
        for pid, prod in self.products_by_id.items():
            price_info = price_resolver.get_price_info(identifier=pid, prod={"name": prod.name, "sku": prod.sku, "id": prod.id})
            if price_info.get("price") is not None:
                prod.price = price_info["price"]

        # 2c. Populate verified full descriptions and specs from verified_descriptions.json
        desc_path = Path(__file__).parent.parent / "data" / "verified_descriptions.json"
        if desc_path.exists():
            try:
                import re
                with open(desc_path, "r", encoding="utf-8") as f:
                    descriptions_data = json.load(f)
                    for d_key, d_info in descriptions_data.items():
                        d_key_norm = re.sub(r"[\s\-_/]+", "", d_key.lower())
                        matched = False
                        for pid, prod in self.products_by_id.items():
                            p_id_norm = re.sub(r"[\s\-_/]+", "", pid.lower())
                            p_name_norm = re.sub(r"[\s\-_/]+", "", prod.name.lower())
                            if p_id_norm == d_key_norm or d_key_norm in p_id_norm or d_key_norm in p_name_norm:
                                matched = True
                                if d_info.get("full_description"):
                                    prod.full_description = d_info["full_description"]
                                    if not prod.description or len(prod.description) < 150:
                                        prod.description = d_info.get("short_description") or d_info["full_description"][:300]
                                if d_info.get("feature_headings"):
                                    prod.feature_headings = d_info["feature_headings"]
                                if d_info.get("specifications_table"):
                                    prod.specifications_table = d_info["specifications_table"]
                                if d_info.get("image_url") and not prod.image_url:
                                    prod.image_url = d_info["image_url"]

                        if not matched and d_info.get("full_description"):
                            # Index as canonical product
                            brand_val = "Citizen" if "citizen" in d_key else "Epson"
                            cat_val = "photo_booth" if "citizen" in d_key else ("promotional_dye_sub" if ("f100" in d_key or "f500" in d_key) else ("scanner" if "ds-" in d_key or "12000xl" in d_key else "technical_cad"))
                            media_entry = VERIFIED_HARDWARE_MEDIA.get(d_key, {})
                            img_val = media_entry.get("image_url") or d_info.get("image_url")
                            sku_val = media_entry.get("sku") or d_key.upper()
                            w_lbl = None
                            w_mm = None
                            if "cx-02w" in d_key:
                                w_lbl = "8x10, 8x12 inches"
                                w_mm = 203
                            elif "cx-02" in d_key:
                                w_lbl = "4x6, 5x7, 6x8, 6x9 inches"
                                w_mm = 152
                            elif "cy-02" in d_key:
                                w_lbl = "4x6, 5x7, 6x8 inches"
                                w_mm = 152
                            elif "cz-01" in d_key:
                                w_lbl = "4x6, 4.5x8 inches"
                                w_mm = 114

                            new_prod = NormalizedProduct(
                                id=d_key,
                                canonical_id=media_entry.get("canonical_id") or d_key,
                                display_name=media_entry.get("display_name") or d_info.get("title", d_key),
                                entity_type=media_entry.get("entity_type", "printer"),
                                product_url=media_entry.get("website_url") or d_info.get("url"),
                                datasheet_url=media_entry.get("datasheet_url"),
                                structured_specs=media_entry.get("structured_specs", {}),
                                brand=brand_val,
                                model=d_info.get("title", d_key),
                                name=d_info.get("title", d_key),
                                category=cat_val,
                                sku=sku_val,
                                verified=VerifiedSpecs(
                                    ink_technology="Dye-Sublimation Thermal Transfer" if "citizen" in d_key else None,
                                    applications=["Photo Booth", "Event Photography", "Studio"] if "citizen" in d_key else [],
                                    max_width_label=w_lbl,
                                    max_width_mm=w_mm,
                                    supported_print_sizes=list(media_entry.get("supported_print_sizes", [])),
                                ),
                                source=ProductSource(website_url=media_entry.get("website_url") or d_info.get("url")),
                                full_description=d_info.get("full_description"),
                                description=d_info.get("short_description") or d_info.get("full_description", "")[:300],
                                feature_headings=d_info.get("feature_headings", []),
                                specifications_table=d_info.get("specifications_table", {}),
                                image_url=img_val,
                                supported_print_sizes=list(media_entry.get("supported_print_sizes", [])),
                            )
                            price_info = price_resolver.get_price_info(identifier=d_key, prod={"name": new_prod.name})
                            if price_info.get("price") is not None:
                                new_prod.price = price_info["price"]
                            self.products_by_id[d_key] = new_prod
            except Exception as e:
                logger.error(f"Error loading verified descriptions from {desc_path}: {e}")


        # 3. Index standalone scanners from products.json if not already in corpus
        if self.products_path.exists():
            try:
                with open(self.products_path, "r", encoding="utf-8") as f:
                    products_data = json.load(f)
                    for item in products_data:
                        cat_item = item.get("category", "")
                        name = item.get("name", "")
                        sku = str(item.get("sku") or item.get("_id") or "")
                        if cat_item == "Scanner" or ("scanner" in name.lower() and "ink" not in cat_item.lower() and "ribbon" not in name.lower()):
                            p_id = f"epson-{sku.lower()}" if sku else f"scanner-{len(self.products_by_id)}"
                            if p_id not in self.products_by_id and not any(p.name == name for p in self.products_by_id.values()):
                                specs = VerifiedSpecs(
                                    has_scanner=True,
                                    applications=["Document Scanning", "Archiving", "Business Invoices"],
                                    media_handling="ADF / Flatbed Document Scanner",
                                )
                                norm_scanner = NormalizedProduct(
                                    id=p_id,
                                    canonical_id=p_id,
                                    display_name=name,
                                    entity_type="scanner",
                                    product_url=item.get("website_url") or item.get("web_url"),
                                    brand="Epson",
                                    model=name.split()[0] if name else "Epson Scanner",
                                    name=name,
                                    category="scanner",
                                    # SKU: prefer the item's own sku field; fall back to the part-number
                                    # that forms the product ID (already the canonical SKU for these items)
                                    sku=sku or p_id.upper(),
                                    verified=specs,
                                    source=ProductSource(website_url=item.get("website_url") or item.get("web_url")),
                                    image_url=item.get("image_url") or item.get("image"),
                                    description=item.get("description") or "Official high-precision document scanner from Kepler Tech LLC.",
                                    consumables=item.get("consumables", []),
                                )
                                self.products_by_id[norm_scanner.id] = norm_scanner
            except Exception as e:
                logger.error(f"Error indexing scanners from {self.products_path}: {e}")

        # Index by category
        self.products_by_category = {}
        for p in self.products_by_id.values():
            self.products_by_category.setdefault(p.category, []).append(p)
        logger.info(f"Loaded {len(self.products_by_id)} normalized products across {len(self.products_by_category)} categories.")


    def _normalize_corpus_item(self, item: Dict) -> Optional[NormalizedProduct]:
        p_id = item.get("id")
        if not p_id:
            return None

        # Determine category
        cat_raw = item.get("category", "").lower()
        if "f100" in p_id or "f500" in p_id:
            category = "promotional_dye_sub"
        elif "booth" in cat_raw or "citizen" in p_id:
            category = "photo_booth"
        elif "cad" in cat_raw or "plotter" in cat_raw:
            category = "technical_cad"
        elif "photo" in cat_raw or "fine_art" in cat_raw or "art" in cat_raw:
            category = "photo_fine_art"
        elif "office" in cat_raw or "enterprise" in cat_raw:
            category = "office_enterprise"
        elif "scanner" in cat_raw:
            category = "scanner"
        elif "paper" in cat_raw or "media" in cat_raw:
            category = "media_paper"
        elif "software" in cat_raw or "server" in cat_raw:
            category = "software"
        elif "ink" in cat_raw or "cartridge" in cat_raw or "consumable" in cat_raw:
            category = "consumable"
        else:
            category = "technical_cad"


        # Width calculation
        width_str = item.get("width", "")
        full_text = (item.get("name", "") + " " + width_str + " " + item.get("intended_usage", "")).lower()
        max_width_mm = None
        max_width_label = width_str if width_str else None
        if "44" in width_str:
            max_width_mm = 1118
            max_width_label = "44-inch Production"
        elif "36" in width_str or "a0" in width_str.lower():
            max_width_mm = 914
            max_width_label = "36-inch (A0)"
        elif "24" in width_str or "a1" in width_str.lower():
            max_width_mm = 610
            max_width_label = "24-inch (A1)"
        elif "17" in width_str or "a2" in width_str.lower():
            max_width_mm = 432
            max_width_label = "17-inch (A2+)"
        elif "13" in width_str or "a3" in width_str.lower():
            max_width_mm = 329
            max_width_label = "13-inch (A3+)"
        elif "a4" in full_text or "8.3" in width_str:
            max_width_mm = 210
            max_width_label = "A4"
        elif "cx-02w" in p_id or "cx02w" in p_id:
            max_width_mm = 203
            max_width_label = "8x10, 8x12 inches"
        elif "cx-02" in p_id or "cx02" in p_id or "cy-02" in p_id:
            max_width_mm = 152
            max_width_label = "4x6, 5x7, 6x8 inches"
        elif "cz-01" in p_id or "cz01" in p_id:
            max_width_mm = 114
            max_width_label = "4x6, 4.5x8 inches"

        # Scanner: strict 3-valued logic (True / False / None)
        name_desc = (
            str(item.get("name", "")) + " " +
            str(item.get("title", "")) + " " +
            str(item.get("short_description", "")) + " " +
            str(item.get("full_description", "")) + " " +
            str(item.get("media_handling", "")) + " " +
            str(item.get("comparison_highlights", ""))
        ).lower()
        if p_id in ("epson-t5100m", "epson-t5400m", "epson-surecolor-sc-t5100m", "epson-sc-t5400m", "epson-am-c4000", "epson-am-c550") or "integrated scanner" in name_desc or "scanner included" in name_desc or "multifunction" in name_desc or "mfp" in name_desc:
            has_scanner = True
        elif "print only" in name_desc or "standalone plotter" in name_desc or "desktop plotter" in name_desc or "dual-roll production plotter" in name_desc or p_id in ("epson-t3100", "epson-t5100", "epson-t5700d", "epson-p700", "epson-p900", "epson-p7500", "epson-p9500", "epson-p5300", "citizen-cx-02", "citizen-cx-02w", "citizen-cy-02", "citizen-cz-01", "epson-f100", "epson-f500"):
            has_scanner = False
        else:
            has_scanner = None

        # Connectivity
        conn_raw = item.get("connectivity", "")
        connectivity = []
        if "wi-fi" in conn_raw.lower() or "wifi" in conn_raw.lower():
            connectivity.append("Wi-Fi")
        if "ethernet" in conn_raw.lower() or "gigabit" in conn_raw.lower() or "network" in conn_raw.lower():
            connectivity.append("Ethernet")
        if "usb" in conn_raw.lower():
            connectivity.append("USB")

        # Applications
        apps = []
        intended = item.get("intended_usage", "").lower()
        if "cad" in intended or "architecture" in intended or "drawings" in intended or "blueprint" in intended:
            apps.extend(["CAD", "Architecture", "Engineering", "Blueprints"])
        if "gis" in intended or "map" in intended:
            apps.append("GIS & Maps")
        if "photo" in intended or "gallery" in intended or "fine art" in intended:
            apps.extend(["Photography", "Fine Art", "Gallery Proofing"])
        if "event" in intended or "booth" in intended:
            apps.extend(["Photo Booth", "Event Printing"])

        specs = VerifiedSpecs(
            max_width_mm=max_width_mm,
            max_width_label=max_width_label,
            has_scanner=has_scanner,
            resolution=item.get("max_resolution"),
            speed=item.get("speed") or item.get("print_speed"),
            ink_technology=item.get("ink_technology"),
            connectivity=connectivity,
            applications=apps,
            cartridge_capacities=item.get("capacity") or item.get("cartridge_capacities"),
            media_handling=item.get("media_handling"),
            footprint=item.get("footprint"),
            weight=item.get("weight"),
        )

        ent_type = "scanner" if category == "scanner" else ("consumable" if category == "consumable" else ("media" if category == "media_paper" else ("software" if category == "software" else "printer")))
        src_u = item.get("source_url") or item.get("website_url") or item.get("url")

        return NormalizedProduct(
            id=p_id,
            canonical_id=p_id,
            display_name=item.get("name", p_id),
            entity_type=ent_type,
            product_url=src_u,
            brand=item.get("brand", "Epson"),
            model=item.get("name", "").split()[0] if item.get("name") else p_id,
            name=item.get("name", p_id),
            category=category,
            verified=specs,
            source=ProductSource(website_url=src_u),
            comparison_highlights=item.get("comparison_highlights"),
            description=item.get("intended_usage"),
        )

    def get_by_id(self, product_id: str) -> Optional[NormalizedProduct]:
        if not product_id:
            return None
        if product_id in self.products_by_id:
            return self.products_by_id[product_id]
        from catalog.product_resolver import resolve_canonical_id
        canon = resolve_canonical_id(product_id)
        if canon and canon in self.products_by_id:
            return self.products_by_id[canon]
        p_id_lower = product_id.lower().strip()
        for p in self.products_by_id.values():
            if p.id.lower() == p_id_lower or (p.sku and p.sku.lower() == p_id_lower) or (p.canonical_id and p.canonical_id.lower() == p_id_lower):
                return p
        return None

    def get_all(self) -> List[NormalizedProduct]:
        return list(self.products_by_id.values())

    def get_by_category(self, category: str) -> List[NormalizedProduct]:
        return self.products_by_category.get(category, [])


# Singleton catalog repository
catalog_repository = CatalogRepository()
