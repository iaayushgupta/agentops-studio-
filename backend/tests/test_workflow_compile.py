"""
Test 2 — WorkflowCompiler
Covers:
  • Compiling the Payment Triage graph produces an invokable LangGraph app.
  • Routing functions correctly map failure_type enum values.
  • Reviewer score numeric gate (gte 7) routes to the correct branch.
  • Router retry guard (iteration_count ≥ 2 forces the success path).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.runtime.compiler import WorkflowCompiler
from app.seeds.seed_workflows import PAYMENT_TRIAGE_GRAPH


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_workflow(graph: dict):
    """Build a minimal mock Workflow object that WorkflowCompiler.compile() expects."""
    wf = MagicMock()
    wf.graph_json = graph
    return wf


# ── Compilation smoke test ─────────────────────────────────────────────────────

async def test_compile_payment_triage_succeeds():
    """compile() returns a non-None object with an ainvoke method."""
    wf = _make_workflow(PAYMENT_TRIAGE_GRAPH)
    compiler = WorkflowCompiler()
    compiled = await compiler.compile(wf)
    assert compiled is not None
    assert hasattr(compiled, "ainvoke"), "Compiled graph must expose ainvoke()"


async def test_compile_minimal_graph():
    """A minimal start → agent → end graph compiles without error."""
    minimal_graph = {
        "nodes": [
            {"id": "start",    "type": "start", "data": {"label": "Start"}},
            {"id": "my_agent", "type": "agent", "data": {"agent": "intake_agent", "label": "Test"}},
            {"id": "end",      "type": "end",   "data": {"label": "End"}},
        ],
        "edges": [
            {"id": "e1", "source": "start",    "target": "my_agent"},
            {"id": "e2", "source": "my_agent", "target": "end"},
        ],
    }
    wf = _make_workflow(minimal_graph)
    compiler = WorkflowCompiler()
    compiled = await compiler.compile(wf)
    assert compiled is not None


# ── Router unit tests (no LLM, no DB) ─────────────────────────────────────────

def _find_node(graph: dict, node_id: str) -> dict:
    for n in graph["nodes"]:
        if n["id"] == node_id:
            return n
    raise KeyError(f"Node '{node_id}' not found")


def test_failure_type_router_gateway_error_routes_to_resolution():
    """failure_type=gateway_error → resolution (exact-match in cases dict)."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_failure")
    router = WorkflowCompiler()._build_router(cond_node)
    result = router({"failure_type": "gateway_error", "iteration_count": 0})
    assert result == "resolution"


def test_failure_type_router_insufficient_funds_routes_to_resolution():
    """failure_type=insufficient_funds → resolution."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_failure")
    router = WorkflowCompiler()._build_router(cond_node)
    assert router({"failure_type": "insufficient_funds", "iteration_count": 0}) == "resolution"


def test_failure_type_router_unknown_falls_to_default_escalation():
    """failure_type=fraud_block → not in specific cases → default → escalation."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_failure")
    router = WorkflowCompiler()._build_router(cond_node)
    result = router({"failure_type": "fraud_block", "iteration_count": 0})
    assert result == "escalation"


def test_failure_type_router_case_insensitive():
    """Router comparison is case-insensitive per BUG 4 fix."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_failure")
    router = WorkflowCompiler()._build_router(cond_node)
    assert router({"failure_type": "GATEWAY_ERROR", "iteration_count": 0}) == "resolution"


def test_score_router_passes_when_score_gte_7():
    """reviewer_score=8 with operator=gte threshold=7 → true → telegram_response."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_score")
    router = WorkflowCompiler()._build_router(cond_node)
    result = router({"reviewer_score": 8.0, "iteration_count": 1})
    assert result == "telegram_response"


def test_score_router_fails_when_score_lt_7():
    """reviewer_score=5 → false → reviewer_retry."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_score")
    router = WorkflowCompiler()._build_router(cond_node)
    result = router({"reviewer_score": 5.0, "iteration_count": 1})
    assert result == "reviewer_retry"


def test_score_router_boundary_at_7():
    """reviewer_score=7 exactly → passes (gte 7 is True)."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_score")
    router = WorkflowCompiler()._build_router(cond_node)
    assert router({"reviewer_score": 7.0, "iteration_count": 1}) == "telegram_response"


def test_reviewer_retry_guard_forces_success_at_iteration_2():
    """When iteration_count ≥ 2 the guard forces the 'true' (success) path."""
    cond_node = _find_node(PAYMENT_TRIAGE_GRAPH, "cond_score")
    router = WorkflowCompiler()._build_router(cond_node)
    # Score is low (would normally route to retry), but iteration_count=2 → force success
    result = router({"reviewer_score": 3.0, "iteration_count": 2})
    assert result == "telegram_response"
