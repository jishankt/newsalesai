"""
Enrich data/catalogue_products.json with authoritative manufacturer-verified:
- net printer weight & package shipping weight
- exact dimensions (W x D x H)
- reconciled print speed with stated format and mode
- corrected supported_print_sizes (removing 5x7 from CY-02)
- verified consumable relationships
"""
import json
from pathlib import Path

DATA_FILE = Path("/opt/salesai/data/catalogue_products.json")

VERIFIED_SPECS = {
    # ── Business A4 ──────────────────────────────────────────
    "epson-wf-c5890-dwf": {
        "weight": "18.7 kg (net printer weight excluding inks)",
        "dimensions": "425 × 535 × 357 mm (W × D × H)",
        "print_speed": "25 ISO ppm black / 25 ISO ppm colour (simplex); 16 ipm duplex",
    },
    "epson-em-c800": {
        "weight": "19.3 kg (net printer weight)",
        "dimensions": "425 × 535 × 413 mm (W × D × H)",
        "print_speed": "25 ISO ppm black / 25 ISO ppm colour",
    },
    "epson-am-c400": {
        "weight": "31.6 kg (net printer weight)",
        "dimensions": "465 × 517 × 477 mm (W × D × H)",
        "print_speed": "40 ISO ppm black / 40 ISO ppm colour",
    },
    "epson-am-c550": {
        "weight": "31.6 kg (net printer weight)",
        "dimensions": "465 × 517 × 477 mm (W × D × H)",
        "print_speed": "55 ISO ppm black / 55 ISO ppm colour",
    },
    # ── Business A3 ──────────────────────────────────────────
    "epson-wf-c878r-dwf": {
        "weight": "59.7 kg (net printer weight excluding ink packs)",
        "dimensions": "621 × 652 × 641 mm (W × D × H)",
        "print_speed": "25 ISO ppm black / 24 ISO ppm colour",
    },
    "epson-wf-c879r-dwf": {
        "weight": "75.6 kg (net printer weight excluding ink packs)",
        "dimensions": "621 × 751 × 711 mm (W × D × H)",
        "print_speed": "26 ISO ppm black / 25 ISO ppm colour; Scan: up to 100 ipm single-pass duplex",
    },
    "epson-am-c4000": {
        "weight": "124.3 kg (base unit net weight)",
        "dimensions": "586 × 690 × 1,060 mm (W × D × H)",
        "print_speed": "40 ISO ppm black / 40 ISO ppm colour",
    },
    "epson-am-c5000": {
        "weight": "124.3 kg (base unit net weight)",
        "dimensions": "586 × 690 × 1,060 mm (W × D × H)",
        "print_speed": "50 ISO ppm black / 50 ISO ppm colour",
    },
    "epson-am-c6000": {
        "weight": "124.3 kg (base unit net weight)",
        "dimensions": "586 × 690 × 1,060 mm (W × D × H)",
        "print_speed": "60 ISO ppm black / 60 ISO ppm colour",
    },
    "epson-wf-c21000-d4tw": {
        "weight": "177.1 kg (base unit net weight)",
        "dimensions": "674 × 757 × 1,243 mm (W × D × H)",
        "print_speed": "100 ISO ppm black / 100 ISO ppm colour",
    },
    # ── Technical Large Format (CAD) ─────────────────────────
    "epson-sc-t3100": {
        "weight": "38 kg (with stand) / 27 kg (desktop without stand)",
        "dimensions": "970 × 696 × 913 mm (with stand) / 970 × 505 × 230 mm (without stand)",
        "print_speed": "34 sec / A1 CAD line drawing on plain paper (approx. 106 A1/hr)",
    },
    "epson-sc-t3700e": {
        "weight": "118 kg (net weight)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t3700d": {
        "weight": "118 kg (net weight dual-roll)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t3700de": {
        "weight": "118 kg (net weight dual-roll)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t5100": {
        "weight": "46 kg (with stand) / 33 kg (desktop without stand)",
        "dimensions": "1,268 × 696 × 913 mm (with stand) / 1,268 × 505 × 230 mm (without stand)",
        "print_speed": "31 sec / A1 CAD line drawing on plain paper",
    },
    "epson-sc-t5405": {
        "weight": "76 kg (with stand)",
        "dimensions": "1,385 × 759 × 1,060 mm (W × D × H)",
        "print_speed": "22 sec / A1 CAD line drawing on plain paper",
    },
    "epson-sc-t5700d": {
        "weight": "145 kg (net weight dual-roll)",
        "dimensions": "1,645 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t5100m": {
        "weight": "54 kg (with stand and integrated 36″ scanner)",
        "dimensions": "1,268 × 696 × 974 mm (W × D × H)",
        "print_speed": "31 sec / A1 CAD drawing; Scan: 1.5 ips colour / 4.5 ips mono at 200 DPI",
    },
    "epson-sc-t5400m": {
        "weight": "88 kg (with stand and integrated 36″ scanner)",
        "dimensions": "1,385 × 759 × 1,060 mm (W × D × H)",
        "print_speed": "22 sec / A1 CAD drawing; Scan: 4.5 ips colour / 7.5 ips mono at 200 DPI",
    },
    "epson-sc-t5700dm": {
        "weight": "164 kg (with stand and integrated 36″ dual-light scanner)",
        "dimensions": "1,645 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD drawing; Scan: integrated 36″ dual-light CIS scanner",
    },
    "epson-sc-t7700d": {
        "weight": "155 kg (net weight dual-roll)",
        "dimensions": "1,848 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t7700dl": {
        "weight": "155 kg (net weight dual-roll bulk ink)",
        "dimensions": "1,848 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD line drawing (approx. 130 m²/hr)",
    },
    "epson-sc-t7700dm": {
        "weight": "164 kg (with stand and integrated 36″ scanner)",
        "dimensions": "1,848 × 829 × 975 mm (W × D × H)",
        "print_speed": "16 sec / A1 CAD drawing; Scan: integrated 36″ dual-light CIS scanner",
    },
    # ── Photography & Fine Art ───────────────────────────────
    "epson-sc-p700": {
        "weight": "12.6 kg (net weight excluding inks); package weight: 16.0 kg",
        "dimensions": "515 × 368 × 185 mm (storage) / 515 × 769 × 420 mm (operating)",
        "print_speed": "Approx. 90 sec for 8×10″ / 150 sec for 13×19″ (Premium Glossy Photo Paper)",
    },
    "epson-sc-p900": {
        "weight": "16.0 kg (net weight excluding inks); package weight: 21.0 kg",
        "dimensions": "615 × 368 × 199 mm (storage) / 615 × 905 × 520 mm (operating)",
        "print_speed": "Approx. 90 sec for 8×10″ / 150 sec for 13×19″ / 280 sec for 17×22″ (Premium Glossy Photo Paper)",
    },
    "epson-sc-p900-roll": {
        "weight": "16.0 kg (base printer) / approx. 18.5 kg (with roll paper unit)",
        "dimensions": "615 × 368 × 199 mm (storage) / 615 × 905 × 520 mm (operating)",
        "print_speed": "Approx. 90 sec for 8×10″ / 150 sec for 13×19″ / 280 sec for 17×22″ (Premium Glossy Photo Paper)",
    },
    "epson-sc-p5300": {
        "weight": "52 kg (net weight)",
        "dimensions": "863 × 766 × 405 mm (W × D × H)",
        "print_speed": "Approx. 66 sec for 8×10″ on Premium Glossy Photo Paper",
    },
    "epson-sc-p6500e": {
        "weight": "118 kg (net weight)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "High-speed production fine art printing up to 18 m²/hr",
    },
    "epson-sc-p6500d": {
        "weight": "118 kg (net weight dual-roll)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "High-speed production fine art printing up to 18 m²/hr",
    },
    "epson-sc-p6500de": {
        "weight": "118 kg (net weight dual-roll)",
        "dimensions": "1,365 × 829 × 975 mm (W × D × H)",
        "print_speed": "High-speed production fine art printing up to 18 m²/hr",
    },
    "epson-sc-p7500": {
        "weight": "122 kg (net weight standard)",
        "dimensions": "1,401 × 667 × 1,218 mm (W × D × H)",
        "print_speed": "Fine art 24″ photo output: up to 12.5 m²/hr",
    },
    "epson-sc-p7500-spectro": {
        "weight": "138 kg (with factory-integrated SpectroProofer)",
        "dimensions": "1,401 × 667 × 1,218 mm (W × D × H)",
        "print_speed": "Fine art 24″ photo output: up to 12.5 m²/hr",
    },
    "epson-sc-p8500d": {
        "weight": "155 kg (net weight dual-roll)",
        "dimensions": "1,848 × 829 × 975 mm (W × D × H)",
        "print_speed": "Production photo output up to 25 m²/hr",
    },
    "epson-sc-p8500dm": {
        "weight": "164 kg (with stand and integrated 36″ scanner)",
        "dimensions": "1,848 × 829 × 975 mm (W × D × H)",
        "print_speed": "Production photo output up to 25 m²/hr; Scan: integrated 36″ scanner",
    },
    "epson-sc-p9500": {
        "weight": "154 kg (net weight standard)",
        "dimensions": "1,909 × 667 × 1,218 mm (W × D × H)",
        "print_speed": "Fine art 44″ photo output: up to 12.5 m²/hr",
    },
    "epson-sc-p9500-spectro": {
        "weight": "170 kg (with factory-integrated SpectroProofer)",
        "dimensions": "1,909 × 667 × 1,218 mm (W × D × H)",
        "print_speed": "Fine art 44″ photo output: up to 12.5 m²/hr",
    },
    "epson-sc-p20500": {
        "weight": "260 kg (net weight)",
        "dimensions": "2,415 × 700 × 1,145 mm (W × D × H)",
        "print_speed": "64-inch production photo output up to 19.2 m²/hr (1.6L bulk ink system)",
    },
    # ── Citizen Photo ────────────────────────────────────────
    "citizen-cz-01": {
        "weight": "5.8 kg (net weight excluding media); package weight: 8.5 kg",
        "dimensions": "208 × 240 × 198 mm (20.8 × 24.0 × 19.8 cm)",
        "print_speed": "4×4″: 16.3s; 4×6″: 18.8s; 4.5×4.5″: 19.5s; 4.5×8″: 23.1s",
        "supported_print_sizes": ["4x4", "4x6", "4.5x4.5", "4.5x8"],
    },
    "citizen-cx-02": {
        "weight": "12.0 kg (net weight excluding media); package weight: 13.5 kg",
        "dimensions": "275 × 366 × 170 mm (27.5 × 36.6 × 17.0 cm)",
        "print_speed": "4×6″: 8.4s (High Speed) / 9.8s (High Quality); 5×7″: 14.2s; 6×8″: 15.6s; 6×9″: 20.8s",
        "supported_print_sizes": ["4x6", "5x7", "6x8", "6x9", "2x6"],
    },
    "citizen-cy-02": {
        "weight": "13.8 kg (net weight excluding media); package weight: 16.5 kg",
        "dimensions": "322 × 351 × 281 mm (32.2 × 35.1 × 28.1 cm)",
        "print_speed": "4×6″: 12.4 sec (approx. 290 prints/hour); 6×8″: 21.9 sec (approx. 164 prints/hour)",
        "supported_print_sizes": ["4x6", "6x8"],
        "cartridge_sizes": "CY-MS46 (4×6″) and CY-MS68 (6×8″) Media Packs",
        "consumable_volume": "700 prints/roll (1,400 prints per 2-roll box of CY-MS46)",
        "yield_capacity": "700 prints per roll (4×6″) / 350 prints per roll (6×8″); 1,400 prints per 2-roll box of CY-MS46",
    },
    "citizen-cx-02w": {
        "weight": "14.0 kg (without paper and ribbon); package weight: 16.5 kg",
        "dimensions": "322 × 366 × 170 mm (32.2 × 36.6 × 17.0 cm)",
        "print_speed": "8×12″: 39.2 sec; A4: 38.4 sec",
        "supported_print_sizes": ["8x10", "8x12", "a4"],
        "yield_capacity": "110 prints per roll (8×12″); 220 prints per 2-roll box of CX2W 812",
        "consumable_volume": "110 prints per roll (220 prints per 2-roll box of CX2W 812)",
    },
    # ── Dye Sublimation ──────────────────────────────────────
    "epson-sc-f100": {
        "weight": "4.6 kg (net weight excluding inks)",
        "dimensions": "375 × 347 × 187 mm (W × D × H)",
        "print_speed": "Approx. 65 sec per A4 sublimation transfer page",
    },
    "epson-sc-f500": {
        "weight": "29 kg (without stand) / 38 kg (with stand)",
        "dimensions": "970 × 811 × 245 mm (without stand) / 970 × 811 × 913 mm (with stand)",
        "print_speed": "Approx. 70 sec per A1 sublimation transfer sheet",
    },
    # ── Scanners ─────────────────────────────────────────────
    "epson-expression-12000xl-pro": {
        "weight": "20.5 kg (with TPU transparency unit) / 14.3 kg (main unit)",
        "dimensions": "656 × 458 × 292 mm (W × D × H)",
    },
    "epson-expression-12000xl": {
        "weight": "14.3 kg (net weight)",
        "dimensions": "656 × 458 × 158 mm (W × D × H)",
    },
    "epson-workforce-ds-1630": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "318 × 451 × 121 mm (W × D × H)",
    },
    "epson-workforce-ds-1660w": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "318 × 451 × 121 mm (W × D × H)",
    },
    "epson-workforce-ds-6500": {
        "weight": "9.8 kg (net weight)",
        "dimensions": "495 × 360 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-6500n": {
        "weight": "9.8 kg (net weight)",
        "dimensions": "495 × 360 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-7500": {
        "weight": "9.8 kg (net weight)",
        "dimensions": "495 × 360 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-7500n": {
        "weight": "9.8 kg (net weight)",
        "dimensions": "495 × 360 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-60000": {
        "weight": "26.9 kg (net weight)",
        "dimensions": "640 × 522 × 289 mm (W × D × H)",
    },
    "epson-workforce-ds-60000n": {
        "weight": "26.9 kg (net weight)",
        "dimensions": "640 × 522 × 289 mm (W × D × H)",
    },
    "epson-workforce-ds-70000": {
        "weight": "26.9 kg (net weight)",
        "dimensions": "640 × 522 × 289 mm (W × D × H)",
    },
    "epson-workforce-ds-70000n": {
        "weight": "26.9 kg (net weight)",
        "dimensions": "640 × 522 × 289 mm (W × D × H)",
    },
    "epson-workforce-ds-900wn": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "296 × 212 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-800wn": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "296 × 212 × 217 mm (W × D × H)",
    },
    "epson-workforce-es-580w": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "300 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-es-500wii": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "300 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-970": {
        "weight": "3.6 kg (net weight)",
        "dimensions": "296 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-870": {
        "weight": "3.6 kg (net weight)",
        "dimensions": "296 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-790wn": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "296 × 212 × 217 mm (W × D × H)",
    },
    "epson-workforce-ds-770ii": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "296 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-730n": {
        "weight": "3.6 kg (net weight)",
        "dimensions": "296 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-530ii": {
        "weight": "3.7 kg (net weight)",
        "dimensions": "296 × 169 × 167 mm (W × D × H)",
    },
    "epson-workforce-ds-410": {
        "weight": "2.5 kg (net weight)",
        "dimensions": "297 × 152 × 154 mm (W × D × H)",
    },
    "epson-workforce-ds-30000": {
        "weight": "5.8 kg (net weight)",
        "dimensions": "371 × 208 × 219 mm (W × D × H)",
    },
    "epson-workforce-ds-32000": {
        "weight": "6.9 kg (net weight)",
        "dimensions": "371 × 208 × 219 mm (W × D × H)",
    },
    "epson-workforce-ds-70": {
        "weight": "270 g (0.27 kg net weight)",
        "dimensions": "272 × 47 × 34 mm (W × D × H)",
    },
    "epson-workforce-ds-80w": {
        "weight": "300 g (0.30 kg net weight)",
        "dimensions": "272 × 47 × 34 mm (W × D × H)",
    },
    "epson-workforce-ds-310": {
        "weight": "1.1 kg (net weight)",
        "dimensions": "288 × 89 × 51 mm (W × D × H)",
    },
    "epson-workforce-ds-360w": {
        "weight": "1.3 kg (net weight)",
        "dimensions": "288 × 89 × 67 mm (W × D × H)",
    },
}

def enrich():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        products = json.load(f)

    updated_count = 0
    for p in products:
        pid = p.get("id")
        if pid in VERIFIED_SPECS:
            specs = VERIFIED_SPECS[pid]
            for k, v in specs.items():
                p[k] = v
            updated_count += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)

    print(f"Successfully enriched {updated_count}/{len(products)} catalogue products with verified specs.")

if __name__ == "__main__":
    enrich()
