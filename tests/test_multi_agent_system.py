"""
Unit Tests for the 4-Agent Conversational AI Architecture.
Verifies:
  1. Agent registry & metadata (Receptionist, Product Specialist, Technical RAG, Sales Lead).
  2. SQLite Lead Repository operations (save_lead, get_leads).
  3. Dynamic agent dispatch and theme color metadata from Orchestrator.
  4. Commercial lead extraction and persistence trigger.
  5. Flask /api/agents and /api/leads endpoints.
"""

import unittest
import tempfile
import os
from persistence.lead_repository import LeadRepository
from agents import (
    receptionist_agent,
    product_catalog_agent,
    technical_rag_agent,
    sales_lead_agent,
    list_agent_metadata,
    get_agent_by_id,
)
from domain.conversation_state import ConversationState
from domain.conversation_types import LLMUnderstanding, Intent
from agent.orchestrator import orchestrator
from app import app


class TestMultiAgentSystem(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_agent_registry_and_metadata(self):
        """Verify all 4 sub-agents are registered with distinct colors and badges."""
        agents = list_agent_metadata()
        self.assertEqual(len(agents), 4)

        agent_map = {a["id"]: a for a in agents}
        
        # Agent 1: Front Desk / Receptionist
        self.assertIn("receptionist", agent_map)
        self.assertEqual(agent_map["receptionist"]["theme_color"], "#10b981")
        self.assertIn("Front Desk", agent_map["receptionist"]["badge"])

        # Agent 2: Product & Catalog Specialist
        self.assertIn("product_specialist", agent_map)
        self.assertEqual(agent_map["product_specialist"]["theme_color"], "#1877f2")
        self.assertIn("Product Specialist", agent_map["product_specialist"]["badge"])

        # Agent 3: Technical RAG & Comparison
        self.assertIn("technical_rag", agent_map)
        self.assertEqual(agent_map["technical_rag"]["theme_color"], "#8b5cf6")
        self.assertIn("Tech & Comparison", agent_map["technical_rag"]["badge"])

        # Agent 4: Sales & Lead Generation
        self.assertIn("sales_lead", agent_map)
        self.assertEqual(agent_map["sales_lead"]["theme_color"], "#f59e0b")
        self.assertIn("Sales & Quotes", agent_map["sales_lead"]["badge"])

    def test_lead_repository_sqlite(self):
        """Verify LeadRepository saves and retrieves commercial leads."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            repo = LeadRepository(db_path=tmp.name)
            lead_id = repo.save_lead(
                session_id="test-session-123",
                customer_name="Ahmed Al Maktoum",
                company="Gulf Printing LLC",
                email="ahmed@gulfprinting.ae",
                phone="+971501234567",
                product_interest="Epson SureColor SC-T5100",
                notes="Requires 2 units with on-site installation.",
            )
            self.assertIsNotNone(lead_id)
            self.assertGreater(lead_id, 0)

            leads = repo.get_leads(limit=10)
            self.assertEqual(len(leads), 1)
            self.assertEqual(leads[0]["customer_name"], "Ahmed Al Maktoum")
            self.assertEqual(leads[0]["email"], "ahmed@gulfprinting.ae")
            self.assertEqual(leads[0]["company"], "Gulf Printing LLC")

    def test_sales_lead_agent_extraction_and_turn(self):
        """Verify SalesLeadAgent extracts email and phone numbers and persists lead."""
        contacts = sales_lead_agent.extract_contact_info(
            "My name is John Doe from Apex Studio. You can email me at john@apex.com or call +971551234567."
        )
        self.assertEqual(contacts["email"], "john@apex.com")
        self.assertIn("+971551234567", contacts["phone"])
        self.assertEqual(contacts["company"], "Apex Studio")
        self.assertEqual(contacts["name"], "John Doe")

        # Test turn execution
        state = ConversationState(session_id="lead-test-sess")
        res = sales_lead_agent.handle_turn(
            raw_message="My name is John Doe, email john@apex.com, please send a quote for SC-T3100.",
            normalized_message="my name is john doe email john@apex.com please send a quote for sc-t3100",
            understanding=None,
            state=state,
            session_id="lead-test-sess",
        )
        self.assertIn("commercial sales team", res.reply)
        self.assertIn("john@apex.com", res.reply)
        self.assertEqual(res.source, "agent:sales_lead:lead_captured")

    def test_orchestrator_agent_switching(self):
        """Verify orchestrator dynamically switches between the 4 sub-agents."""
        state = ConversationState(session_id="switching-test")

        # Turn 1: Greeting -> Agent 1 (Receptionist)
        t1 = orchestrator.process_turn(
            raw_message="Hello!",
            session_id="switching-test",
            history=[],
            state=state,
        )
        self.assertEqual(t1["active_agent"]["id"], "receptionist")
        self.assertEqual(t1["active_agent"]["theme_color"], "#10b981")

        # Turn 2: Exact Product Lookup -> Agent 2 (Product Specialist)
        t2 = orchestrator.process_turn(
            raw_message="Show me the Epson SureColor SC-T3100",
            session_id="switching-test",
            history=[],
            state=state,
        )
        self.assertEqual(t2["active_agent"]["id"], "product_specialist")
        self.assertEqual(t2["active_agent"]["theme_color"], "#1877f2")

        # Turn 3: Technical Comparison -> Agent 3 (Technical RAG)
        t3 = orchestrator.process_turn(
            raw_message="Compare Epson SureColor T3100 vs T5100",
            session_id="switching-test",
            history=[],
            state=state,
        )
        self.assertEqual(t3["active_agent"]["id"], "technical_rag")
        self.assertEqual(t3["active_agent"]["theme_color"], "#8b5cf6")

        # Turn 4: Discount inquiry & contact submission -> Commercial Guardrail Policy (Receptionist + DISCOUNT_REFUSAL)
        t4 = orchestrator.process_turn(
            raw_message="Can I get a discount on the T3100? My email is buyer@emiratesprint.ae",
            session_id="switching-test",
            history=[],
            state=state,
        )
        self.assertEqual(t4["active_agent"]["id"], "receptionist")
        self.assertIn("official website", t4["reply"])

    def test_api_agents_and_leads_endpoints(self):
        """Verify /api/agents and /api/leads return valid JSON responses."""
        # /api/agents
        res_agents = self.app.get("/api/agents")
        self.assertEqual(res_agents.status_code, 200)
        data_agents = res_agents.get_json()
        self.assertTrue(data_agents["success"])
        self.assertEqual(len(data_agents["agents"]), 4)

        # /api/leads
        res_leads = self.app.get("/api/leads")
        self.assertEqual(res_leads.status_code, 200)
        data_leads = res_leads.get_json()
        self.assertTrue(data_leads["success"])
        self.assertIsInstance(data_leads["leads"], list)


if __name__ == "__main__":
    unittest.main()
