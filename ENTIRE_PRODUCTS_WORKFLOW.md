# Kepler Tech SalesAI — Complete Product Qualification & Category Workflows

This document contains the complete qualification flows, decision trees, and deterministic subcategory mappings for all **43 certified hardware printers** and **29 professional scanners** in the Kepler Tech catalogue.

---

## 1. Product Qualification Flowchart: Overview

```mermaid
flowchart LR
    INQ["Customer Inquiry / Prompt"] --> CAT["Identify Primary Category"]

    CAT -->|"Office / Multifunction"| OFF["Office Enterprise<br/>A4 and A3 MFPs"]
    CAT -->|"CAD / Blueprint / GIS"| CAD["Technical Large Format<br/>24, 36, 44 inch plotters"]
    CAT -->|"Photo / Fine Art / Gallery"| PHO["Photography & Fine Art<br/>13 to 64 inch printers"]
    CAT -->|"Photo Booth / Instant Photo"| CTZ["Citizen Dye-Sub Photo<br/>4, 6, 8 inch printers"]
    CAT -->|"Apparel / T-Shirt / Mug"| DYE["Dye Sublimation<br/>A4 desktop and 24 inch roll"]
    CAT -->|"Scanning Solutions"| SCN["Professional Scanners<br/>Fine art, hybrid, sheetfed"]

    style INQ fill:#0f172a,stroke:#020617,color:#ffffff
    style CAT fill:#fef3c7,stroke:#d97706,color:#000000
    style OFF fill:#2563eb,stroke:#1d4ed8,color:#ffffff
    style CAD fill:#7c3aed,stroke:#6d28d9,color:#ffffff
    style PHO fill:#db2777,stroke:#be185d,color:#ffffff
    style CTZ fill:#ea580c,stroke:#c2410c,color:#ffffff
    style DYE fill:#0d9488,stroke:#0f766e,color:#ffffff
    style SCN fill:#475569,stroke:#334155,color:#ffffff
```

---

## 2. Office / Multifunction (3 Subcategories in A4 & 3 Subcategories in A3)

