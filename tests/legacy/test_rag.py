"""
Unit tests for RAG Retrieval and Product Comparison Engine.
"""

import unittest
from rag.retriever import rag_retriever
from rag.comparison_engine import detect_comparison_request, generate_comparison_response
from app import app


class RagAndComparisonTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_rag_corpus_loaded(self):
        self.assertTrue(len(rag_retriever.products) >= 10)
        self.assertIsNotNone(rag_retriever.vectorizer)

    def test_rag_cad_plotter_retrieval(self):
        results = rag_retriever.retrieve("24-inch A1 technical CAD plotter for blueprints")
        self.assertTrue(len(results) > 0)
        top_product = results[0]
        self.assertIn("T3100", top_product["name"])
        self.assertIn("24-inch", top_product["width"])

    def test_rag_photo_printer_retrieval(self):
        results = rag_retriever.retrieve("17-inch professional exhibition photo printer with 10 colors")
        self.assertTrue(len(results) > 0)
        top_product = results[0]
        self.assertIn("P900", top_product["name"])

    def test_product_comparison_engine(self):
        comp = detect_comparison_request("compare Epson SureColor T3100 vs T5100", {"intent": "PRODUCT_COMPARISON"})
        self.assertTrue(comp["is_comparison"])
        self.assertEqual(len(comp["models"]), 2)

        res = generate_comparison_response(comp["models"][0], comp["models"][1], "compare Epson SureColor T3100 vs T5100")
        self.assertIn("T3100", res["text"])
        self.assertIn("T5100", res["text"])
        # Section D: Must ask clarifying question and not leak price
        self.assertIn("?", res["text"])
        self.assertNotIn("AED", res["text"])
        self.assertNotIn("$", res["text"])

    def test_api_chat_returns_retrieved_sources(self):
        resp = self.client.post("/api/chat", json={
            "message": "What are the specifications of the Citizen CX-02 dye-sub printer?",
            "session_id": "test-rag-session"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("retrieved_sources", data)
        self.assertTrue(len(data["retrieved_sources"]) > 0)
        top_source = data["retrieved_sources"][0]
        self.assertIn("Citizen", top_source["name"])
        self.assertIn("url", top_source)


if __name__ == "__main__":
    unittest.main()
