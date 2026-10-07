"""
Test Suite for Investment and Running Cost Inquiries & Recommendations.
"""

import unittest
from domain.conversation_state import ConversationState
from catalog.repository import catalog_repository
from catalog.cost_per_print_calculator import cost_per_print_calculator
from agent.orchestrator import Orchestrator


class TestInvestmentAndRunningCost(unittest.TestCase):

    def setUp(self):
        self.orchestrator = Orchestrator()

    def test_calculator_investment_and_running_cost_comparison(self):
        """Verify build_investment_and_running_cost_comparison includes prices, yields, and breakeven recommendations."""
        cz01 = catalog_repository.get_by_id("citizen-cz-01").to_dict()
        cx02 = catalog_repository.get_by_id("citizen-cx-02").to_dict()

        res = cost_per_print_calculator.build_investment_and_running_cost_comparison([cz01, cx02], print_format="4x6")
        self.assertIn("AED 3,200.00", res)
        self.assertIn("AED 4,385.00", res)
        self.assertIn("AED 0.98", res)
        self.assertIn("AED 0.61", res)
        self.assertIn("Which One Is Best for You?", res)
        self.assertIn("Lowest Initial Investment", res)
        self.assertIn("Lowest Running Cost", res)
        self.assertNotIn("commercial details are not provided in this chat", res.lower())

    def test_single_printer_cost_per_print_has_hardware_price(self):
        """Verify calculate_cost_per_print includes verified hardware investment price and no blanket withholding disclaimer."""
        res = cost_per_print_calculator.calculate_cost_per_print("citizen-cz-01", print_format="4x6", include_hardware_price=True)
        self.assertEqual(res.status, "verified")
        self.assertIn("Hardware Investment", res.explanation)
        self.assertIn("AED 3,200.00", res.explanation)
        self.assertNotIn("commercial details are not provided in this chat", res.explanation.lower())

    def test_orchestrator_multi_turn_investment_recommendation(self):
        """Verify orchestrator returns investment table and decision recommendation without false disclaimer."""
        state = ConversationState(session_id="test_unit_inv_rec")
        cz01 = catalog_repository.get_by_id("citizen-cz-01").to_dict()
        cx02 = catalog_repository.get_by_id("citizen-cx-02").to_dict()
        state.candidate_products = [cz01, cx02]
        state.category = "citizen_photo"

        turn = self.orchestrator.process_turn(
            "which one is best for me. in both investment and running cost?",
            state=state
        )
        reply = turn.get("reply", "")
        self.assertIn("AED 3,200.00", reply)
        self.assertIn("AED 4,385.00", reply)
        self.assertIn("0.98", reply)
        self.assertIn("0.61", reply)
        self.assertIn("Which One Is Best for You?", reply)
        self.assertNotIn("commercial details are not provided in this chat", reply.lower())


if __name__ == "__main__":
    unittest.main()
