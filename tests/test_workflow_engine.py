"""
Test Suite for Kepler Tech SalesAI n8n-Style Workflow Engine.
Validates:
1. Pipeline node execution and trace observability.
2. Conversational understanding and question vs requirement distinction.
3. Deterministic state updates and negation overwriting ('actually no scanner' -> scanner_required=False).
4. Anaphora and reference resolution ('it', 'first one', 'both').
5. Tool execution and verified evidence binding.
6. Commercial guardrails and discount deflection.
"""

import unittest
from workflow import WorkflowEngine, WorkflowContext
from domain.conversation_state import ConversationState


class TestWorkflowEngine(unittest.TestCase):

    def setUp(self):
        self.engine = WorkflowEngine()

    def test_pipeline_execution_and_trace(self):
        """Verifies all 11 pipeline nodes execute and produce a complete execution trace."""
        res = self.engine.run("Does the SC-T3100 have a scanner?", session_id="test-wf-trace")
        self.assertIn("SC-T3100", res["reply"])
        self.assertIn("trace_summary", res)
        self.assertIn("execution_trace", res)

        trace = res["execution_trace"]
        step_names = [s["step"] for s in trace]
        expected_steps = [
            "NORMALIZE", "LOAD_STATE", "UNDERSTAND", "RESOLVE_CONTEXT",
            "UPDATE_STATE", "DECISION", "EXECUTE_NODE", "VERIFIED_EVIDENCE",
            "RESPONSE_AI", "VALIDATION", "SAVE_STATE"
        ]
        for exp in expected_steps:
            self.assertIn(exp, step_names, f"Expected step {exp} missing from trace")

    def test_question_does_not_force_requirement(self):
        """'Does it have a scanner?' must NOT be treated as a mandatory scanner requirement."""
        state = ConversationState(session_id="test-wf-q-vs-req")
        self.engine.run("Does the SC-T3100 have a scanner?", session_id="test-wf-q-vs-req", state=state)
        # Should not set scanner_required = True
        self.assertFalse(state.requirements.get("scanner_required", False))

    def test_negation_overwrites_scanner_requirement(self):
        """'Actually, no scanner needed' must strictly overwrite scanner_required to False."""
        state = ConversationState(session_id="test-wf-negation")
        state.requirements["scanner_required"] = True
        self.assertTrue(state.requirements["scanner_required"])

        self.engine.run("Actually, no scanner needed", session_id="test-wf-negation", state=state)
        self.assertFalse(state.requirements["scanner_required"])

    def test_correction_overwrites_width(self):
        """'Actually I need 36 inch' must overwrite 24-inch to 36-inch."""
        state = ConversationState(session_id="test-wf-width-corr")
        state.requirements["print_width"] = 24
        state.requirements["paper_size"] = "A1"

        self.engine.run("Actually I need 36 inch A0 plotter", session_id="test-wf-width-corr", state=state)
        self.assertEqual(state.requirements.get("print_width"), 36)
        self.assertEqual(state.requirements.get("paper_size"), "A0")

    def test_reference_resolution_anaphora(self):
        """Turn 1 introduces SC-P900; Turn 2 asks 'What inks does it use?' using pronoun 'it'."""
        state = ConversationState(session_id="test-wf-anaphora")
        res1 = self.engine.run("Tell me about Epson SC-P900", session_id="test-wf-anaphora", state=state)
        self.assertIn("C11CH37401", state.displayed_product_ids)

        res2 = self.engine.run("What inks does it use?", session_id="test-wf-anaphora", state=state)
        self.assertIn("UltraChrome PRO10", res2["reply"])
        trace2 = res2["execution_trace"]
        resolve_step = next(s for s in trace2 if s["step"] == "RESOLVE_CONTEXT")
        self.assertIn("Resolved 1 product reference", resolve_step["summary"])

    def test_reference_resolution_ordinal(self):
        """Turn 1 shows two CAD plotters; Turn 2 asks about 'the second one'."""
        state = ConversationState(session_id="test-wf-ordinal")
        state.displayed_product_ids = ["epson-t3100", "epson-t5100"]

        res = self.engine.run("Tell me the specs for the second one", session_id="test-wf-ordinal", state=state)
        trace = res["execution_trace"]
        resolve_step = next(s for s in trace if s["step"] == "RESOLVE_CONTEXT")
        self.assertIn("epson-t5100", resolve_step["details"]["target_products"])

    def test_commercial_guardrail_discount_deflection(self):
        """Requests for discounts must be deflected with the commercial policy message."""
        res = self.engine.run("Can you give me a 20% discount on this plotter?", session_id="test-wf-discount")
        self.assertEqual(res["source"], "guardrail:discount_refusal")
        self.assertIn("discount", res["reply"].lower())
        self.assertEqual(len(res["cards"]), 0)

    def test_consumables_replenishment_route(self):
        """Inquiry for inks of SC-T3100 must activate the consumables route and bind genuine consumables."""
        res = self.engine.run("Inks for SC-T3100", session_id="test-wf-cons")
        self.assertEqual(res["active_agent"], "Product & Catalog Specialist")
        self.assertTrue(
            "UltraChrome" in res["reply"] or "T40" in res["reply"] or "C13T40" in res["reply"] or "genuine" in res["reply"]
        )

    def test_orchestrator_delegation_to_workflow(self):
        """Orchestrator.execute_workflow must invoke the workflow engine and return trace."""
        from agent.orchestrator import orchestrator
        res = orchestrator.execute_workflow("Tell me about SC-P900", session_id="test-orch-wf")
        self.assertIn("execution_trace", res)
        self.assertTrue(len(res["execution_trace"]) >= 10)
        self.assertIn("reply", res)

    def test_flask_workflow_endpoint(self):
        """Flask endpoint /api/workflow/run must return status 200 and full trace."""
        from app import app
        with app.test_client() as client:
            resp = client.post("/api/workflow/run", json={"message": "I need a 24 inch CAD plotter", "session_id": "test-api-wf"})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIn("execution_trace", data)
            self.assertIn("ascii_trace", data)
            self.assertIn("reply", data)

    def test_product_card_sent_only_once_on_followup(self):
        """Card is sent when product is introduced, but suppressed on follow-up spec queries."""
        from agent.orchestrator import orchestrator
        state = ConversationState(session_id="test-card-once")

        # Turn 1: Product introduced -> card is sent
        t1 = orchestrator.process_turn("Tell me about SC-F100", session_id="test-card-once", state=state)
        self.assertEqual(len(t1["product_cards"]), 1)
        self.assertIn("epson-sc-f100", state.displayed_product_ids)

        # Turn 2: Follow-up spec question "what is the print speed" -> NO repeat card!
        t2 = orchestrator.process_turn("what is the print speed", session_id="test-card-once", state=state)
        self.assertIn("65 sec", t2["reply"].lower())
        self.assertEqual(len(t2["product_cards"]), 0, "Card should not be sent again on follow-up spec question")

        # Turn 3: Follow-up spec question "does it have wifi" -> NO repeat card!
        t3 = orchestrator.process_turn("does it have wifi", session_id="test-card-once", state=state)
        self.assertEqual(len(t3["product_cards"]), 0, "Card should not be sent again on wifi question")

        # Turn 4: Explicit request "show product card again" -> card is re-displayed!
        t4 = orchestrator.process_turn("show product card again", session_id="test-card-once", state=state)
        self.assertEqual(len(t4["product_cards"]), 1, "Card should be displayed when explicitly requested")


if __name__ == "__main__":
    unittest.main()
