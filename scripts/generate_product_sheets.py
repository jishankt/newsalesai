#!/usr/bin/env python3
"""
Generate Complete Product Details Sheets & Training Datasets.
Creates:
1. data/sheets/master_complete_products.csv
2. data/sheets/hardware_printers.csv
3. data/sheets/scanners.csv
4. data/sheets/medias_and_papers.csv
5. data/sheets/consumables.csv
6. data/sheets/complete_training_corpus.json
7. data/sheets/training_qa_pairs.jsonl
"""

import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "sheets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load base data
with open(DATA_DIR / "catalogue_products.json", "r", encoding="utf-8") as f:
    catalogue_products = json.load(f)

with open(DATA_DIR / "media_products.json", "r", encoding="utf-8") as f:
    media_products = json.load(f)

with open(DATA_DIR / "products.json", "r", encoding="utf-8") as f:
    products_db = json.load(f)

with open(DATA_DIR / "verified_brochures.json", "r", encoding="utf-8") as f:
    verified_brochures = json.load(f)

with open(DATA_DIR / "verified_descriptions.json", "r", encoding="utf-8") as f:
    verified_descriptions = json.load(f)

with open(DATA_DIR / "verified_prices.json", "r", encoding="utf-8") as f:
    verified_prices = json.load(f)

try:
    with open(DATA_DIR / "website_prices_cache.json", "r", encoding="utf-8") as f:
        website_prices = json.load(f)
except Exception:
    website_prices = {}

# Build SKU and ID lookups for fast retrieval
db_sku_map = {}
for p in products_db:
    sku = str(p.get("sku") or p.get("_id") or "").strip().upper()
    if sku:
        db_sku_map[sku] = p

def clean_str(val):
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return ", ".join(str(x) for x in val if x)
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val).strip()

def get_brochure_url(pid, display_name):
    pid_l = (pid or "").lower()
    for k, v in verified_brochures.items():
        if k.lower() in pid_l or pid_l in k.lower():
            return v.get("pdf", "")
        for alias in v.get("aliases", []):
            if alias.lower() in pid_l or alias.lower() in (display_name or "").lower():
                return v.get("pdf", "")
    return ""

def get_price_val(pid, sku=None):
    pid_clean = (pid or "").lower()
    if pid_clean in verified_prices:
        val = verified_prices[pid_clean]
        return val.get("price") or val.get("price_str") or ""
    if sku and str(sku).lower() in verified_prices:
        val = verified_prices[str(sku).lower()]
        return val.get("price") or val.get("price_str") or ""
    if sku and str(sku).lower() in website_prices:
        val = website_prices[str(sku).lower()]
        return val.get("price") or val.get("price_str") or ""
    if pid_clean in website_prices:
        val = website_prices[pid_clean]
        return val.get("price") or val.get("price_str") or ""
    if sku and str(sku).upper() in db_sku_map:
        return db_sku_map[str(sku).upper()].get("price") or ""
    return ""

# ---------------------------------------------------------
# 1. PROCESS HARDWARE PRINTERS & SCANNERS
# ---------------------------------------------------------
hardware_printers = []
hardware_scanners = []

