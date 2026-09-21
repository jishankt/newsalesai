"""
Script to synchronize and correct all product consumables, media & paper supplies,
and website URLs across catalogue_products.json and products.json.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOGUE_FILE = DATA_DIR / "catalogue_products.json"
PRODUCTS_FILE = DATA_DIR / "products.json"
SITEMAP_FILE = DATA_DIR / "sitemap_image_map.json"

# Verified Genuine Consumables Mapping for all 43 Catalogue Products
# Includes genuine Inks, Maintenance Boxes, and Compatible Paper / Media Rolls
CATALOGUE_CONSUMABLES_MAP = {
    # ── Business A4 Printers ──
    "epson-wf-c5890-dwf": [
        "C13T11D140", "C13T11D240", "C13T11D340", "C13T11D440",  # T11D XL Black, Cyan, Magenta, Yellow
        "C13T11E140", "C13T11E240", "C13T11E340", "C13T11E440",  # T11E XXL Black, Cyan, Magenta, Yellow
        "C13S210125",                                             # Maintenance Box
    ],
    "epson-em-c800": [
        "C13T11N140", "C13T11N240", "C13T11N340", "C13T11N440",  # T11N XL Black, Cyan, Magenta, Yellow
        "C13T11P140", "C13T11P240", "C13T11P340", "C13T11P440",  # T11P XXL Black, Cyan, Magenta, Yellow
        "C13S210125",                                             # Maintenance Box
    ],
    "epson-am-c400": [
        "C13T08Q140", "C13T08Q240", "C13T08Q340", "C13T08Q440",  # T08Q Black, Cyan, Magenta, Yellow
        "C12C937201",                                             # Maintenance Box
    ],
    "epson-am-c550": [
        "C13T08Q140", "C13T08Q240", "C13T08Q340", "C13T08Q440",  # T08Q Black, Cyan, Magenta, Yellow
        "C12C937201",                                             # Maintenance Box
    ],

    # ── Business A3 Printers ──
    "epson-wf-c878r-dwf": [
        "C13T05A100", "C13T05A200", "C13T05A300", "C13T05A400",  # T05A XL Inks
        "C13T05B100", "C13T05B200", "C13T05B300", "C13T05B400",  # T05B XXL Inks
        "C13T671400",                                             # Maintenance Box
    ],
    "epson-wf-c879r-dwf": [
        "C13T05A100", "C13T05A200", "C13T05A300", "C13T05A400",
        "C13T05B100", "C13T05B200", "C13T05B300", "C13T05B400",
        "C13T671400",
    ],
    "epson-am-c4000": [
        "C13T08H100", "C13T08H200", "C13T08H300", "C13T08H400",  # T08H Black, Cyan, Magenta, Yellow
        "C12C937181",                                             # Maintenance Box
    ],
    "epson-am-c5000": [
        "C13T08G100", "C13T08G200", "C13T08G300", "C13T08G400",  # T08G Black, Cyan, Magenta, Yellow
        "C12C937181",                                             # Maintenance Box
    ],
    "epson-am-c6000": [
        "C13T08G100", "C13T08G200", "C13T08G300", "C13T08G400",  # T08G Black, Cyan, Magenta, Yellow
        "C12C937181",                                             # Maintenance Box
    ],
    "epson-wf-c20600": [
        "C13T02Y100", "C13T02Y200", "C13T02Y300", "C13T02Y400",  # T02Y Black, Cyan, Magenta, Yellow
        "C13T671300",                                             # Maintenance Box
    ],
    "epson-wf-c20750": [
        "C13T02Y100", "C13T02Y200", "C13T02Y300", "C13T02Y400",  # T02Y Black, Cyan, Magenta, Yellow
        "C13T671300",                                             # Maintenance Box
    ],
    "epson-wf-c21000": [
        "C13T02Y100", "C13T02Y200", "C13T02Y300", "C13T02Y400",  # T02Y Black, Cyan, Magenta, Yellow
        "C13T671300",                                             # Maintenance Box
    ],
    "epson-wf-c21000-d4tw": [
        "C13T02Y100", "C13T02Y200", "C13T02Y300", "C13T02Y400",  # T02Y Black, Cyan, Magenta, Yellow
        "C13T671300",                                             # Maintenance Box
    ],
    "epson-wf-m21000": [
        "C13T02Y100",                                             # T02Y Monochrome Black
        "C13T671300",                                             # Maintenance Box
    ],

    # ── Technical Large Format (T-Series) ──
    "epson-sc-t3100": [
        "C13S210057",                                             # Maintenance Box
        "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440",  # T40C Standard (26ml/50ml)
        "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440",  # T40D High Capacity (50ml/80ml)
        "C13S041385", "C13S041595",                               # 24" Doubleweight Matte & Enhanced Matte Roll
    ],
    "epson-sc-t3100m": [
        "C13S210057",
        "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440",
        "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440",
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t3400": [
        "C13T699700",                                             # Maintenance Box
        "C13T41R240", "C13T41R340", "C13T41R440", "C13T41R540",  # T41R 110ml
        "C13T41F240", "C13T41F340", "C13T41F440", "C13T41F540",  # T41F 350ml
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t3405": [
        "C13T699700",
        "C13T41R240", "C13T41R340", "C13T41R440", "C13T41R540",
        "C13T41F240", "C13T41F340", "C13T41F440", "C13T41F540",
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t3700e": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t3700d": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t3700de": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041385", "C13S041595",
    ],
    "epson-sc-t5100": [
        "C13S210057",
        "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440",
        "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440",
        "C13S041385", "C13S041387", "C13S041595", "C13S041597",   # 24" and 36"/44" Rolls
    ],
    "epson-sc-t5100m": [
        "C13S210057",
        "C13T40C140", "C13T40C240", "C13T40C340", "C13T40C440",
        "C13T40D140", "C13T40D240", "C13T40D340", "C13T40D440",
        "C13S041385", "C13S041387", "C13S041595",
    ],
    "epson-sc-t5400m": [
        "C13T699700",
        "C13T41R240", "C13T41R340", "C13T41R440", "C13T41R540",
        "C13T41F240", "C13T41F340", "C13T41F440", "C13T41F540",
        "C13S041385", "C13S041387", "C13S041597",
    ],
    "epson-sc-t5405": [
        "C13T699700",
        "C13T41R240", "C13T41R340", "C13T41R440", "C13T41R540",
        "C13T41F240", "C13T41F340", "C13T41F440", "C13T41F540",
        "C13S041385", "C13S041387", "C13S041597",
    ],
    "epson-sc-t5700d": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041387", "C13S041597",
    ],
    "epson-sc-t5700dm": [
        "C13S210115", "C13S210116",                               # Maintenance Box & Borderless Pad
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",  # T50M 350ml
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",  # T50U 700ml
        "C13S041387", "C13S041597",
    ],
    "epson-sc-t7700d": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041387", "C13S041597", "C13S042138",
    ],
    "epson-sc-t7700dl": [
        "C13S210115", "C13S210116",
        "C13T53A100", "C13T53A200", "C13T53A300", "C13T53A400", "C13T53A800", "C13T53A900",  # 1.6L RIPS Inks
        "C13S041387", "C13S041597", "C13S042138",
    ],
    "epson-sc-t7700dm": [
        "C13S210115", "C13S210116",
        "C13T50M100", "C13T50M200", "C13T50M300", "C13T50M400", "C13T50M800", "C13T50MF00",
        "C13T50U100", "C13T50U200", "C13T50U300", "C13T50U400", "C13T50U80N", "C13T50UF00",
        "C13S041387", "C13S041597", "C13S042138",
    ],

    # ── Photography Large Format (P-Series) ──
    "epson-sc-p700": [
        "C12C935711",                                             # Maintenance Box
        "C13T46S100", "C13T46S200", "C13T46S300", "C13T46S400", "C13T46S500",  # T46S PRO10 Inks
        "C13T46S600", "C13T46S700", "C13T46S800", "C13T46S900", "C13T46SD00",
        "C13S041785", "C13S042330", "C13S042300",                 # A3+ Luster, Hot/Cold Press Fine Art
    ],
    "epson-sc-p900": [
        "C12C935711",
        "C13T47A100", "C13T47A200", "C13T47A300", "C13T47A400", "C13T47A500",  # T47A PRO10 Inks (50ml)
        "C13T47A600", "C13T47A700", "C13T47A800", "C13T47A900", "C13T47AD00",
        "C12C935901",                                             # Roll Media Adapter
        "C13S042123", "C13S041725", "C13S041846",                 # A2 Luster, 17" Matte Roll, 17" Canvas Satin
    ],
    "epson-sc-p900-roll": [
        "C12C935711",
        "C13T47A100", "C13T47A200", "C13T47A300", "C13T47A400", "C13T47A500",
        "C13T47A600", "C13T47A700", "C13T47A800", "C13T47A900", "C13T47AD00",
        "C12C935901",
        "C13S042123", "C13S041725", "C13S041846",
    ],
    "epson-sc-p5300": [
        "C13S210057",
        "C13T47A100", "C13T47A200", "C13T47A300", "C13T47A400", "C13T47A500",
        "C13T47A600", "C13T47A700", "C13T47A800", "C13T47A900", "C13T47AD00",
        "C13S041725", "C13S041846",
    ],
    "epson-sc-p6500e": [
        "C13S210115", "C13S210116",
        "C13T48M100", "C13T48M200", "C13T48M300", "C13T48M400", "C13T48M800", "C13T48ME00",  # T48M PRO6 350ml
        "C13S041595", "C13S041847",
    ],
    "epson-sc-p6500d": [
        "C13S210115", "C13S210116",
        "C13T48M100", "C13T48M200", "C13T48M300", "C13T48M400", "C13T48M800", "C13T48ME00",
        "C13S041595", "C13S041847",
    ],
    "epson-sc-p6500de": [
        "C13S210115", "C13S210116",
        "C13T48M100", "C13T48M200", "C13T48M300", "C13T48M400", "C13T48M800", "C13T48ME00",
        "C13S041595", "C13S041847",
    ],
    "epson-sc-p7500": [
        "C13T699700",                                             # Maintenance Box
        "C13T44J240", "C13T44J740", "C13T44JB40", "C13T44J940", "C13T44J840",  # T44J 350ml 12-color
        "C13T44JA40", "C13T44JD40", "C13T44J640", "C13T44J440",
        "C13T44Q240", "C13T44Q740", "C13T44QB40", "C13T44QA40", "C13T44QD40", "C13T44Q440",  # T44Q 700ml
        "C13S041595", "C13S041847",
    ],
    "epson-sc-p7500-spectro": [
        "C13T699700",
        "C13T44J240", "C13T44J740", "C13T44JB40", "C13T44J940", "C13T44J840",
        "C13T44JA40", "C13T44JD40", "C13T44J640", "C13T44J440",
        "C13T44Q240", "C13T44Q740", "C13T44QB40", "C13T44QA40", "C13T44QD40", "C13T44Q440",
        "C13S041595", "C13S041847",
    ],
    "epson-sc-p8500d": [
        "C13S210115", "C13S210116",
        "C13T48M100", "C13T48M200", "C13T48M300", "C13T48M400", "C13T48M800", "C13T48ME00",
        "C13S041597", "C13S041848",
    ],
    "epson-sc-p8500dm": [
        "C13S210115", "C13S210116",
        "C13T48M100", "C13T48M200", "C13T48M300", "C13T48M400", "C13T48M800", "C13T48ME00",
        "C13S041597", "C13S041848",
    ],
    "epson-sc-p9500": [
        "C13T699700",
        "C13T44J240", "C13T44J740", "C13T44JB40", "C13T44J940", "C13T44J840",
        "C13T44JA40", "C13T44JD40", "C13T44J640", "C13T44J440",
        "C13T44Q240", "C13T44Q740", "C13T44QB40", "C13T44QA40", "C13T44QD40", "C13T44Q440",
        "C13S041597", "C13S041848", "C13S045259",
    ],
    "epson-sc-p9500-spectro": [
        "C13T699700",
        "C13T44J240", "C13T44J740", "C13T44JB40", "C13T44J940", "C13T44J840",
        "C13T44JA40", "C13T44JD40", "C13T44J640", "C13T44J440",
        "C13T44Q240", "C13T44Q740", "C13T44QB40", "C13T44QA40", "C13T44QD40", "C13T44Q440",
        "C13S041597", "C13S041848", "C13S045259",
    ],
    "epson-sc-p20500": [
        "C13S210115",
        "C13T56F100", "C13T56F500",                               # PRO12 1.6L IIPS Inks
        "C13S042138", "C13S042135", "C13S045065",                 # 64" Matte, Enhanced Matte, Canvas Satin
    ],

    # ── Citizen Photo Printers ──
    "citizen-cx-02": [
        "CX2.4x6", "CX2.6X8", "Citizen CX-02 Bag", "Citizen Pen"
    ],
    "citizen-cy-02": [
        "CY-MS46", "CY-MS68", "CY02Bag", "Citizen Pen"
    ],
    "citizen-cx-02w": [
        "CX2W 812", "Citizen Pen"
    ],
    "citizen-cz-01": [
        "CZ-MS46", "CZ-MS458", "CZ01 Carry Bag", "Citizen Pen"
    ],

    # ── Dye Sublimation (F-Series) ──
    "epson-sc-f100": [
        "C13T49N100", "C13T49N200", "C13T49N300", "C13T49N400",  # DS Inks 140ml
        "C13S210125",                                             # Maintenance Box
    ],
    "epson-sc-f500": [
        "C13T49N100", "C13T49N200", "C13T49N300", "C13T49N400",  # DS Inks 140ml
        "C13S210057",                                             # Maintenance Box
    ],
}


def sync_catalogue_products():
    print("--- 1. Synchronizing catalogue_products.json ---")
    with open(CATALOGUE_FILE, "r", encoding="utf-8") as f:
        catalogue = json.load(f)

    for item in catalogue:
        cid = item["id"]
        # Populate verified consumables
        if cid in CATALOGUE_CONSUMABLES_MAP:
            item["consumables"] = CATALOGUE_CONSUMABLES_MAP[cid]
        else:
            print(f"WARNING: No consumables mapped for {cid}")

        # Correct specific URLs and images
        if cid in ("epson-sc-p9500", "epson-sc-p9500-spectro"):
            item["product_url"] = "https://www.keplertechllc.com/product/epson-surecolor-p9500-large-format-printer/"
            if cid == "epson-sc-p9500-spectro":
                item["image_url"] = "https://www.keplertechllc.com/wp-content/uploads/2016/03/Epson-P9500-Printer-4.webp"
        elif cid == "epson-sc-p7500-spectro":
            item["image_url"] = "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P7500-Printer.webp"
        elif cid in ("epson-sc-p900", "epson-sc-p900-roll"):
            item["product_url"] = "https://www.keplertechllc.com/product/epson-surecolor-p900-17-inch-photo-printer/"
        elif cid == "epson-wf-c20600":
            item["product_url"] = "https://www.keplertechllc.com/product/epson-workforce-enterprise-wf-c20600-printer/"

    with open(CATALOGUE_FILE, "w", encoding="utf-8") as f:
        json.dump(catalogue, f, indent=2, ensure_ascii=False)
    print(f"Successfully updated {len(catalogue)} catalogue products in {CATALOGUE_FILE}")


def sync_products_json():
    print("--- 2. Synchronizing products.json ---")
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)

    # Corrections dictionary by SKU
    URL_AND_IMG_FIXES = {
        "C11CE20001A0": {  # SC-P20000
            "name": "Epson SureColor SC-P20000 Large Format Printer",
            "website_url": "https://www.keplertechllc.com/product/epson-sc-p20000-large-format-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-sc-p20000-large-format-printer/",
            "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/EPSON-P20000-PEINTER-1.webp",
            "image": "https://www.keplertechllc.com/wp-content/uploads/2023/03/EPSON-P20000-PEINTER-1.webp",
            "consumables": [
                "C13T619300",  # Maintenance Box
                "C13T56F100", "C13T56F500",  # PRO Inks
                "C13S042138", "C13S042135", "C13S045065"  # 64" Media Rolls
            ]
        },
        "C11CE41301A0": {  # SC-P6000
            "name": "Epson SureColor SC-P6000 24\" Large-Format Printer STD",
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-p6000-24-large-format-printer-std/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-p6000-24-large-format-printer-std/",
            "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P6000-Printer-1.webp",
            "image": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P6000-Printer-1.webp",
            "consumables": [
                "C13T699700",  # Maintenance Box
                "C13T44J240", "C13T44J740", "C13T44J940", "C13T44J840",  # Inks
                "C13S041595", "C13S041847"  # 24" Media Rolls
            ]
        },
        "C11CF66001A4": {  # SC-P5000 STD
            "name": "Epson SureColor SC-P5000 17\" Large Format Printer STD",
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p5000-standard-large-format-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p5000-standard-large-format-printer/",
            "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P5000-Printer-2.webp",
            "image": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P5000-Printer-2.webp",
            "consumables": [
                "C13T699700",
                "C13T44J240", "C13T44J740",
                "C13S041725", "C13S041846"
            ]
        },
        "C11CF66001A6": {  # SC-P5000 Spectro
            "name": "Epson SureColor SC-P5000 17\" Large Format Printer Spectro",
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p5000-standard-large-format-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-sc-p5000-standard-large-format-printer/",
            "image_url": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P5000-Printer-2.webp",
            "image": "https://www.keplertechllc.com/wp-content/uploads/2023/03/Epson-P5000-Printer-2.webp",
            "consumables": [
                "C13T699700",
                "C13T44J240", "C13T44J740",
                "C13S041725", "C13S041846"
            ]
        },
        "C11CH13301A1": {  # SC-P9500
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-p9500-large-format-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-p9500-large-format-printer/",
        },
        "C11CH86401BY": {  # WF-C20600
            "website_url": "https://www.keplertechllc.com/product/epson-workforce-enterprise-wf-c20600-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-workforce-enterprise-wf-c20600-printer/",
        },
        "C11CH37402DA": {  # SC-P900
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-p900-17-inch-photo-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-p900-17-inch-photo-printer/",
        },
        "C11CH37402DR": {  # SC-P900 Roll
            "website_url": "https://www.keplertechllc.com/product/epson-surecolor-p900-17-inch-photo-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-surecolor-p900-17-inch-photo-printer/",
        },
        "C11CH84301A1": {  # SC-T7700DM
            "website_url": "https://www.keplertechllc.com/product/epson-sc-t7700dm-multi-function-technical-printer/",
            "web_url": "https://www.keplertechllc.com/product/epson-sc-t7700dm-multi-function-technical-printer/",
        },
        # Hardware printers that had empty consumables
        "C11CD66301A0": {  # SC-T3200 Stand
            "consumables": ["C13T699700", "C13T692100", "C13T692200", "C13T692300", "C13T692400", "C13T692500", "C13S041385"]
        },
        "C11CD66301A1": {  # SC-T3200 Without Stand
            "consumables": ["C13T699700", "C13T692100", "C13T692200", "C13T692300", "C13T692400", "C13T692500", "C13S041385"]
        },
        "C11CD67301A2": {  # SC-T5200 MFP HDD
            "consumables": ["C13T699700", "C13T692100", "C13T692200", "C13T692300", "C13T692400", "C13T692500", "C13S041387"]
        },
        "C11CD68301A1": {  # SC-T7200 MFP
            "consumables": ["C13T699700", "C13T692100", "C13T692200", "C13T692300", "C13T692400", "C13T692500", "C13S042138"]
        },
        "C11CF34201": {  # WF-C869R
            "consumables": ["C13T973120", "C13T973220", "C13T973320", "C13T973420", "C13T974120", "C13T974220", "C13T974320", "C13T974420", "C13T671400"]
        }
    }

    updated_count = 0
    for p in products:
        sku = p.get("sku")
        if sku in URL_AND_IMG_FIXES:
            fixes = URL_AND_IMG_FIXES[sku]
            p.update(fixes)
            updated_count += 1

    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"Successfully updated specific product records in {PRODUCTS_FILE}")


if __name__ == "__main__":
    sync_catalogue_products()
    sync_products_json()
