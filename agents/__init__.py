"""
Specialist Sub-Agents Package for Kepler Tech Conversational AI.
Exposes the 4 dedicated sub-agents:
  1. ReceptionistAgent (Kepler Concierge)
  2. ProductCatalogAgent (Product & Catalog Specialist)
  3. TechnicalRagAgent (Technical & Comparison Specialist)
  4. SalesLeadAgent (Sales & Quotation Specialist)
"""

from typing import Dict, Any, Optional
from agents.base_agent import BaseSpecialistAgent
from agents.receptionist_agent import ReceptionistAgent, receptionist_agent
from agents.product_catalog_agent import ProductCatalogAgent, product_catalog_agent
from agents.technical_rag_agent import TechnicalRagAgent, technical_rag_agent
from agents.sales_lead_agent import SalesLeadAgent, sales_lead_agent
from agents.pydantic_ai_agent import PydanticAiSpecialistAgent, pydantic_ai_specialist

SPECIALIST_AGENTS: Dict[str, BaseSpecialistAgent] = {
    receptionist_agent.agent_id: receptionist_agent,
    product_catalog_agent.agent_id: product_catalog_agent,
    technical_rag_agent.agent_id: technical_rag_agent,
    sales_lead_agent.agent_id: sales_lead_agent,
    pydantic_ai_specialist.agent_id: pydantic_ai_specialist,
}


def get_agent_by_id(agent_id: str) -> Optional[BaseSpecialistAgent]:
    """Retrieves an agent by its unique identifier."""
    return SPECIALIST_AGENTS.get(agent_id)


def list_agent_metadata() -> list:
    """Returns metadata list of all registered sub-agents."""
    return [agent.get_info() for agent in SPECIALIST_AGENTS.values()]


__all__ = [
    "BaseSpecialistAgent",
    "ReceptionistAgent",
    "receptionist_agent",
    "ProductCatalogAgent",
    "product_catalog_agent",
    "TechnicalRagAgent",
    "technical_rag_agent",
    "SalesLeadAgent",
    "sales_lead_agent",
    "PydanticAiSpecialistAgent",
    "pydantic_ai_specialist",
    "SPECIALIST_AGENTS",
    "get_agent_by_id",
    "list_agent_metadata",
]