for cp in catalogue_products:
    pid = cp.get("id")
    category = cp.get("main_category")
    is_scanner = category == "scanners"
    
    # Resolve brochure
    brochure_url = get_brochure_url(pid, cp.get("display_name"))
    
    # Resolve verified price
    price_val = get_price_val(pid, cp.get("id"))
    
    # Resolve enriched description
    desc_info = verified_descriptions.get(pid, {})
    full_desc = desc_info.get("full_description") or ""
    short_desc = desc_info.get("short_description") or ""
    
    # Resolve linked consumables details
    consumable_skus = cp.get("consumables", [])
    consumable_details = []
    for csku in consumable_skus:
        csku_up = str(csku).strip().upper()
        item = db_sku_map.get(csku_up)
        if item:
            consumable_details.append({
                "sku": csku_up,
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "price": item.get("price", ""),
                "url": item.get("website_url") or item.get("web_url") or "",
                "image": item.get("image_url") or item.get("image") or ""
            })
        else:
            consumable_details.append({
                "sku": csku_up,
                "name": f"Consumable {csku_up}",
                "category": "Consumable",
                "price": "",
                "url": "",
                "image": ""
            })

    item_row = {
        "id": pid,
        "display_name": cp.get("display_name", ""),
        "model_family": cp.get("model_family", ""),
        "brand": cp.get("brand", ""),
        "main_category": cp.get("main_category", ""),
        "subcategory": cp.get("subcategory", ""),
        "product_line": cp.get("product_line", ""),
        "catalogue": cp.get("catalogue", ""),
        "source_catalogue": cp.get("source_catalogue", ""),
        "product_url": cp.get("product_url", ""),
        "image_url": cp.get("image_url", ""),
        "brochure_url": brochure_url,
        "price_aed": price_val,
        "paper_size": cp.get("paper_size", ""),
        "max_width_inches": cp.get("max_width_inches", ""),
        "colour_mode": cp.get("colour_mode", ""),
        "functions": clean_str(cp.get("functions", [])),
        "applications": clean_str(cp.get("applications", [])),
        "supported_print_sizes": clean_str(cp.get("supported_print_sizes", [])),
        "print_speed": cp.get("print_speed", ""),
        "scan_speed": cp.get("scan_speed", ""),
        "dpi": cp.get("dpi", ""),
        "optical_resolution": cp.get("optical_resolution", ""),
        "optical_density": cp.get("optical_density", ""),
        "scanning_range": cp.get("scanning_range", ""),
        "scanner_type": cp.get("scanner_type", ""),
        "scanner_integrated": cp.get("scanner_integrated", ""),
        "dual_roll": cp.get("dual_roll", ""),
        "spectro": cp.get("spectro", ""),
        "memory": cp.get("memory", ""),
        "total_colours": cp.get("total_colours", ""),
        "colour_specification": cp.get("colour_specification", ""),
        "cartridge_sizes": cp.get("cartridge_sizes", ""),
        "consumable_volume": cp.get("consumable_volume", ""),
        "yield_capacity": cp.get("yield_capacity", ""),
        "pattern_and_finishing": cp.get("pattern_and_finishing", ""),
        "weight": cp.get("weight", ""),
        "dimensions": cp.get("dimensions", ""),
        "warranty": cp.get("warranty", ""),
        "features": clean_str(cp.get("features", [])),
        "recommended_monthly_min": cp.get("recommended_monthly_min", ""),
        "recommended_monthly_max": cp.get("recommended_monthly_max", ""),
        "short_description": short_desc,
        "full_description": full_desc,
        "consumables_count": len(consumable_skus),
        "consumables_skus": ", ".join(consumable_skus),
        "consumables_detailed": json.dumps(consumable_details, ensure_ascii=False)
    }

    if is_scanner:
        hardware_scanners.append(item_row)
    else:
        hardware_printers.append(item_row)

# ---------------------------------------------------------
# 2. PROCESS MEDIA & PAPER PRODUCTS
# ---------------------------------------------------------
processed_media = []
for mp in media_products:
    sku = mp.get("sku", "").strip()
    name = mp.get("name", "").strip()
    price_val = get_price_val(sku, sku)
    
    media_row = {
        "sku": sku,
        "name": name,
        "family_code": mp.get("family_code", ""),
        "brand": mp.get("brand", ""),
        "category": mp.get("category", ""),
        "surface_finish": mp.get("surface_finish", ""),
        "weight_gsm": mp.get("weight_gsm", ""),
        "format_type": mp.get("format_type", ""),
        "size_label": mp.get("size_label", ""),
        "width_inches": mp.get("width_inches", ""),
        "ink_compatibility": clean_str(mp.get("ink_compatibility", [])),
        "compatible_printers": clean_str(mp.get("compatible_printers", [])),
        "product_url": mp.get("url", ""),
        "image_url": mp.get("image_url", ""),
        "price_aed": price_val
    }
    processed_media.append(media_row)

# ---------------------------------------------------------
# 3. PROCESS CONSUMABLES
# ---------------------------------------------------------
# Collect all consumable products from products_db
# Categories: Ink Cartridge, Maintenance Box, Ribbon, Accessory
processed_consumables = []
consumable_categories = {"Ink Cartridge", "Maintenance Box", "Accessory"}

