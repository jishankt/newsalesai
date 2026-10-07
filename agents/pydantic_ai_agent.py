"""
Pydantic-AI Powered Specialist Agent for SalesAI & Local Assistant Tasks.
Integrates Pydantic-AI with local Ollama models and dynamic tool calling.

Supports:
  1. Personal assistant utility tools (time, calculation, notes persistence)
  2. Enterprise SalesAI catalog tools (search_catalog, get_product_specs, get_compatible_consumables, compare_products)
  3. Standalone interactive CLI loop (python agents/pydantic_ai_agent.py)
  4. Integration as a registered SpecialistAgent in the SalesAI orchestrator pipeline
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

# Add project root to sys.path if running as script
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agents.base_agent import BaseSpecialistAgent
from domain.conversation_types import RouteResult, LLMUnderstanding, RouteName
from domain.conversation_state import ConversationState

logger = logging.getLogger("agent.pydantic_ai")

# Configuration & Notes file path
NOTES_FILE = os.path.join(project_root, "data", "notes.txt")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")


def resolve_available_model(preferred_model: str = "qwen3.5:2b") -> str:
    """
    Resolves the best available local Ollama model.
    Falls back gracefully if the requested model (e.g. qwen3.5:2b) is not installed.
    """
    import urllib.request
    try:
        raw_url = OLLAMA_BASE_URL.replace("/v1", "") + "/api/tags"
        req = urllib.request.Request(raw_url, headers={"User-Agent": "SalesAI-PydanticAI"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed_models = [m.get("name", "") for m in data.get("models", [])]
            
            # Check exact or prefix match
            for m in installed_models:
                if preferred_model in m or m in preferred_model:
                    return m
            
            # Check standard fallbacks (prefer fast responsive models for interactive assistant)
            for candidate in ["qwen2.5:latest", "llama3.2:1b", "qwen2.5:0.5b", "qwen3:8b", "qwen2.5:32b", DEFAULT_OLLAMA_MODEL]:
                for m in installed_models:
                    if candidate == m or m == candidate:
                        return m
            for candidate in ["qwen2.5", "llama3.2", "qwen3"]:
                for m in installed_models:
                    if candidate in m:
                        return m
            if installed_models:
                return installed_models[0]
    except Exception as e:
        logger.warning(f"Could not query Ollama tags ({e}); using preferred or default model.")
    
    return DEFAULT_OLLAMA_MODEL


ACTIVE_MODEL_NAME = resolve_available_model(os.getenv("PREFERRED_MODEL", "qwen3.5:2b"))

model = OllamaModel(
    ACTIVE_MODEL_NAME,
    provider=OllamaProvider(base_url=OLLAMA_BASE_URL),
)


# ==========================================
# Tool Definitions (User & Enterprise Tools)
# ==========================================

def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")


def calculate(expression: str) -> str:
    """Evaluate a basic math expression, e.g. '23 * 7 + 1' or '295 / 300'."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "Error: only numbers and + - * / ( ) are allowed."
    try:
        return str(eval(expression))
    except Exception as error:
        return f"Error: {error}"


def save_note(note: str) -> str:
    """Save a short note so it can be recalled later."""
    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    with open(NOTES_FILE, "a", encoding="utf-8") as file:
        file.write(f"- {note}\n")
    return "Note saved."


def read_notes() -> str:
    """Read back all previously saved notes."""
    if not os.path.exists(NOTES_FILE):
        return "No notes saved yet."
    with open(NOTES_FILE, "r", encoding="utf-8") as file:
        return file.read()


def search_catalog(query: str, category: Optional[str] = None) -> str:
    """
    Search Kepler Tech's live catalog for printers, scanners, media, or consumables.
    Returns matched products with specifications and pricing policy details.
    """
    try:
        from catalog.catalogue_loader import catalogue_loader
        q_lower = query.lower()
        matched = []
        for p in catalogue_loader.products:
            p_name = p.get("name", "").lower()
            p_id = p.get("id", "").lower()
            p_cat = p.get("category", "").lower()
            p_brand = p.get("brand", "").lower()
            if any(term in p_name or term in p_id for term in q_lower.split()):
                matched.append(p)
        if not matched:
            from agent.tool_executor import CatalogToolExecutor
            executor = CatalogToolExecutor()
            res = executor._search_catalog(query=query, category=category, limit=3)
            cards = res.get("cards", [])
            if not cards:
                return f"No catalog items found matching '{query}'."
            summary = [f"Found {len(cards)} matching items:"]
            for c in cards:
                summary.append(f"- {c.get('name')} (SKU: {c.get('sku')}): {c.get('price_formatted')}. URL: {c.get('product_url')}")
            return "\n".join(summary)

        summary = [f"Found {len(matched[:4])} matching catalogue items:"]
        for p in matched[:4]:
            summary.append(f"- {p.get('name')} (ID: {p.get('id')}): Category: {p.get('category')}. Speeds/Specs: {p.get('specs', {})}")
        return "\n".join(summary)
    except Exception as e:
        return f"Catalog search error: {e}"