```mermaid
flowchart LR
    ROOT["Office Enterprise"] --> SIZE{"Paper Size"}

    %% ================= A4 OUTPUT =================
    SIZE -->|"A4 Output"| A4_SUB{"A4 Subcategories"}

    %% A4 Subcat 1: Standard Desktop MFP
    A4_SUB -->|"1. a4_standard_mfp<br/>(Low Volume)"| A4_S1["Standard Business MFP<br/><b>< 100 pages/day</b>"]
    A4_S1 --> M1["<b>WorkForce Pro WF-C5890DWF</b><br/>• Speed: <b>25 ISO ppm</b> (34 ppm draft)<br/>• Daily: <b>< 100 pages/day</b><br/>• Monthly: <b>500 – 5,000 pages/mo</b> (Max: 45k)"]

    %% A4 Subcat 2: Compact RIPS
    A4_SUB -->|"2. a4_compact_rips<br/>(Medium Volume)"| A4_S2["Compact RIPS MFP<br/><b>100 – 300 pages/day</b>"]
    A4_S2 --> M2["<b>WorkForce Pro EM-C800</b><br/>• Speed: <b>25 ISO ppm</b> (High-Yield RIPS)<br/>• Daily: <b>100 – 300 pages/day</b><br/>• Monthly: <b>1,000 – 10,000 pages/mo</b> (Max: 50k)"]

    %% A4 Subcat 3: Enterprise Line-Head
    A4_SUB -->|"3. a4_enterprise_linehead<br/>(High Volume)"| A4_S3["Enterprise Line-Head MFP<br/><b>300 – 2,000+ pages/day</b>"]
    A4_S3 --> M3["<b>WorkForce Enterprise AM-C400</b><br/>• Speed: <b>40 ISO ppm</b> Line-Head<br/>• Daily: <b>300 – 800 pages/day</b><br/>• Monthly: <b>1,500 – 15,000 pages/mo</b> (Max: 100k)"]
    A4_S3 --> M4["<b>WorkForce Enterprise AM-C550</b><br/>• Speed: <b>55 ISO ppm</b> Line-Head<br/>• Daily: <b>800 – 2,000+ pages/day</b><br/>• Monthly: <b>2,000 – 20,000+ pages/mo</b> (Max: 150k)"]

    %% ================= A3 OUTPUT =================
    SIZE -->|"A3 Output"| A3_SUB{"A3 Subcategories"}

    %% A3 Subcat 1: Departmental RIPS
    A3_SUB -->|"1. a3_departmental_rips<br/>(Low-to-Mid Volume)"| A3_S1["Departmental RIPS MFP<br/><b>100 – 500 pages/day</b>"]
    A3_S1 --> M5["<b>WorkForce Pro WF-C878R DWF</b><br/>• Speed: <b>25 ISO ppm</b> (45 ipm ADF scan)<br/>• Daily: <b>100 – 400 pages/day</b><br/>• Monthly: <b>1,500 – 10,000 pages/mo</b> (Max: 75k)"]
    A3_S1 --> M6["<b>WorkForce Pro WF-C879R DWF</b><br/>• Speed: <b>26 ISO ppm</b> (100 ipm single-pass scan)<br/>• Daily: <b>200 – 500 pages/day</b><br/>• Monthly: <b>2,000 – 15,000 pages/mo</b> (Max: 75k)"]

    %% A3 Subcat 2: Enterprise Line-Head
    A3_SUB -->|"2. a3_enterprise_linehead<br/>(Departmental High Volume)"| A3_S2["Enterprise Line-Head MFP<br/><b>500 – 3,500 pages/day</b>"]
    A3_S2 --> M7["<b>WorkForce Enterprise AM-C4000</b><br/>• Speed: <b>40 ISO ppm</b> Line-Head<br/>• Daily: <b>500 – 1,500 pages/day</b><br/>• Monthly: <b>5,000 – 30,000 pages/mo</b> (Max: 200k)"]
    A3_S2 --> M8["<b>WorkForce Enterprise AM-C5000</b><br/>• Speed: <b>50 ISO ppm</b> Line-Head<br/>• Daily: <b>1,500 – 2,500 pages/day</b><br/>• Monthly: <b>7,000 – 40,000 pages/mo</b> (Max: 250k)"]
    A3_S2 --> M9["<b>WorkForce Enterprise AM-C6000</b><br/>• Speed: <b>60 ISO ppm</b> Line-Head<br/>• Daily: <b>2,000 – 3,500 pages/day</b><br/>• Monthly: <b>10,000 – 60,000 pages/mo</b> (Max: 300k)"]

    %% A3 Subcat 3: Flagship Ultra High-Speed
    A3_SUB -->|"3. a3_production_flagship<br/>(Continuous Central Repro)"| A3_S3["Ultra High-Speed Flagship<br/><b>3,000 – 10,000+ pages/day</b>"]
    A3_S3 --> M10["<b>WorkForce Enterprise WF-C21000 D4TW</b><br/>• Speed: <b>100 ISO ppm</b> Line-Head<br/>• Daily: <b>3,000 – 10,000+ pages/day</b><br/>• Monthly: <b>15,000 – 100,000+ pages/mo</b> (Max: 400k)"]

    style ROOT fill:#2563eb,stroke:#1d4ed8,color:#ffffff
    style SIZE fill:#fef3c7,stroke:#d97706,color:#000000
    style A4_SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style A3_SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style A4_S1 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style A4_S2 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style A4_S3 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style A3_S1 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style A3_S2 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
    style A3_S3 fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
```

### Office Volume & Speed Calculation Reference

