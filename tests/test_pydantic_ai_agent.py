"""
Unit and Integration Tests for Pydantic-AI Specialist Agent & Tool Suite.
Validates:
  1. Utility tools: get_current_time, calculate, save_note, read_notes.
  2. Enterprise catalog tools: search_catalog, get_product_specs, get_compatible_consumables.
  3. Pydantic-AI Agent initialization and model resolution.
  4. Specialist Agent registration in agents.SPECIALIST_AGENTS.
"""

import os
import pytest
from datetime import datetime

import agents
from agents.pydantic_ai_agent import (
    get_current_time,
    calculate,
    save_note,
    read_notes,
    search_catalog,
    get_product_specs,
    get_compatible_consumables,
    pydantic_ai_specialist,
    pydantic_agent_instance,
    resolve_available_model,
)


def test_time_tool():
    res = get_current_time()
    assert isinstance(res, str)
    assert any(day in res for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])


def test_calculate_tool():
    assert calculate("23 * 7 + 1") == "162"
    assert calculate("100 / 4") == "25.0"
    assert "Error:" in calculate("import os")


def test_notes_tool(tmp_path):
    save_note("Unit test note alpha")
    notes = read_notes()
    assert "Unit test note alpha" in notes


def test_catalog_tools():
    # 1. Search
    res_search = search_catalog("Citizen CZ-01")
    assert "Citizen CZ-01" in res_search

    # 2. Specs
    res_specs = get_product_specs("citizen-cz-01")
    assert "Citizen CZ-01" in res_specs

    # 3. Consumables
    res_cons = get_compatible_consumables("SC-F500")
    assert isinstance(res_cons, str)


def test_agent_registration():
    all_agents = agents.list_agent_metadata()
    agent_ids = [a["id"] for a in all_agents]
    assert "pydantic_ai_agent" in agent_ids
    specialist = agents.get_agent_by_id("pydantic_ai_agent")
    assert specialist is not None
    assert specialist.name == "Pydantic-AI Tool Calling Specialist"


def test_model_resolution():
    model_name = resolve_available_model("qwen3.5:2b")
    assert model_name in ["qwen2.5:latest", "llama3.2:1b", "qwen2.5:0.5b", "qwen3:8b", "qwen2.5:32b", "qwen3.5:2b"]