# Map of which printers use each consumable SKU
consumable_to_printers = {}
for cp in catalogue_products:
    pid = cp.get("id")
    pname = cp.get("display_name")
    for csku in cp.get("consumables", []):
        csku_up = str(csku).strip().upper()
        consumable_to_printers.setdefault(csku_up, []).append(f"{pname} ({pid})")

seen_consumable_skus = set()
for p in products_db:
    cat = p.get("category") or ""
    sku = str(p.get("sku") or p.get("_id") or "").strip().upper()
    name = p.get("name", "").strip()
    name_l = name.lower()
    
    is_consumable = (
        cat in consumable_categories or
        any(k in name_l for k in ["cartridge", "maintenance box", "ink tank", "ribbon", "ink bottle", "roller kit", "carrier sheet", "cleaning sheet"])
    ) and not any(hw in cat.lower() for hw in ["printer", "scanner"]) and not ("printer" in name_l and "ink" not in name_l and "cartridge" not in name_l)
    
    if is_consumable and sku and sku not in seen_consumable_skus:
        seen_consumable_skus.add(sku)
        
        # Color extraction
        color = ""
        for c in ["Black", "Cyan", "Magenta", "Yellow", "Light Cyan", "Light Magenta", "Photo Black", "Matte Black", "Gray", "Light Gray", "Violet", "Orange", "Green"]:
            if re.search(r'\b' + re.escape(c) + r'\b', name, re.IGNORECASE):
                color = c
                break
        
        printers_using = consumable_to_printers.get(sku, [])
        
        c_row = {
            "sku": sku,
            "name": name,
            "category": cat or "Consumable",
            "brand": "Citizen" if "citizen" in name_l else "Epson",
            "color": color,
            "price_aed": p.get("price", ""),
            "stock": p.get("stock", ""),
            "availability": p.get("availability", ""),
            "yield_capacity": p.get("yield_capacity", ""),
            "product_url": p.get("website_url") or p.get("web_url") or "",
            "image_url": p.get("image_url") or p.get("image") or "",
            "description": p.get("description", ""),
            "compatible_printers_count": len(printers_using),
            "compatible_printers": "; ".join(printers_using)
        }
        processed_consumables.append(c_row)

# ---------------------------------------------------------
# 4. MASTER COMPLETE PRODUCTS DATASET
# ---------------------------------------------------------
master_products = []

# Add Printers
for p in hardware_printers:
    master_products.append({
        "item_type": "Hardware Printer",
        "id_or_sku": p["id"],
        "name": p["display_name"],
        "brand": p["brand"],
        "category": p["main_category"],
        "subcategory": p["subcategory"],
        "product_url": p["product_url"],
        "image_url": p["image_url"],
        "brochure_url": p["brochure_url"],
        "price_aed": p["price_aed"],
        "key_specifications": f"Sizes: {p['supported_print_sizes']} | Max Width: {p['max_width_inches']}\" | Speed: {p['print_speed']} | DPI: {p['dpi']} | Colours: {p['colour_specification'] or p['total_colours']}",
        "consumables_or_media_summary": f"{p['consumables_count']} genuine consumables: {p['consumables_skus']}",
        "description": p["short_description"] or p["full_description"] or p["applications"]
    })

# Add Scanners
for s in hardware_scanners:
    master_products.append({
        "item_type": "Hardware Scanner",
        "id_or_sku": s["id"],
        "name": s["display_name"],
        "brand": s["brand"],
        "category": "Scanner",
        "subcategory": s["scanner_type"] or s["subcategory"],
        "product_url": s["product_url"],
        "image_url": s["image_url"],
        "brochure_url": s["brochure_url"],
        "price_aed": s["price_aed"],
        "key_specifications": f"Type: {s['scanner_type']} | Scan Speed: {s['scan_speed']} | DPI: {s['dpi']} / {s['optical_resolution']} | Range: {s['scanning_range']} | Warranty: {s['warranty']}",
        "consumables_or_media_summary": f"Consumables: {s['consumables_skus']}",
        "description": s["short_description"] or s["full_description"] or s["features"]
    })