| Format | Subcategory | Model | Speed | Daily Pages | Recommended Monthly Volume | Max Monthly Duty |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **A4** | `a4_standard_mfp` | **WF-C5890DWF** | 25 ppm | < 100 pages | 500 – 5,000 | 45,000 |
| **A4** | `a4_compact_rips` | **EM-C800** | 25 ppm | 100 – 300 pages | 1,000 – 10,000 | 50,000 |
| **A4** | `a4_enterprise_linehead` | **AM-C400** | 40 ppm | 300 – 800 pages | 1,500 – 15,000 | 100,000 |
| **A4** | `a4_enterprise_linehead` | **AM-C550** | 55 ppm | 800 – 2,000 pages | 2,000 – 20,000+ | 150,000 |
| **A3** | `a3_departmental_rips` | **WF-C878R DWF** | 25 ppm | 100 – 400 pages | 1,500 – 10,000 | 75,000 |
| **A3** | `a3_departmental_rips` | **WF-C879R DWF** | 26 ppm | 200 – 500 pages | 2,000 – 15,000 | 75,000 |
| **A3** | `a3_enterprise_linehead` | **AM-C4000** | 40 ppm | 500 – 1,500 pages | 5,000 – 30,000 | 200,000 |
| **A3** | `a3_enterprise_linehead` | **AM-C5000** | 50 ppm | 1,500 – 2,500 pages | 7,000 – 40,000 | 250,000 |
| **A3** | `a3_enterprise_linehead` | **AM-C6000** | 60 ppm | 2,000 – 3,500 pages | 10,000 – 60,000 | 300,000 |
| **A3** | `a3_production_flagship` | **WF-C21000 D4TW** | 100 ppm | 3,000 – 10,000+ pages | 15,000 – 100,000+ | 400,000 |

---

## 3. CAD / Technical Large Format (`technical_large_format` — All 13 Models)

```mermaid
flowchart LR
    ROOT["Technical Large Format (CAD/GIS)"] --> SUB{"Select Subcategory"}

    %% 1. 24-inch Print-Only
    SUB -->|"technical_24_print_only"| S_T24["24-inch Print-Only (A1)"]
    S_T24 --> T1["SureColor SC-T3100<br/>• Entry desktop / stand | 34s/A1 | XD2 inks"]
    S_T24 --> T2["SureColor SC-T3700E<br/>• Compact production single roll | 16s/A1 | Red ink"]
    S_T24 --> T3["SureColor SC-T3700D<br/>• Production dual roll auto-switching | 16s/A1"]
    S_T24 --> T4["SureColor SC-T3700DE<br/>• Production dual roll + Adobe PostScript"]

    %% 2. 36-inch Print-Only
    SUB -->|"technical_36_print_only"| S_T36_P["36-inch Print-Only (A0)"]
    S_T36_P --> T5["SureColor SC-T5100<br/>• Entry 36″ stand plotter | 31s/A1"]
    S_T36_P --> T6["SureColor SC-T5405<br/>• High-speed production CAD | 22s/A1"]
    S_T36_P --> T7["SureColor SC-T5700D<br/>• Dual roll production + Red ink | 16s/A1"]

    %% 3. 36-inch Multifunction (MFP)
    SUB -->|"technical_36_multifunction"| S_T36_M["36-inch Multifunction (MFP)"]
    S_T36_M --> T8["SureColor SC-T5100M<br/>• Compact 36″ CIS scanner MFP"]
    S_T36_M --> T9["SureColor SC-T5400M<br/>• Production 36″ CIS scanner MFP"]
    S_T36_M --> T10["SureColor SC-T5700DM<br/>• Dual-roll + 36″ dual-light CIS scanner"]

    %% 4. 44-inch Print-Only
    SUB -->|"technical_44_print_only"| S_T44_P["44-inch Print-Only"]
    S_T44_P --> T11["SureColor SC-T7700D<br/>• 44″ dual roll production (700ml cartridges)"]
    S_T44_P --> T12["SureColor SC-T7700DL<br/>• 44″ dual roll with 1.6L bulk ink supply"]

    %% 5. 44-inch Multifunction (MFP)
    SUB -->|"technical_44_multifunction"| S_T44_M["44-inch Multifunction (MFP)"]
    S_T44_M --> T13["SureColor SC-T7700DM<br/>• 44″ dual roll + integrated 36″ scanner"]

    style ROOT fill:#7c3aed,stroke:#6d28d9,color:#ffffff
    style SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style S_T24 fill:#ede9fe,stroke:#8b5cf6,color:#4c1d95
    style S_T36_P fill:#ede9fe,stroke:#8b5cf6,color:#4c1d95
    style S_T36_M fill:#ede9fe,stroke:#8b5cf6,color:#4c1d95
    style S_T44_P fill:#ede9fe,stroke:#8b5cf6,color:#4c1d95
    style S_T44_M fill:#ede9fe,stroke:#8b5cf6,color:#4c1d95
```

