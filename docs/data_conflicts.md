# Data Conflicts Log

*Logged during Phase 0 Audit for Kepler Tech Sales AI.*  
*Per instruction: Catalogue JSON values are preserved in runtime until user decision is finalized.*

---

### 1. SC-P8500D / SC-P8500DM Print Speed
- **Brochure / Datasheet Claim:** `18 m²/hr`
- **Catalogue JSON (`data/catalogue_products.json`):** `Production photo output up to 25 m²/hr`
- **Current Runtime Behavior:** Uses Catalogue JSON value (`25 m²/hr`).
- **Status:** Pending user decision.

---

### 2. WorkForce Enterprise EM-C800 Recommended Monthly Volume
- **Brochure / Datasheet Claim:** `2,500 – 10,000 pages`
- **Catalogue JSON (`data/catalogue_products.json`):** `recommended_monthly_min: 1,000`, `recommended_monthly_max: 10,000`
- **Current Runtime Behavior:** Uses Catalogue JSON range (`1,000 – 10,000 pages`).
- **Status:** Pending user decision.

---

### 3. Citizen Photo Print Speeds
- **Citizen CX-02:**
  - **Brochure Claim:** `8.8s` (4×6″)
  - **Catalogue JSON:** `8.4s (High Speed) / 9.8s (High Quality)`
- **Citizen CY-02:**
  - **Brochure Claim:** `14.9s` (4×6″)
  - **Catalogue JSON:** `12.4 seconds (approx. 290 prints/hour)`
- **Citizen CX-02W:**
  - **Brochure Claim:** `33.7s` (8×10″)
  - **Catalogue JSON:** `39.2 sec (8×12″) / 38.4 sec (A4)`
- **Current Runtime Behavior:** Uses Catalogue JSON values.
- **Status:** Pending user decision.

---

### 4. Citizen CX-02 Supported Print Dimensions
- **Brochure Claim:** `5×5″, 6×6″` square photo cuts explicitly highlighted.
- **Catalogue JSON:** `["4x6", "5x7", "6x8", "6x9", "2x6"]`
- **Current Runtime Behavior:** Uses Catalogue JSON array.
- **Status:** Pending user decision.