# Add Media & Paper
for m in processed_media:
    master_products.append({
        "item_type": "Media & Paper",
        "id_or_sku": m["sku"],
        "name": m["name"],
        "brand": m["brand"],
        "category": f"Media ({m['category']})",
        "subcategory": m["surface_finish"],
        "product_url": m["product_url"],
        "image_url": m["image_url"],
        "brochure_url": "",
        "price_aed": m["price_aed"],
        "key_specifications": f"Weight: {m['weight_gsm']} GSM | Finish: {m['surface_finish']} | Format: {m['format_type']} ({m['size_label']}) | Roll Width: {m['width_inches']}\" | Inks: {m['ink_compatibility']}",
        "consumables_or_media_summary": f"Compatible with: {m['compatible_printers']}",
        "description": f"{m['brand']} {m['name']} - {m['surface_finish']} {m['format_type']} media"
    })

# Add Consumables
for c in processed_consumables:
    master_products.append({
        "item_type": "Consumable",
        "id_or_sku": c["sku"],
        "name": c["name"],
        "brand": c["brand"],
        "category": c["category"],
        "subcategory": c["color"] or "Maintenance/Supply",
        "product_url": c["product_url"],
        "image_url": c["image_url"],
        "brochure_url": "",
        "price_aed": c["price_aed"],
        "key_specifications": f"Colour: {c['color']} | Yield/Cap: {c['yield_capacity']} | Stock: {c['stock']}",
        "consumables_or_media_summary": f"Fits {c['compatible_printers_count']} printers: {c['compatible_printers']}",
        "description": c["description"]
    })

# Helper to write CSV
def write_csv_file(filepath, rows, fieldnames):
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for r in rows:
            # ensure all fields exist
            clean_row = {k: r.get(k, "") for k in fieldnames}
            writer.writerow(clean_row)
    print(f"Wrote {len(rows)} records to {filepath}")

# Write CSV files
write_csv_file(
    OUTPUT_DIR / "master_complete_products.csv",
    master_products,
    ["item_type", "id_or_sku", "name", "brand", "category", "subcategory", "product_url", "image_url", "brochure_url", "price_aed", "key_specifications", "consumables_or_media_summary", "description"]
)

write_csv_file(
    OUTPUT_DIR / "hardware_printers.csv",
    hardware_printers,
    [
        "id", "display_name", "model_family", "brand", "main_category", "subcategory", "product_line",
        "product_url", "image_url", "brochure_url", "price_aed", "paper_size", "max_width_inches",
        "colour_mode", "functions", "applications", "supported_print_sizes", "print_speed", "dpi",
        "scanner_integrated", "dual_roll", "spectro", "memory", "total_colours", "colour_specification",
        "cartridge_sizes", "consumable_volume", "yield_capacity", "weight", "dimensions",
        "recommended_monthly_min", "recommended_monthly_max", "consumables_count", "consumables_skus"
    ]
)

write_csv_file(
    OUTPUT_DIR / "scanners.csv",
    hardware_scanners,
    [
        "id", "display_name", "model_family", "brand", "main_category", "subcategory", "scanner_type",
        "product_url", "image_url", "brochure_url", "price_aed", "scan_speed", "dpi",
        "optical_resolution", "optical_density", "scanning_range", "features", "warranty",
        "weight", "dimensions", "recommended_monthly_min", "recommended_monthly_max",
        "consumables_skus", "short_description"
    ]
)

write_csv_file(
    OUTPUT_DIR / "medias_and_papers.csv",
    processed_media,
    [
        "sku", "name", "family_code", "brand", "category", "surface_finish", "weight_gsm",
        "format_type", "size_label", "width_inches", "ink_compatibility", "compatible_printers",
        "product_url", "image_url", "price_aed"
    ]
)

write_csv_file(
    OUTPUT_DIR / "consumables.csv",
    processed_consumables,
    [
        "sku", "name", "category", "brand", "color", "price_aed", "stock", "availability",
        "yield_capacity", "compatible_printers_count", "compatible_printers", "product_url", "image_url", "description"
    ]
)

# ---------------------------------------------------------
# 5. WRITE RICH TRAINING CORPUS JSON & JSONL
# ---------------------------------------------------------
training_corpus = []
qa_pairs = []

