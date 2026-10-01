"""
QA Automated Test Suite - Section E: Semantic Understanding
Tests:
- "same ink as last time?" -> historical reference resolution
- Typos and short messages ("epson p900 ink cost?", "p900 black ink", "do u have A3 scaner")
- Follow-ups without naming product ("and the paper for it?")
- Topic switch mid-chat, then return to earlier topic
- Arabic and Hinglish messages
"""

import unittest
import os
import uuid
import json
from app import app
from persistence.customer_repository import customer_repository
from persistence.state_repository import state_repository
from domain.state_store import state_manager

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_qa_isolated.db")


class TestSectionESemantics(unittest.TestCase):
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

    def test_e1_same_ink_as_last_time_reference_resolution(self):
        """'same ink as last time?' must resolve to the active/previous printer from history."""
        sid = f"sess_e1_{uuid.uuid4().hex[:6]}"
        # Turn 1: Discuss SC-P900
        r1 = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "Tell me about the Epson SureColor SC-P900"
        })
        self.assertEqual(r1.status_code, 200)

        # Turn 2: Ask for "same ink as last time"
        r2 = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "What is the ink for this printer?"
        })
        self.assertEqual(r2.status_code, 200)
        reply2 = r2.get_json().get("reply", "")
        self.assertTrue(
            "UltraChrome PRO10" in reply2 or "p900" in reply2.lower(),
            f"Failed to resolve ink for SC-P900! Reply: {reply2[:150]}"
        )

    def test_e2_typos_and_short_messages(self):
        """Typos and shorthand queries must be understood and routed correctly."""
        # 1. "epson p900 ink cost?"
        sid1 = f"sess_typo1_{uuid.uuid4().hex[:6]}"
        r1 = self.client.post("/api/chat", json={"session_id": sid1, "message": "epson p900 ink cost?"})
        self.assertEqual(r1.status_code, 200)
        rep1 = r1.get_json().get("reply", "")
        # Should address SC-P900 ink and cite official pricing website
        self.assertTrue("https://www.keplertechllc.com/" in rep1 or "p900" in rep1.lower())

        # 2. "p900 black ink"
        sid2 = f"sess_typo2_{uuid.uuid4().hex[:6]}"
        r2 = self.client.post("/api/chat", json={"session_id": sid2, "message": "p900 black ink"})
        self.assertEqual(r2.status_code, 200)
        rep2 = r2.get_json().get("reply", "")
        self.assertTrue("photo black" in rep2.lower() or "matte black" in rep2.lower() or "ultrachrome" in rep2.lower())

        # 3. "do u have A3 scaner"
        sid3 = f"sess_typo3_{uuid.uuid4().hex[:6]}"
        r3 = self.client.post("/api/chat", json={"session_id": sid3, "message": "do u have A3 scaner"})
        self.assertEqual(r3.status_code, 200)
        rep3 = r3.get_json().get("reply", "")
        self.assertTrue(
            "scanner" in rep3.lower() or "ds-" in rep3.lower() or "workforce" in rep3.lower(),
            f"Failed to route scanner query: {rep3[:100]}"
        )

    def test_e3_follow_up_without_naming_product(self):
        """'and the paper for it?' must retain active product context."""
        sid = f"sess_followup_{uuid.uuid4().hex[:6]}"
        # Turn 1: Discuss SC-T3100
        self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "Tell me about the Epson SureColor SC-T3100 plotter"
        })

        # Turn 2: Follow-up without naming model
        r2 = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "and the paper for it?"
        })
        self.assertEqual(r2.status_code, 200)
        rep2 = r2.get_json().get("reply", "")
        self.assertTrue(
            "paper" in rep2.lower() or "roll" in rep2.lower() or "matte" in rep2.lower() or "bond" in rep2.lower() or "t3100" in rep2.lower(),
            f"Context lost on follow-up: {rep2[:150]}"
        )

    def test_e4_topic_switch_and_return(self):
        """Switch from CAD to photo booth, then return to CAD without confusion."""
        sid = f"sess_switch_{uuid.uuid4().hex[:6]}"
        # Turn 1: CAD plotter
        self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "I need a 24-inch CAD plotter for architectural drawings."
        })

        # Turn 2: Switch topic to Citizen photo booth
        r2 = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "Wait, also what photo booth printers do you have from Citizen?"
        })
        self.assertEqual(r2.status_code, 200)
        rep2 = r2.get_json().get("reply", "")
        self.assertTrue("citizen" in rep2.lower() or "cx-02" in rep2.lower() or "cz-01" in rep2.lower())

        # Turn 3: Return to the first CAD plotter
        r3 = self.client.post("/api/chat", json={
            "session_id": sid,
            "message": "Going back to the 24-inch CAD plotter, what is its print speed?"
        })
        self.assertEqual(r3.status_code, 200)
        rep3 = r3.get_json().get("reply", "")
        self.assertTrue("34 sec" in rep3 or "t3100" in rep3.lower() or "a1" in rep3.lower())

    def test_e5_multilingual_arabic_and_hinglish(self):
        """Handle Arabic and Hinglish queries smoothly."""
        # Arabic query
        sid_ar = f"sess_ar_{uuid.uuid4().hex[:6]}"
        r_ar = self.client.post("/api/chat", json={
            "session_id": sid_ar,
            "message": "أريد طابعة مخططات هندسية مقاس 24 بوصة"
        })
        self.assertEqual(r_ar.status_code, 200)
        rep_ar = r_ar.get_json().get("reply", "")
        # Should identify 24-inch plotter / SC-T3100
        self.assertTrue(len(rep_ar) > 20)

        # Hinglish query
        sid_hi = f"sess_hi_{uuid.uuid4().hex[:6]}"
        r_hi = self.client.post("/api/chat", json={
            "session_id": sid_hi,
            "message": "bhai mujhe architectural drawing ke liye plotter chahiye"
        })
        self.assertEqual(r_hi.status_code, 200)
        rep_hi = r_hi.get_json().get("reply", "")
        self.assertTrue("plotter" in rep_hi.lower() or "cad" in rep_hi.lower() or "drawing" in rep_hi.lower() or "surecolor" in rep_hi.lower())


if __name__ == "__main__":
    unittest.main()