def get_product_specs(product_identifier: str) -> str:
    """
    Retrieve full technical specifications, print resolution, dimensions, and speed for a product SKU or model name.
    """
    try:
        from catalog.catalogue_loader import catalogue_loader
        q_lower = product_identifier.lower().strip()
        matched = None
        for p in catalogue_loader.products:
            if q_lower == p.get("id", "").lower() or q_lower in p.get("name", "").lower() or p.get("name", "").lower() in q_lower:
                matched = p
                break
        if matched:
            return (
                f"Product: {matched.get('name')} (ID: {matched.get('id')})\n"
                f"Category: {matched.get('category')} ({matched.get('subcategory')})\n"
                f"Brand: {matched.get('brand')}\n"
                f"Specs: {json.dumps(matched.get('specs', {}), indent=2)}"
            )

        from agent.tool_executor import CatalogToolExecutor
        executor = CatalogToolExecutor()
        res = executor._get_product_specs(identifier=product_identifier)
        if not res.get("found"):
            return f"Product '{product_identifier}' not found in Kepler catalog."
        card = res.get("card", {})
        specs = res.get("specifications", {})
        return (
            f"Product: {card.get('name')} ({card.get('sku')})\n"
            f"Price: {card.get('price_formatted')}\n"
            f"Specs: {json.dumps(specs, indent=2)}\n"
            f"URL: {card.get('product_url')}"
        )
    except Exception as e:
        return f"Specs fetch error: {e}"


def get_compatible_consumables(printer_identifier: str) -> str:
    """
    Discover genuine inks, maintenance boxes, and media compatible with a given printer model or SKU.
    """
    try:
        from agent.tool_executor import CatalogToolExecutor
        executor = CatalogToolExecutor()
        res = executor._get_compatible_consumables(printer_identifier=printer_identifier, limit=5)
        cards = res.get("cards", [])
        if not cards:
            return f"No verified consumables found for '{printer_identifier}'."
        lines = [f"Consumables for {printer_identifier}:"]
        for c in cards:
            lines.append(f"- {c.get('name')} (SKU: {c.get('sku')}): {c.get('price_formatted')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Consumables error: {e}"


ALL_TOOLS = [
    get_current_time,
    calculate,
    save_note,
    read_notes,
    search_catalog,
    get_product_specs,
    get_compatible_consumables,
]

SYSTEM_INSTRUCTIONS = (
    "You are Kepler Tech SalesAI and intelligent personal assistant running 100% locally with Pydantic-AI. "
    "You assist customers with printing hardware, genuine consumables, running costs, technical specifications, "
    "and personal assistant tasks. Use your tools whenever they can help answer the question accurately without guessing. "
    "Keep your answers short, accurate, and friendly."
)

pydantic_agent_instance = Agent(
    model,
    tools=ALL_TOOLS,
    instructions=SYSTEM_INSTRUCTIONS,
)


class PydanticAiSpecialistAgent(BaseSpecialistAgent):
    """
    SalesAI Specialist Agent powered by Pydantic-AI.
    Can be dispatched to handle complex tool-calling turns within the SalesAI conversational pipeline.
    """
    def __init__(self):
        super().__init__(
            agent_id="pydantic_ai_agent",
            name="Pydantic-AI Tool Calling Specialist",
            role="Dynamic Tool-Calling & Multi-Domain Assistant",
            theme_color="#8b5cf6",
            badge="⚡ Pydantic-AI Specialist",
            icon="fas fa-brain",
        )
        self.agent = pydantic_agent_instance

    def handle_turn(
        self,
        raw_message: str,
        normalized_message: str,
        understanding: Optional[LLMUnderstanding],
        state: ConversationState,
        **kwargs,
    ) -> RouteResult:
        logger.info(f"PydanticAiSpecialistAgent handling: {raw_message[:60]}")
        try:
            res = self.agent.run_sync(raw_message)
            reply_text = str(res.output)
            return RouteResult(
                route=RouteName.CONSULTATIVE,
                reply=reply_text,
                source="agent:pydantic_ai_agent",
                matched_products=[],
            )
        except Exception as e:
            logger.error(f"Pydantic-AI execution failure: {e}", exc_info=True)
            return RouteResult(
                route=RouteName.HELP,
                reply="I'm here to help with your printing equipment, calculations, or catalog queries. How can I assist?",
                source="agent:pydantic_ai_agent:fallback",
            )


pydantic_ai_specialist = PydanticAiSpecialistAgent()


def main():
    """Interactive CLI runner for local personal assistant & tool testing."""
    print("=" * 65)
    print(f"  Pydantic-AI Local Assistant Ready! (Model: {ACTIVE_MODEL_NAME})")
    print("  Type 'quit' or 'exit' to end the session.")
    print("=" * 65 + "\n")
    history = []
    while True:
        try:
            user_input = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if user_input.strip().lower() in ("quit", "exit"):
            break
        if not user_input.strip():
            continue
        try:
            result = pydantic_agent_instance.run_sync(user_input, message_history=history)
            history = result.all_messages()
            print(f"\nAgent: {result.output}\n")
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