# Generate rich text representation for training
for p in hardware_printers:
    text_desc = (
        f"Product: {p['display_name']} (Model: {p['model_family']}, Brand: {p['brand']})\n"
        f"Category: {p['main_category']} - {p['subcategory']}\n"
        f"Product Link: {p['product_url']}\n"
        f"Datasheet/Brochure: {p['brochure_url'] or 'Contact sales'}\n"
        f"Image URL: {p['image_url']}\n"
        f"Price: {p['price_aed'] or 'Quotation on request'}\n"
        f"Print Specifications: Max Width: {p['max_width_inches']} inches, Sizes: {p['supported_print_sizes']}, "
        f"Print Speed: {p['print_speed']}, Resolution: {p['dpi']}, Colour System: {p['colour_specification'] or p['total_colours']} colours\n"
        f"Hardware Features: Dual Roll: {p['dual_roll']}, Integrated Scanner: {p['scanner_integrated']}, Spectrophotometer: {p['spectro']}\n"
        f"Recommended Monthly Duty Cycle: {p['recommended_monthly_min']} to {p['recommended_monthly_max']} pages\n"
        f"Applications: {p['applications']}\n"
        f"Weight: {p['weight']}, Dimensions: {p['dimensions']}\n"
        f"Genuine Consumables ({p['consumables_count']} items): {p['consumables_skus']}\n"
    )
    if p["full_description"]:
        text_desc += f"Detailed Overview: {p['full_description']}\n"
    
    training_corpus.append({
        "id": p["id"],
        "entity_type": "printer",
        "title": p["display_name"],
        "brand": p["brand"],
        "product_url": p["product_url"],
        "image_url": p["image_url"],
        "brochure_url": p["brochure_url"],
        "specs": p,
        "consumables": p["consumables_skus"].split(", ") if p["consumables_skus"] else [],
        "training_text": text_desc.strip()
    })
    
    # QA Pair 1: Specs and Link
    qa_pairs.append({
        "instruction": f"Provide the official specifications and Kepler Tech product link for the {p['display_name']}.",
        "input": f"Tell me about {p['display_name']} specs and link",
        "output": (
            f"The {p['display_name']} is a genuine {p['brand']} {p['main_category'].replace('_', ' ')} solution.\n"
            f"• Product Link: {p['product_url']}\n"
            f"• Official Brochure: {p['brochure_url'] or 'Available upon request'}\n"
            f"• Print Capabilities: Max width {p['max_width_inches']}\", sizes {p['supported_print_sizes']}\n"
            f"• Speed & Resolution: {p['print_speed']}, {p['dpi']}\n"
            f"• Inks & Colours: {p['colour_specification'] or p['total_colours']}\n"
            f"• Applications: {p['applications']}\n"
            f"• Recommended Duty: {p['recommended_monthly_min']} - {p['recommended_monthly_max']} prints/month"
        )
    })
    
    # QA Pair 2: Consumables
    if p["consumables_skus"]:
        qa_pairs.append({
            "instruction": f"What genuine consumables and ink cartridges work with the {p['display_name']}?",
            "input": f"Compatible consumables for {p['display_name']}",
            "output": (
                f"The verified genuine consumables for the {p['display_name']} include: {p['consumables_skus']}.\n"
                f"For full consumable ordering and pricing, view the model at: {p['product_url']}"
            )
        })

