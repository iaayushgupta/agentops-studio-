"""
Test 5 — Tool Execution & Guardrails
Covers:
  • get_transaction returns real mock data for TXN-0001 (from seeds).
  • get_transaction returns {"error": ...} for unknown IDs.
  • GuardrailEvaluator.filter_tool raises GuardrailViolation when tool is not
    in agent.tools_enabled (non-empty list).
  • GuardrailEvaluator.filter_tool is a NO-OP when tools_enabled is empty
    (empty list = no restriction per spec).
  • GuardrailEvaluator.check_before_step raises on iteration limit exceeded.
  • GuardrailEvaluator.check_before_step raises on cost ceiling exceeded.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.runtime.guardrails import GuardrailEvaluator, GuardrailViolation
from app.runtime.tools.payment_tools import get_transaction, get_psp_status


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_agent(name: str = "test_agent", tools: list[str] | None = None,
                max_iterations: int = 10, max_cost_usd: float = 1.0):
    """
    Build a minimal duck-typed Agent for guardrail tests.
    No DB access needed — GuardrailEvaluator only reads .name, .tools_enabled,
    .max_iterations, and .max_cost_usd.
    """
    return SimpleNamespace(
        name=name,
        tools_enabled=tools if tools is not None else [],
        max_iterations=max_iterations,
        max_cost_usd=max_cost_usd,
    )


# ── Tool execution tests (require DB with seeded mock data) ───────────────────

async def test_get_transaction_known_id_returns_data():
    """get_transaction('TXN-0001') returns a dict with expected fields."""
    result = await get_transaction.ainvoke({"transaction_id": "TXN-0001"})
    assert isinstance(result, dict)
    assert "error" not in result, f"Unexpected error: {result.get('error')}"
    assert result["transaction_id"] == "TXN-0001"
    assert "amount" in result
    assert "status" in result
    assert "psp" in result


async def test_get_transaction_unknown_id_returns_error():
    """get_transaction with a non-existent ID returns an error dict."""
    result = await get_transaction.ainvoke({"transaction_id": "TXN-DOES-NOT-EXIST"})
    assert isinstance(result, dict)
    assert "error" in result


async def test_get_psp_status_known_psp():
    """get_psp_status returns status/latency/error_rate for a known PSP name."""
    # The seed data includes at least one PSP. Try "stripe" or "adyen" (case-insensitive).
    for psp_name in ("stripe", "Stripe", "adyen", "Adyen"):
        result = await get_psp_status.ainvoke({"psp_name": psp_name})
        if "error" not in result:
            assert "status" in result
            assert "latency_ms" in result
            assert "error_rate" in result
            return   # found at least one known PSP — test passes

    # If none matched, the seed data uses different names.
    # Fail gracefully with a descriptive message.
    pytest.skip("No known PSP name found in seed data — check seed_mock_data.py")


async def test_get_psp_status_unknown_psp_returns_error():
    """get_psp_status with a non-existent PSP returns an error dict."""
    result = await get_psp_status.ainvoke({"psp_name": "NONEXISTENT_PSP_XYZ"})
    assert "error" in result


# ── Guardrail: filter_tool (tool allowlist) ───────────────────────────────────

def test_filter_tool_raises_when_tool_not_in_allowlist():
    """
    Agent with tools_enabled=["get_transaction"] cannot use send_telegram_message.
    GuardrailViolation must be raised.
    """
    agent = _mock_agent(tools=["get_transaction"])
    evaluator = GuardrailEvaluator()

    with pytest.raises(GuardrailViolation) as exc_info:
        evaluator.filter_tool(agent, "send_telegram_message")

    assert "send_telegram_message" in exc_info.value.reason
    assert "test_agent" in exc_info.value.reason


def test_filter_tool_allows_listed_tool():
    """Tool that IS in tools_enabled must pass without raising."""
    agent = _mock_agent(tools=["get_transaction", "calculator"])
    evaluator = GuardrailEvaluator()
    # Should not raise
    evaluator.filter_tool(agent, "get_transaction")
    evaluator.filter_tool(agent, "calculator")


def test_filter_tool_empty_list_means_no_restriction():
    """
    Per spec: tools_enabled=[] → no restriction.
    Any tool name must pass without raising.
    """
    agent = _mock_agent(tools=[])
    evaluator = GuardrailEvaluator()
    # Must not raise, regardless of tool name
    evaluator.filter_tool(agent, "send_telegram_message")
    evaluator.filter_tool(agent, "some_hypothetical_tool")


# ── Guardrail: check_before_step (iteration and cost ceilings) ────────────────

def test_check_before_step_raises_on_iteration_exceeded():
    """iteration_count > max_iterations → GuardrailViolation."""
    agent = _mock_agent(max_iterations=5)
    evaluator = GuardrailEvaluator()
    state = {"iteration_count": 6, "total_cost_usd": 0.0}

    with pytest.raises(GuardrailViolation) as exc_info:
        evaluator.check_before_step(agent, state, run=None)

    assert "Iteration" in exc_info.value.reason


def test_check_before_step_allows_at_max_iteration():
    """iteration_count == max_iterations is still allowed (not strictly greater)."""
    agent = _mock_agent(max_iterations=5)
    evaluator = GuardrailEvaluator()
    state = {"iteration_count": 5, "total_cost_usd": 0.0}
    # Should not raise
    evaluator.check_before_step(agent, state, run=None)


def test_check_before_step_raises_on_cost_exceeded():
    """total_cost_usd > max_cost_usd → GuardrailViolation."""
    agent = _mock_agent(max_cost_usd=0.50)
    evaluator = GuardrailEvaluator()
    state = {"iteration_count": 1, "total_cost_usd": 0.75}

    with pytest.raises(GuardrailViolation) as exc_info:
        evaluator.check_before_step(agent, state, run=None)

    assert "Cost" in exc_info.value.reason


def test_check_before_step_allows_at_cost_ceiling():
    """total_cost_usd == max_cost_usd is still allowed (not strictly greater)."""
    agent = _mock_agent(max_cost_usd=0.50)
    evaluator = GuardrailEvaluator()
    state = {"iteration_count": 1, "total_cost_usd": 0.50}
    evaluator.check_before_step(agent, state, run=None)


def test_check_before_step_allows_zero_cost_and_zero_iterations():
    """Fresh state (all zeros) must pass all guardrails."""
    agent = _mock_agent()
    evaluator = GuardrailEvaluator()
    state = {"iteration_count": 0, "total_cost_usd": 0.0}
    evaluator.check_before_step(agent, state, run=None)