---

## 4. Photography & Fine Art (`photography_large_format` — All 14 Models)

```mermaid
flowchart LR
    ROOT["Photography & Fine Art"] --> SUB{"Select Subcategory"}

    %% 1. 13-inch Desktop
    SUB -->|"photo_13_desktop"| S_P13["13-inch Desktop (A3+)"]
    S_P13 --> P1["SureColor SC-P700<br/>• 10-colour UltraChrome PRO10 | Carbon Black Mode"]

    %% 2. 17-inch Desktop & Heavy Duty
    SUB -->|"photo_17_desktop"| S_P17["17-inch Desktop & Production (A2+)"]
    S_P17 --> P2["SureColor SC-P900<br/>• 17″ desktop sheet photo printer"]
    S_P17 --> P3["SureColor SC-P900 with Roll Adapter<br/>• 17″ panoramic roll photo printer"]
    S_P17 --> P4["SureColor SC-P5300<br/>• 17″ heavy-duty production roll (PRO10 + Violet)"]

    %% 3. 24-inch Professional
    SUB -->|"photo_24_professional"| S_P24["24-inch Professional Studio"]
    S_P24 --> P5["SureColor SC-P6500E<br/>• 24″ 6-colour PRO6 compact single roll"]
    S_P24 --> P6["SureColor SC-P6500D<br/>• 24″ 6-colour PRO6 compact dual roll"]
    S_P24 --> P7["SureColor SC-P6500DE<br/>• 24″ 6-colour PRO6 dual roll + Adobe PS"]
    S_P24 --> P8["SureColor SC-P7500<br/>• 24″ 12-colour UltraChrome PRO12 (99% Pantone)"]
    S_P24 --> P9["SureColor SC-P7500 Spectro<br/>• 24″ automated ILS30 spectrophotometer proofer"]

    %% 4. 44-inch Professional
    SUB -->|"photo_44_professional"| S_P44["44-inch Professional Gallery"]
    S_P44 --> P10["SureColor SC-P8500D<br/>• 44″ 6-colour PRO6 dual roll commercial photo"]
    S_P44 --> P11["SureColor SC-P8500DM<br/>• 44″ dual roll commercial photo + 36″ scanner"]
    S_P44 --> P12["SureColor SC-P9500<br/>• 44″ 12-colour UltraChrome PRO12 master studio"]
    S_P44 --> P13["SureColor SC-P9500 Spectro<br/>• 44″ automated ILS30 spectrophotometer proofer"]

    %% 5. 64-inch Production
    SUB -->|"photo_64_production"| S_P64["64-inch High-Volume Production"]
    S_P64 --> P14["SureColor SC-P20500<br/>• 64″ 12-colour PRO12 | 1.6L bulk ink packs"]

    style ROOT fill:#db2777,stroke:#be185d,color:#ffffff
    style SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style S_P13 fill:#fce7f3,stroke:#ec4899,color:#831843
    style S_P17 fill:#fce7f3,stroke:#ec4899,color:#831843
    style S_P24 fill:#fce7f3,stroke:#ec4899,color:#831843
    style S_P44 fill:#fce7f3,stroke:#ec4899,color:#831843
    style S_P64 fill:#fce7f3,stroke:#ec4899,color:#831843
```

---

## 5. Photo Booth / Instant Photo (`citizen_photo` — All 4 Models)

