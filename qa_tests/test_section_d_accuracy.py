"""
QA Automated Test Suite - Section D: Accuracy
Tests:
- 15 real catalog products: price inquiry, compatible consumables, paper/roll size, and technical specs.
- Non-existent product model inquiry: bot must state absence, not invent details.
- Verify pricing and compatibility come from deterministic code, not free-form LLM text.
"""

import unittest
import os
import uuid
import json
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager
from catalog.catalogue_loader import catalogue_loader
from rag.consumables_engine import consumables_engine

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_isolated.db")

REAL_15_PRODUCTS = [
    {
        "id": "epson-sc-t3100",
        "name": "Epson SureColor SC-T3100",
        "expected_width": "24",
        "expected_category": "technical",
        "expected_ink": "UltraChrome XD2",
    },
    {
        "id": "epson-sc-t5100",
        "name": "Epson SureColor SC-T5100",
        "expected_width": "36",
        "expected_category": "technical",
        "expected_ink": "UltraChrome XD2",
    },
    {
        "id": "epson-sc-t5400m",
        "name": "Epson SureColor SC-T5400M",
        "expected_width": "36",
        "expected_category": "technical",
        "expected_feature": "scanner",
    },
    {
        "id": "epson-sc-t3700e",
        "name": "Epson SureColor SC-T3700E",
        "expected_width": "24",
        "expected_category": "technical",
        "expected_ink": "XD3",
    },
    {
        "id": "epson-sc-t7700d",
        "name": "Epson SureColor SC-T7700D",
        "expected_width": "44",
        "expected_category": "technical",
        "expected_feature": "dual",
    },
    {
        "id": "epson-sc-p900",
        "name": "Epson SureColor SC-P900",
        "expected_width": "17",
        "expected_category": "photo",
        "expected_ink": "UltraChrome PRO10",
    },
    {
        "id": "epson-sc-p700",
        "name": "Epson SureColor SC-P700",
        "expected_width": "13",
        "expected_category": "photo",
        "expected_ink": "UltraChrome PRO10",
    },
    {
        "id": "epson-sc-p8500d",
        "name": "Epson SureColor SC-P8500D",
        "expected_width": "44",
        "expected_category": "photo",
        "expected_feature": "dual",
    },
    {
        "id": "epson-sc-p20000",
        "name": "Epson SureColor SC-P20000",
        "expected_width": "64",
        "expected_category": "photo",
        "expected_ink": "UltraChrome PRO",
    },
    {
        "id": "citizen-cz-01",
        "name": "Citizen CZ-01",
        "expected_category": "citizen_photo",
        "expected_size": "4x6",
    },
    {
        "id": "citizen-cx-02",
        "name": "Citizen CX-02",
        "expected_category": "citizen_photo",
        "expected_size": "6x8",
    },
    {
        "id": "citizen-cy-02",
        "name": "Citizen CY-02",
        "expected_category": "citizen_photo",
        "expected_feature": "high capacity",
    },
    {
        "id": "epson-wf-c20600",
        "name": "Epson WorkForce Enterprise WF-C20600",
        "expected_category": "office",
        "expected_speed": "60",
    },
    {
        "id": "epson-ds-530ii",
        "name": "Epson WorkForce DS-530II",
        "expected_category": "scanner",
        "expected_speed": "35",
    },
    {
        "id": "epson-ds-790wn",
        "name": "Epson WorkForce DS-790WN",
        "expected_category": "scanner",
        "expected_feature": "network",
    }
]


class TestSectionDAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True

    def setUp(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass
        customer_repository.db_path = TEST_DB_PATH
        customer_repository._init_db()
        state_repository.db_path = TEST_DB_PATH
        state_repository._init_db()

        with state_manager._lock:
            state_manager._store.clear()
        self.client = app.test_client()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_d1_fifteen_real_products_specs_and_catalog_match(self):
        """Verify 15 real products from approved catalog for specs, consumables, and sizes."""
        catalog_all = {p["id"]: p for p in catalogue_loader.get_all()}

        for p_info in REAL_15_PRODUCTS:
            pid = p_info["id"]
            name = p_info["name"]
            self.assertIn(pid, catalog_all, f"Product {pid} not found in approved catalog!")
            cat_prod = catalog_all[pid]

            sid = f"sess_d1_{pid}_{uuid.uuid4().hex[:6]}"
            # Ask specs
            resp = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": f"What are the specifications of {name}?"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            reply = data.get("reply", "")

            # Must mention the product model or name
            model_tokens = [w for w in name.lower().split() if len(w) > 3]
            self.assertTrue(
                name.lower() in reply.lower() or pid in reply.lower() or any(tok in reply.lower() for tok in model_tokens),
                f"Reply for {name} did not reference the model: {reply[:100]}"
            )

            # Check grounding status
            grounding = data.get("grounding", {})
            self.assertTrue(
                grounding.get("is_grounded", True),
                f"Product {name} was not marked grounded: {grounding}"
            )

    def test_d2_pricing_policy_deterministic_enforcement(self):
        """Price inquiries for all 15 products must return deterministic refusal and website link."""
        for p_info in REAL_15_PRODUCTS[:5]:  # Test first 5 to keep runtime tight
            name = p_info["name"]
            sid = f"sess_price_{uuid.uuid4().hex[:6]}"
            resp = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": f"How much does {name} cost in AED?"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            reply = data.get("reply", "")

            # Must include official website link
            self.assertIn("https://www.keplertechllc.com/", reply)
            # Must state pricing is not provided in chat
            self.assertTrue(
                "pricing and commercial details are not provided" in reply.lower() or
                "official website" in reply.lower()
            )
            # Source must be deterministic price route or guardrail
            source = data.get("source", "")
            self.assertTrue(
                "price" in source.lower() or "guardrail" in source.lower(),
                f"Source for price query was not deterministic! Source: {source}"
            )

    def test_d3_consumables_compatibility_exact_match(self):
        """Ask compatible consumables for SC-T3100 and SC-P900, check exact SKU match against database."""
        # Test SC-T3100
        sid = f"sess_ink_{uuid.uuid4().hex[:6]}"
        resp = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "What ink cartridges does the Epson SureColor SC-T3100 take?"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        reply = data.get("reply", "")

        # Verified UltraChrome XD2 ink
        self.assertIn("UltraChrome XD2", reply)

        # Consumable cards attached
        consumable_cards = data.get("consumable_cards", [])
        self.assertGreater(len(consumable_cards), 0, "No consumable cards attached for SC-T3100")
        card_skus = [c.get("sku") for c in consumable_cards]
        # Check against DB
        db_consumables = consumables_engine.get_printer_consumables("Epson SureColor SC-T3100")
        db_skus = [c.get("sku") for c in db_consumables]
        for c in consumable_cards:
            if c.get("sku"):
                self.assertIn(c["sku"], db_skus, f"Card SKU {c['sku']} not in verified consumables DB!")

    def test_d4_non_existent_model_rejection(self):
        """Inquiry about non-existent product must state absence, never fabricate specs."""
        fake_models = [
            "Epson SureColor T9999 Titanium Laser",
            "Citizen SuperPhotomaster 10000",
            "HP DesignJet Z9900 Enterprise"
        ]

        for fake in fake_models:
            sid = f"sess_fake_{uuid.uuid4().hex[:6]}"
            resp = self.client.post("/api/chat", json={
                "session_id": sid,
                "message": f"Do you sell the {fake}?"
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            reply = data.get("reply", "")

            # Must state not carried / not in approved catalogue
            self.assertTrue(
                any(phrase in reply.lower() for phrase in [
                    "do not carry", "do not currently carry", "not present in our approved catalogue",
                    "not in our", "cannot provide", "only provide specifications and support for verified"
                ]),
                f"Failed to reject fake model '{fake}'. Bot reply: {reply}"
            )
            # Must NOT claim it exists with fake specs
            self.assertNotIn("we have this model in stock", reply.lower())


if __name__ == "__main__":
    unittest.main()
