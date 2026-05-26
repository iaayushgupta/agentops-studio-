"""WorkflowCompiler — converts a React Flow graph_json DAG into a LangGraph StateGraph.

Architecture
------------
compile(workflow) → compiled LangGraph app (ainvoke-able)

Node types in graph_json
  'start'     → entry-point marker; its outgoing edge target becomes the LG entry point
  'agent'     → async closure that runs an LLM + tool loop; maps to a real LG node
  'condition' → pure routing function; NOT a LG node, wired as conditional edges
  'end'       → terminal marker; maps to LangGraph END constant

Checkpointing
  Tries AsyncPostgresSaver (langgraph-checkpoint-postgres + psycopg).
  Falls back to MemorySaver if the package is not installed or connection fails.
  Rebuild the Docker image after adding psycopg[binary] to enable Postgres checkpoints.
"""
from __future__ import annotations

import json
import logging
import operator
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from sqlalchemy import select, text

from app.config import settings
from app.db.models import Agent, Message, MessageRole, RunStep, StepStatus, TokenUsage
from app.db.session import AsyncSessionLocal
from app.runtime.guardrails import GuardrailEvaluator, GuardrailViolation
from app.runtime.llm import get_llm
from app.runtime.tools import TOOL_REGISTRY
from app.services.observability_service import (
    EVT_GUARDRAIL_VIOLATED,
    EVT_STEP_COMPLETED,
    EVT_STEP_STARTED,
    EVT_TOOL_CALLED,
    ObservabilityService,
)

logger = logging.getLogger(__name__)

_guardrails = GuardrailEvaluator()


# ── WorkflowState ──────────────────────────────────────────────────────────────

class WorkflowState(TypedDict):
    run_id: str
    messages: Annotated[list, operator.add]   # reducer: append
    current_output: dict
    iteration_count: int
    reviewer_score: float | None
    failure_type: str | None
    final_response: str | None
    trigger_payload: dict
    total_cost_usd: float                     # running cost (free tier → always 0)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_tools_for_agent(agent: Agent) -> list:
    """Return tool objects for every name in agent.tools_enabled that exists in TOOL_REGISTRY."""
    return [TOOL_REGISTRY[t] for t in (agent.tools_enabled or []) if t in TOOL_REGISTRY]


def _parse_json(content: str) -> dict:
    """
    Extract a JSON dict from an LLM response.

    Strategy (applied in order):
      1. Strip markdown fences (```json … ``` or ``` … ```), then try direct parse.
      2. Try the raw content as-is.
      3. Scan right-to-left for the LAST valid JSON object using brace counting.
         This handles the common case where the LLM echoes a template, then outputs
         the real answer — e.g.:
           "Here is the format: {...template...}  Here is my answer: {...real...}"
         The greedy regex \{[\s\S]*\} would span both objects and fail; the rightmost
         scan finds the second (real) object correctly.
      4. Last resort: return {"raw_response": content} — never raises.
    """
    # ── 1. Strip fences ───────────────────────────────────────────────────────
    stripped = content
    for pattern in (r"```json\s*([\s\S]*?)```", r"```\s*([\s\S]*?)```"):
        m = re.search(pattern, stripped)
        if m:
            stripped = m.group(1).strip()
            break

    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # ── 2. Raw content direct parse ───────────────────────────────────────────
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # ── 3. Rightmost valid JSON object (brace-count scan, right → left) ──────
    end_pos = len(content)
    while end_pos > 0:
        close = content.rfind("}", 0, end_pos)
        if close == -1:
            break
        # Walk leftward to find the matching opening brace
        depth = 0
        start = -1
        for i in range(close, -1, -1):
            if content[i] == "}":
                depth += 1
            elif content[i] == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start == -1:
            end_pos = close
            continue
        try:
            result = json.loads(content[start : close + 1])
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        end_pos = close  # try the next } going leftward

    return {"raw_response": content}