# Scanners QA and Corpus
for s in hardware_scanners:
    text_desc = (
        f"Scanner: {s['display_name']} (Model: {s['model_family']}, Brand: {s['brand']})\n"
        f"Category: Scanner - {s['scanner_type']}\n"
        f"Product Link: {s['product_url']}\n"
        f"Datasheet/Brochure: {s['brochure_url'] or 'Contact sales'}\n"
        f"Image URL: {s['image_url']}\n"
        f"Price: {s['price_aed'] or 'Quotation on request'}\n"
        f"Scanning Specifications: Speed: {s['scan_speed']}, Optical Resolution: {s['optical_resolution']} ({s['dpi']}), "
        f"Optical Density: {s['optical_density']}, Scanning Range: {s['scanning_range']}\n"
        f"Features: {s['features']}\n"
        f"Warranty: {s['warranty']}\n"
        f"Weight: {s['weight']}, Dimensions: {s['dimensions']}\n"
        f"Maintenance & Consumables: {s['consumables_skus']}\n"
    )
    if s["full_description"]:
        text_desc += f"Overview: {s['full_description']}\n"
        
    training_corpus.append({
        "id": s["id"],
        "entity_type": "scanner",
        "title": s["display_name"],
        "brand": s["brand"],
        "product_url": s["product_url"],
        "image_url": s["image_url"],
        "brochure_url": s["brochure_url"],
        "specs": s,
        "consumables": s["consumables_skus"].split(", ") if s["consumables_skus"] else [],
        "training_text": text_desc.strip()
    })
    
    qa_pairs.append({
        "instruction": f"What are the specifications, scan speed, and product link for the {s['display_name']}?",
        "input": f"Give me details and link for {s['display_name']}",
        "output": (
            f"The {s['display_name']} is an official {s['brand']} document scanner.\n"
            f"• Product Link: {s['product_url']}\n"
            f"• Brochure Link: {s['brochure_url'] or 'Available upon request'}\n"
            f"• Scanner Type: {s['scanner_type']}\n"
            f"• Scan Speed: {s['scan_speed']}\n"
            f"• Optical Resolution: {s['optical_resolution']} ({s['dpi']})\n"
            f"• Scanning Range: {s['scanning_range']}\n"
            f"• Features: {s['features']}\n"
            f"• Warranty: {s['warranty']}"
        )
    })

# Media QA and Corpus
for m in processed_media:
    text_desc = (
        f"Media Product: {m['name']} (SKU: {m['sku']}, Brand: {m['brand']})\n"
        f"Category: {m['category']}, Finish: {m['surface_finish']}, Weight: {m['weight_gsm']} GSM\n"
        f"Format: {m['format_type'].upper()}, Size: {m['size_label']} (Width: {m['width_inches']} inches)\n"
        f"Ink Compatibility: {m['ink_compatibility']}\n"
        f"Compatible Hardware Models: {m['compatible_printers']}\n"
        f"Product Link: {m['product_url']}\n"
        f"Image Link: {m['image_url']}\n"
    )
    training_corpus.append({
        "sku": m["sku"],
        "entity_type": "media",
        "title": m["name"],
        "brand": m["brand"],
        "product_url": m["product_url"],
        "image_url": m["image_url"],
        "specs": m,
        "training_text": text_desc.strip()
    })

# Consumables Corpus
for c in processed_consumables:
    text_desc = (
        f"Consumable: {c['name']} (SKU: {c['sku']}, Brand: {c['brand']})\n"
        f"Category: {c['category']}, Colour: {c['color'] or 'N/A'}\n"
        f"Yield/Capacity: {c['yield_capacity'] or 'Standard'}\n"
        f"Price: {c['price_aed'] or 'Quotation on request'}, Stock: {c['stock']}\n"
        f"Compatible Hardware: {c['compatible_printers']}\n"
        f"Product Link: {c['product_url']}\n"
        f"Image Link: {c['image_url']}\n"
    )
    training_corpus.append({
        "sku": c["sku"],
        "entity_type": "consumable",
        "title": c["name"],
        "brand": c["brand"],
        "product_url": c["product_url"],
        "image_url": c["image_url"],
        "specs": c,
        "training_text": text_desc.strip()
    })

# Write JSON & JSONL
with open(OUTPUT_DIR / "complete_training_corpus.json", "w", encoding="utf-8") as f:
    json.dump(training_corpus, f, indent=2, ensure_ascii=False)
print(f"Wrote {len(training_corpus)} rich training records to {OUTPUT_DIR / 'complete_training_corpus.json'}")

with open(OUTPUT_DIR / "training_qa_pairs.jsonl", "w", encoding="utf-8") as f:
    for qa in qa_pairs:
        f.write(json.dumps(qa, ensure_ascii=False) + "\n")
print(f"Wrote {len(qa_pairs)} Q&A training pairs to {OUTPUT_DIR / 'training_qa_pairs.jsonl'}")

print("All sheets and training datasets generated successfully!")
