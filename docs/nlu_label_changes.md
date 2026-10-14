# NLU Dataset Label Changes Log

This document records all changes made to dataset labels during Step 0 of the NLU accuracy audit and fix process, adhering to the compound turn scoring rules:
A prediction is scored as correct if `pred_intent == exp_intent` OR the prediction's secondary list covers the compound intent set.

## Compound Intent Label Additions

1. **`real_006`** (`"How much is the printer and do you deliver to Dubai Marina?"`):
   - Added `secondary_intents: ["shipping_or_delivery"]` alongside primary `availability_or_price_policy` (inquiry asks both price and delivery location).
2. **`real_018`** (`"Do you have stock available in Dubai right now for immediate delivery?"`):
   - Added `secondary_intents: ["shipping_or_delivery"]` alongside primary `availability_or_price_policy` (inquiry asks both local stock availability and delivery timeline).
3. **`compound_intents_001`** (`"price, stock and delivery?"`):
   - Primary: `availability_or_price_policy`, `secondary_intents: ["shipping_or_delivery"]` (combined pricing/stock inquiry and delivery inquiry).
4. **`compound_intents_002`** (`"compare CX-02 and CY-02 and tell me ink cost"`):
   - Primary: `compare`, `secondary_intents: ["availability_or_price_policy"]` (model comparison combined with operational consumable running cost).
5. **`compound_intents_003`** (`"is SC-T3100 available in stock and how fast can you deliver?"`):
   - Primary: `availability_or_price_policy`, `secondary_intents: ["shipping_or_delivery"]` (stock check combined with delivery speed).
6. **`compound_intents_004`** (`"what is the price of SC-P7500 and what inks does it use?"`):
   - Primary: `availability_or_price_policy`, `secondary_intents: ["consumables_lookup"]` (hardware price combined with ink set lookup).
7. **`compound_intents_005`** (`"give me specifications, dimensions and quotation for 2 units"`):
   - Primary: `product_info`, `secondary_intents: ["quote_request"]` (technical dimensions combined with commercial quote).
8. **`compound_intents_006`** (`"can you deliver to Abu Dhabi and give 10% discount?"`):
   - Primary: `shipping_or_delivery`, `secondary_intents: ["discount_request"]` (delivery location combined with pricing discount).
9. **`compound_intents_008`** (`"is P900 compatible with roll paper and what is the cost?"`):
   - Primary: `product_info`, `secondary_intents: ["availability_or_price_policy"]` (roll unit compatibility combined with hardware price).
10. **`compound_intents_010`** (`"how much is the F500 and what is the cost per print?"`):
    - Primary: `availability_or_price_policy`, `secondary_intents: ["product_info"]` (upfront printer price combined with running cost inquiry).
11. **`compound_intents_011`** (`"compare AM-C4000 with WF-C20600 and send official quotation"`):
    - Primary: `compare`, `secondary_intents: ["quote_request"]` (comparison combined with request for formal quotation).
12. **`compound_intents_012`** (`"does SC-T5405 have Wi-Fi and how much does it cost?"`):
    - Primary: `product_info`, `secondary_intents: ["availability_or_price_policy"]` (Wi-Fi connectivity spec combined with printer price).
13. **`compound_intents_013`** (`"send brochure and quote for 3 units"`):
    - Primary: `product_info`, `secondary_intents: ["quote_request"]` (product brochure request combined with 3-unit quotation).
14. **`compound_intents_014`** (`"what inks does Citizen CZ-01 use and are they in stock?"`):
    - Primary: `consumables_lookup`, `secondary_intents: ["availability_or_price_policy"]` (media ribbon lookup combined with stock check).
15. **`compound_intents_015`** (`"can I visit your store in Khalid Bin Waleed today and test print?"`):
    - Primary: `contact_showroom`, `secondary_intents: ["product_info"]` (store visit combined with print demonstration).
16. **`compound_intents_016`** (`"tell me about warranty and delivery charges"`):
    - Primary: `product_info`, `secondary_intents: ["shipping_or_delivery"]` (warranty coverage combined with shipping fee inquiry).
17. **`compound_intents_017`** (`"which is cheaper CX-02 or CY-02 and what is the per print cost?"`):
    - Primary: `compare`, `secondary_intents: ["availability_or_price_policy"]` (pricing comparison combined with per-print running cost).
18. **`compound_intents_018`** (`"give me price of DS-1630 and compatible scanner sheetfed options"`):
    - Primary: `availability_or_price_policy`, `secondary_intents: ["alternatives"]` (scanner pricing combined with alternative model recommendations).
19. **`compound_intents_019`** (`"is this in stock in Dubai and can you deliver today?"`):
    - Primary: `availability_or_price_policy`, `secondary_intents: ["shipping_or_delivery"]` (stock confirmation combined with express same-day delivery).
20. **`compound_intents_020`** (`"how much ink does P7500 consume and what is replacement ink cost?"`):
    - Primary: `product_info`, `secondary_intents: ["consumables_lookup"]` (ink consumption duty spec combined with replacement ink cartridge pricing).
21. **`price_and_policy_004`** (`"send me a quotation for 5 units with custom setup"`):
    - Primary: `custom_config_request`, `secondary_intents: ["quote_request"]` (custom setup request combined with volume quote request).
22. **`reference_resolution_020`** (`"give me discount on it"`):
    - Primary: `discount_request`, `secondary_intents: ["availability_or_price_policy"]` (discount negotiation combined with base pricing request).