```mermaid
flowchart LR
    ROOT["Citizen Dye-Sub Photo"] --> SUB{"Select Subcategory"}

    %% 4-inch
    SUB -->|"citizen_4_inch"| S_C4["4-inch Ultra-Compact"]
    S_C4 --> C1["Citizen CZ-01<br/>• 5.8 kg ultra-compact | 4x6″ and 4.5x8″ prints"]

    %% 6-inch
    SUB -->|"citizen_6_inch"| S_C6["6-inch Event Photos"]
    S_C6 --> C2["Citizen CX-02<br/>• Fast 8.4s print | Ribbon-save rewind (4x6, 5x7, 6x8)"]
    S_C6 --> C3["Citizen CY-02<br/>• High-capacity 700 prints/roll | Heavy duty kiosk"]

    %% 8-inch
    SUB -->|"citizen_8_inch"| S_C8["8-inch Wide Event"]
    S_C8 --> C4["Citizen CX-02W<br/>• 8x10″ and 8x12″ pro prints | Metallic & Silver Pearl"]

    style ROOT fill:#ea580c,stroke:#c2410c,color:#ffffff
    style SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style S_C4 fill:#ffedd5,stroke:#f97316,color:#7c2d12
    style S_C6 fill:#ffedd5,stroke:#f97316,color:#7c2d12
    style S_C8 fill:#ffedd5,stroke:#f97316,color:#7c2d12
```

---

## 6. Apparel / T-Shirt / Mug (`dye_sublimation` — All 2 Models)

```mermaid
flowchart LR
    ROOT["Dye Sublimation"] --> SUB{"Select Subcategory"}

    %% A4 Desktop
    SUB -->|"dye_sublimation_desktop"| S_D1["A4 Desktop Gifts"]
    S_D1 --> D1["SureColor SC-F100 Sublimation Printer<br/>• Refillable ink tanks (140ml)<br/>• For mugs, phone covers, badges, small gifts"]

    %% 24-inch Roll
    SUB -->|"dye_sublimation_24_inch"| S_D2["24-inch Roll Apparel"]
    S_D2 --> D2["SureColor SC-F500 Sublimation Printer<br/>• 24″ continuous roll + auto sheet feeder<br/>• For sports jerseys, apparel, soft signage"]

    style ROOT fill:#0d9488,stroke:#0f766e,color:#ffffff
    style SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style S_D1 fill:#ccfbf1,stroke:#14b8a6,color:#134e4a
    style S_D2 fill:#ccfbf1,stroke:#14b8a6,color:#134e4a
```

---

## 7. Scanning Solutions (`scanners` — All 29 Models)

```mermaid
flowchart LR
    ROOT["Professional Scanners"] --> SUB{"Select Subcategory"}

    %% Photo Scanners
    SUB -->|"photo_scanners"| S_PH["Graphic & Fine Art Film"]
    S_PH --> SC1["Expression 12000XL (A3 Fine Art Flatbed)"]
    S_PH --> SC2["Expression 12000XL Pro (Includes TPU Film Unit)"]

    %% Hybrid Scanners
    SUB -->|"hybrid_scanners"| S_HY["Books & Stacks (Hybrid Flatbed + ADF)"]
    S_HY --> SC3["WorkForce DS-1630 / DS-1660W (A4 Flatbed + 50-page ADF)"]
    S_HY --> SC4["WorkForce DS-6500 / DS-6500N / DS-7500 / DS-7500N (A4 Flatbed + 100-page ADF)"]
    S_HY --> SC5["WorkForce DS-60000 / DS-60000N / DS-70000 / DS-70000N (A3 Flatbed + 200-page ADF)"]

    %% Business Sheetfed Scanners
    SUB -->|"business_scanners"| S_BIZ["Fast Sheetfed Business"]
    S_BIZ --> SC6["Mobile / Portable: DS-70, DS-80W, DS-310, DS-360W"]
    S_BIZ --> SC7["Desktop Workgroup (35–45 ppm): DS-410, DS-530II, ES-500WII, ES-580W"]
    S_BIZ --> SC8["High-Speed Network (65–90 ppm): DS-730N, DS-770II, DS-790WN, DS-800WN, DS-870, DS-970, DS-900WN"]
    S_BIZ --> SC9["A3 Production (70–85 ppm): DS-30000, DS-32000"]

    style ROOT fill:#475569,stroke:#334155,color:#ffffff
    style SUB fill:#fef3c7,stroke:#d97706,color:#000000
    style S_PH fill:#e2e8f0,stroke:#64748b,color:#0f172a
    style S_HY fill:#e2e8f0,stroke:#64748b,color:#0f172a
    style S_BIZ fill:#e2e8f0,stroke:#64748b,color:#0f172a
```