def _eval_op(op_str: str, value: Any, threshold: Any) -> bool:
    """Evaluate a binary comparison operator string."""
    ops: dict[str, Callable] = {
        "eq":     lambda a, b: a == b,
        "neq":    lambda a, b: a != b,
        "gt":     lambda a, b: a > b,
        "gte":    lambda a, b: a >= b,
        "lt":     lambda a, b: a < b,
        "lte":    lambda a, b: a <= b,
        "in":     lambda a, b: (
            str(a).upper() in [str(x).upper() for x in b]
            if hasattr(b, "__iter__") and not isinstance(b, str) else a in b
        ),
        "not_in": lambda a, b: (
            str(a).upper() not in [str(x).upper() for x in b]
            if hasattr(b, "__iter__") and not isinstance(b, str) else a not in b
        ),
    }
    fn = ops.get(op_str)
    if fn is None:
        raise ValueError(f"Unknown condition operator: '{op_str}'")
    return fn(value, threshold)


# ── Final response composer (Python template — no LLM) ────────────────────────

def compose_final_response(state: "WorkflowState") -> str:
    """
    Build a structured, customer-facing message entirely in Python from the
    accumulated agent outputs stored in WorkflowState.  No LLM call is made.

    Field resolution order for each slot:
      transaction_id  — current_output → trigger_payload → fallback
      failed_psp      — current_output["failed_psp"] or ["psp_used"]
      recommended_psp — current_output["recommended_psp"]
      failure_type    — current_output["failure_type"] (set by investigator)
      amount / merchant — current_output or trigger_payload

    Non-payment workflows (support escalation, fraud detection) are detected
    by the absence of a known payment failure_type combined with the presence
    of support-specific fields (priority, customer_message, escalation_message).
    """
    out = state.get("current_output", {})

    failure_type = (
        state.get("failure_type")
        or out.get("failure_type")
        or "unknown"
    )

    ft = str(failure_type).upper()

    # ── Support escalation / tier-support paths ────────────────────────────────
    # These fields are produced by support / escalation agents, not payment agents.
    # Check them first when failure_type is absent or unknown so that support
    # escalation workflows return a meaningful message instead of the payment fallback.
    _payment_types = frozenset({
        "PSP_TIMEOUT", "ROUTING_FAILURE", "GATEWAY_ERROR",
        "CARD_DECLINE", "INSUFFICIENT_FUNDS",
    })
    customer_msg = out.get("customer_message") or out.get("escalation_message")
    priority = out.get("priority")

    if ft not in _payment_types:
        if priority == "high":
            ticket = out.get("ticket_id", "")
            ticket_str = f" Your ticket ID is {ticket}." if ticket else ""
            return (
                f"Dear customer, your high-priority issue has been escalated to our "
                f"senior support team.{ticket_str} We will contact you within 2 hours."
            )
        elif priority == "low":
            return (
                "Dear customer, our support team has reviewed your request and will "
                "provide a resolution within 24 hours."
            )
        if customer_msg:
            return str(customer_msg)

    # ── Payment-specific paths ─────────────────────────────────────────────────
    transaction_id  = out.get("transaction_id") or "your transaction"
    failed_psp      = out.get("psp") or out.get("failed_psp") or "the payment provider"
    recommended_psp = out.get("recommended_psp") or "an alternate provider"
    amount          = out.get("amount", "")
    merchant        = out.get("merchant_name") or "the merchant"
    amount_str = f"${amount} " if amount else ""

    if ft in ("PSP_TIMEOUT", "ROUTING_FAILURE", "GATEWAY_ERROR"):
        return (
            f"Dear customer, your payment of {amount_str}to {merchant} "
            f"(Transaction {transaction_id}) failed due to a timeout on "
            f"{failed_psp}. We recommend retrying via {recommended_psp}, "
            f"which is currently operating normally. Please retry your payment."
        )
    elif ft == "CARD_DECLINE":
        return (
            f"Dear customer, your payment of {amount_str}to {merchant} "
            f"(Transaction {transaction_id}) was declined by your bank. "
            f"Please try a different card or contact your bank for assistance."
        )
    elif ft == "INSUFFICIENT_FUNDS":
        return (
            f"Dear customer, your payment of {amount_str}to {merchant} "
            f"(Transaction {transaction_id}) failed due to insufficient funds. "
            f"Please add funds to your account and retry."
        )
    else:
        # Final fallback — also surfaces any customer_msg the agents produced
        if customer_msg:
            return str(customer_msg)
        return (
            f"Dear customer, your payment to {merchant} "
            f"(Transaction {transaction_id}) could not be processed. "
            f"Our team will investigate and contact you within 24 hours."
        )


# ── WorkflowCompiler ──────────────────────────────────────────────────────────

class WorkflowCompiler:
    """
    Stateless compiler.  Call compile(workflow) each time a run starts.
    The compiled graph is re-used for ainvoke; the checkpointer persists
    thread state keyed by run_id (= thread_id in LangGraph config).
    """

    async def compile(self, workflow: Any) -> Any:
        """
        Parse workflow.graph_json and return a compiled LangGraph app.

        Parameters
        ----------
        workflow : Workflow ORM instance (must have .graph_json dict)

        Supports two graph_json formats automatically:
          • Old ReactFlow format  — nodes with ``id``/``type``/``data`` keys;
                                    edges with ``source``/``target`` keys.
          • Backend-native format — nodes with ``node_id``/``node_type``/``config_json``;
                                    edges with ``source_node_id``/``target_node_id``;
                                    optional top-level ``entry_node`` field.
        """
        graph_json: dict = workflow.graph_json

        # Normalise both formats into a common internal representation
        nodes, adjacency = self._normalize_graph(graph_json)

        # ── Determine entry point ─────────────────────────────────────────────
        # Priority 1: explicit "entry_node" field (new backend-native format)
        # Priority 2: outgoing edge of any "start" or "trigger" node
        #   • "start"   — seeded graphs (old ReactFlow format)
        #   • "trigger" — graphs saved from the Canvas builder (ReactFlow native)
        entry_node_id: str | None = graph_json.get("entry_node") or None
        if not entry_node_id:
            for nid, nd in nodes.items():
                if nd["type"] in ("start", "trigger"):
                    out = adjacency.get(nid, [])
                    if out:
                        entry_node_id = out[0][1]
                    break

        # ── Build StateGraph ──────────────────────────────────────────────────
        graph = StateGraph(WorkflowState)

        # Add 'agent' nodes and 'end' nodes as real LangGraph nodes
        for node_id, node in nodes.items():
            if node["type"] == "agent":
                fn = self._build_agent_node(node_id, node["data"])
                graph.add_node(node_id, fn)
            elif node["type"] == "end":
                # end node is a pure state composition function, NOT an LLM call
                graph.add_node(node_id, self._build_end_node(node_id))

        # Set entry point
        if entry_node_id:
            graph.set_entry_point(entry_node_id)

        # Wire edges
        for node_id, node in nodes.items():
            ntype = node["type"]

            if ntype in ("start", "trigger", "condition"):
                continue  # start/trigger = entry marker; condition wired via incoming agent

            if ntype == "end":
                graph.add_edge(node_id, END)
                continue

            if ntype != "agent":
                continue

            for _eid, tgt_id, _edata in adjacency.get(node_id, []):
                tgt_node = nodes.get(tgt_id, {})
                tgt_type = tgt_node.get("type")

                if tgt_type == "end":
                    # Route to the end composition node, not directly to LangGraph END
                    graph.add_edge(node_id, tgt_id)

                elif tgt_type == "condition":
                    # Build router from condition node; wire as conditional edges
                    router = self._build_router(tgt_node)
                    path_map = self._build_path_map(tgt_id, adjacency, nodes)
                    graph.add_conditional_edges(node_id, router, path_map)

                else:
                    # Plain agent → agent edge
                    graph.add_edge(node_id, tgt_id)

        # ── Checkpointer ─────────────────────────────────────────────────────
        checkpointer = await self._get_checkpointer()

        return graph.compile(checkpointer=checkpointer)

    # ── Graph normalisation ───────────────────────────────────────────────────

    @staticmethod
    def _normalize_graph(
        graph_json: dict,
    ) -> tuple[dict[str, dict], dict[str, list[tuple[str, str, dict]]]]:
        """
        Normalise both old (ReactFlow) and new (backend-native) graph_json formats
        into a common internal representation so the rest of compile() is format-agnostic.

        Returns
        -------
        nodes     : {node_id: {"id": node_id, "type": node_type, "data": data_dict}}
        adjacency : {source_id: [(edge_id, target_id, edge_data_dict), ...]}

        Old ReactFlow format keys  → internal key
          id                        → id / type / data
          type                      →
          data                      →
          source / target / data    → adjacency entries

        New backend-native format keys → internal key
          node_id                    → id / type / data
          node_type                  →
          config_json                →
          source_node_id             → adjacency entries
          target_node_id             →
          condition_json             →
        """
        raw_nodes: list[dict] = graph_json.get("nodes", [])
        raw_edges: list[dict] = graph_json.get("edges", [])

        nodes: dict[str, dict] = {}
        for n in raw_nodes:
            if "node_id" in n:
                # New backend-native format
                node_id = n["node_id"]
                node_type = n["node_type"]
                data: dict = n.get("config_json") or {}
            else:
                # Old ReactFlow format
                node_id = n["id"]
                node_type = n["type"]
                data = n.get("data") or {}
            nodes[node_id] = {"id": node_id, "type": node_type, "data": data}

        adjacency: dict[str, list[tuple[str, str, dict]]] = {}
        for e in raw_edges:
            if "source_node_id" in e:
                # New backend-native format
                src = e["source_node_id"]
                tgt = e["target_node_id"]
                edge_data: dict = e.get("condition_json") or {}
            else:
                # Old ReactFlow format
                src = e["source"]
                tgt = e["target"]
                edge_data = e.get("data") or {}
            edge_id: str = e.get("id") or e.get("label") or f"{src}->{tgt}"
            adjacency.setdefault(src, []).append((edge_id, tgt, edge_data))

        return nodes, adjacency

    # ── Node builders ─────────────────────────────────────────────────────────

    def _build_agent_node(self, node_id: str, node_data: dict) -> Callable:
        """
        Return an async function (state → dict) that:
        1. Runs guardrails
        2. Fetches the agent from DB
        3. Invokes LLM with tool loop
        4. Parses JSON output
        5. Writes RunStep / ToolCall / TokenUsage / Message records
        6. Broadcasts step events
        7. Returns state updates
        """
        # Old format uses "agent" key; new format uses "agent_name" key
        agent_name: str = node_data.get("agent") or node_data.get("agent_name") or node_id
        obs = ObservabilityService()

        async def agent_node(state: WorkflowState) -> dict:  # noqa: C901
            run_id = state["run_id"]
            started_at = datetime.now(timezone.utc)
            called_tools: set = set()   # ISSUE 2: per-invocation dedup; NOT shared across nodes

            async with AsyncSessionLocal() as db:
                # ── 1. Fetch agent ────────────────────────────────────────────
                result = await db.execute(
                    select(Agent).where(Agent.name == agent_name)
                )
                agent = result.scalar_one_or_none()
                if agent is None:
                    raise ValueError(f"Agent '{agent_name}' not found in DB")

                # ── 2. Guardrail: iteration + cost ceiling ────────────────────
                try:
                    _guardrails.check_before_step(agent, state, None)
                except GuardrailViolation as gv:
                    await obs.broadcast(run_id, EVT_GUARDRAIL_VIOLATED, {
                        "node": node_id, "reason": gv.reason,
                    })
                    raise  # propagates to _execute_run → run marked failed

                # ── 3. Broadcast step_started ─────────────────────────────────
                await obs.broadcast(run_id, EVT_STEP_STARTED, {
                    "node": node_id, "agent": agent_name,
                })

                # ── 4. LLM + tools ────────────────────────────────────────────
                tools = _get_tools_for_agent(agent)
                llm = get_llm(agent.model_provider, agent.model_name)
                llm_with_tools = llm.bind_tools(tools) if tools else llm

                # Build message history: system prompt + existing conversation
                lc_messages: list = (
                    [SystemMessage(content=agent.system_prompt)]
                    + state["messages"]
                )
                accumulated: list = []  # new messages produced this step

                # ── 5. Create RunStep record (running) ────────────────────────
                step_record = RunStep(
                    run_id=uuid.UUID(run_id),
                    agent_id=agent.id,
                    status=StepStatus.running,
                    input={"message_count": len(lc_messages)},
                    started_at=started_at,
                )
                db.add(step_record)
                await db.flush()  # need step_record.id for tool calls
                step_id = step_record.id

                # ── 6. Agentic loop: LLM → tool calls → LLM → … ─────────────
                final_response = None
                try:
                    while True:
                        response: AIMessage = await llm_with_tools.ainvoke(
                            lc_messages + accumulated
                        )
                        accumulated.append(response)

                        if not response.tool_calls:
                            final_response = response
                            break

                        # Execute each tool call
                        for tc in response.tool_calls:
                            tool_name: str = tc["name"]
                            tool_args: dict = tc.get("args", {})

                            # ISSUE 2: skip duplicate tool calls within this node invocation
                            call_key = (tool_name, json.dumps(tool_args, sort_keys=True))
                            if call_key in called_tools:
                                logger.debug(
                                    "skipped duplicate tool call: %s(%s)", tool_name, tool_args
                                )
                                accumulated.append(ToolMessage(
                                    content=json.dumps({"skipped": "duplicate call"}),
                                    tool_call_id=tc["id"],
                                ))
                                continue
                            called_tools.add(call_key)

                            # Guardrail: allowlist check
                            try:
                                _guardrails.filter_tool(agent, tool_name)
                            except GuardrailViolation as gv:
                                await obs.broadcast(run_id, EVT_GUARDRAIL_VIOLATED, {
                                    "node": node_id, "tool": tool_name, "reason": gv.reason,
                                })
                                tool_result: Any = {"error": gv.reason}
                            else:
                                tool_fn = TOOL_REGISTRY.get(tool_name)
                                if tool_fn is None:
                                    tool_result = {"error": f"Tool '{tool_name}' not registered"}
                                else:
                                    try:
                                        tool_result = await tool_fn.ainvoke(tool_args)
                                    except Exception as e:
                                        tool_result = {"error": str(e)}

                            # Persist tool call
                            await obs.record_tool_call(
                                db, step_id, tool_name, tool_args,
                                tool_result if isinstance(tool_result, dict)
                                else {"result": str(tool_result)},
                            )

                            # Broadcast
                            await obs.broadcast(run_id, EVT_TOOL_CALLED, {
                                "node": node_id, "tool": tool_name,
                                "args": tool_args,
                                "result": tool_result,
                            })

                            accumulated.append(ToolMessage(
                                content=json.dumps(tool_result)
                                if not isinstance(tool_result, str)
                                else tool_result,
                                tool_call_id=tc["id"],
                            ))

                except Exception:
                    step_record.status = StepStatus.failed
                    step_record.ended_at = datetime.now(timezone.utc)
                    await db.commit()
                    raise

                # ── 7. Record token usage ─────────────────────────────────────
                usage: dict = getattr(final_response, "usage_metadata", None) or {}
                prompt_tokens = usage.get("input_tokens", 0)
                completion_tokens = usage.get("output_tokens", 0)
                cost_increment = 0.0
                if prompt_tokens or completion_tokens:
                    token_record = await obs.record_token_usage(
                        db, run_id,
                        agent.model_provider, agent.model_name,
                        prompt_tokens, completion_tokens,
                    )
                    # BUG 3 fix: propagate real cost into running state total
                    cost_increment = token_record.estimated_cost or 0.0

                # ── 8. Parse JSON output ──────────────────────────────────────
                raw_content: str = final_response.content if final_response else ""
                output: dict = _parse_json(raw_content)

                # ── 9. Persist AI message ─────────────────────────────────────
                await obs.record_message(
                    db, run_id, MessageRole.assistant, raw_content
                )

                # ── 10. Update RunStep ────────────────────────────────────────
                step_record.status = StepStatus.completed
                step_record.output = output
                step_record.ended_at = datetime.now(timezone.utc)
                await db.commit()

            # ── 11. Broadcast step_completed ──────────────────────────────────
            await obs.broadcast(run_id, EVT_STEP_COMPLETED, {
                "node": node_id, "agent": agent_name, "output": output,
            })

            # ── 12. Build state updates ───────────────────────────────────────
            updates: dict = {
                "messages": [AIMessage(content=raw_content)],
                "current_output": {**state.get("current_output", {}), **output},
                "iteration_count": state["iteration_count"] + 1,
                "total_cost_usd": state.get("total_cost_usd", 0.0) + cost_increment,
            }

            # Promote well-known output keys into top-level state fields
            if "reviewer_score" in output:
                try:
                    updates["reviewer_score"] = float(output["reviewer_score"])
                except (TypeError, ValueError):
                    pass

            if "failure_type" in output:
                updates["failure_type"] = output["failure_type"]

            # Build final_response from whichever key the agent produced
            for key in ("customer_message", "resolution", "escalation_message",
                        "response", "message"):
                if key in output:
                    updates["final_response"] = str(output[key])
                    break

            return updates

        agent_node.__name__ = f"node_{node_id}"
        return agent_node

    # ── End node (pure state composition — no LLM) ────────────────────────────

    def _build_end_node(self, node_id: str) -> Callable:
        """
        Pure async function — no LLM, no agent.
        Calls compose_final_response() to build a structured customer-facing
        message from accumulated agent outputs, then persists it to the runs table.
        """
        async def end_node(state: WorkflowState) -> dict:
            run_id = state["run_id"]
            final = compose_final_response(state)

            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("UPDATE runs SET final_response = :val WHERE id = :rid"),
                    {"val": final, "rid": uuid.UUID(run_id)},
                )
                await db.commit()

            return {"final_response": final}

        end_node.__name__ = f"node_{node_id}"
        return end_node

    # ── Condition routing ──────────────────────────────────────────────────────

    def _build_router(self, cond_node: dict) -> Callable[[dict], str]:
        """
        Return a routing function (state → target_node_id_string) built
        from the condition node's data.

        Supports:
          • Enum matching:  state[field] in cases dict → cases[value] or cases['default']
          • Numeric ops:    state[field] <op> threshold → cases['true'] or cases['false']
        Includes the reviewer-retry guard (iteration_count ≥ 2 → force success path).
        """
        data: dict = cond_node.get("data", {})
        field: str = data.get("field", "")
        op_str: str | None = data.get("operator")
        threshold: Any = data.get("threshold")
        cases: dict = data.get("cases", {})

        def router(state: dict) -> str:
            field_val = state.get(field)

            if op_str and threshold is not None:
                # Numeric comparison
                try:
                    result = _eval_op(op_str, float(field_val or 0), float(threshold))
                except (TypeError, ValueError):
                    result = False
                key = "true" if result else "false"
                target = cases.get(key)
            else:
                # Enum / string matching — BUG 4 fix: case-insensitive comparison
                val_norm = str(field_val).lower() if field_val is not None else ""
                cases_lower = {k.lower(): v for k, v in cases.items()}
                target = cases_lower.get(val_norm)
                if target is None:
                    target = cases_lower.get("default")

            # Reviewer retry guard (per spec): if this is a score condition and
            # we've already retried once, force the success-path to avoid infinite loop.
            if field == "reviewer_score" and state.get("iteration_count", 0) >= 2:
                target = cases.get("true", target)

            # Fallback: first case value
            if target is None and cases:
                target = next(iter(cases.values()))

            return target or "__end__"

        return router

    def _build_path_map(
        self,
        cond_node_id: str,
        adjacency: dict[str, list[tuple[str, str, dict]]],
        nodes: dict[str, dict],
    ) -> dict[str, Any]:
        """
        Build the path_map dict for add_conditional_edges from the outgoing
        edges of a condition node.  Maps routing string → LangGraph node name or END.
        """
        path_map: dict[str, Any] = {}
        for _eid, tgt_id, _edata in adjacency.get(cond_node_id, []):
            tgt_type = nodes.get(tgt_id, {}).get("type")
            if tgt_type == "end":
                path_map[tgt_id] = END
                path_map["__end__"] = END
            else:
                path_map[tgt_id] = tgt_id
        # Always provide a fallback END mapping so the router can return "__end__"
        path_map.setdefault("__end__", END)
        return path_map

    # ── Checkpointer ──────────────────────────────────────────────────────────

    async def _get_checkpointer(self):
        """
        Try AsyncPostgresSaver (langgraph-checkpoint-postgres + psycopg).
        Falls back to MemorySaver automatically.

        Production note: run `make up` after adding psycopg[binary] and
        langgraph-checkpoint-postgres to pyproject.toml to enable Postgres checkpoints.
        """
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore

            # AsyncPostgresSaver needs a plain psycopg3 connection string
            conn_str = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            checkpointer = await AsyncPostgresSaver.from_conn_string(conn_str)
            await checkpointer.setup()   # idempotent: creates checkpoint tables if absent
            logger.info("Checkpointing: AsyncPostgresSaver (Postgres)")
            return checkpointer

        except Exception as exc:
            logger.warning(
                "AsyncPostgresSaver unavailable (%s); falling back to MemorySaver. "
                "Add psycopg[binary] + langgraph-checkpoint-postgres and rebuild to enable "
                "Postgres checkpointing.",
                exc,
            )
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore

            return MemorySaver()
