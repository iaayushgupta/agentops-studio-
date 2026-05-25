"""GuardrailEvaluator — pre-step safety checks for agent nodes."""
from __future__ import annotations


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails; carries a human-readable reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GuardrailEvaluator:
    """
    Stateless evaluator called at the start of every agent node execution.

    check_before_step  — enforces iteration and cost ceilings per agent config.
    filter_tool        — enforces the agent's tools_enabled allowlist.
    """

    def check_before_step(self, agent, state: dict, run) -> None:
        """
        Raise GuardrailViolation if:
          • state['iteration_count'] > agent.max_iterations
          • current run cost (state['total_cost_usd']) > agent.max_cost_usd

        Parameters
        ----------
        agent : Agent ORM instance (must have max_iterations, max_cost_usd attrs)
        state : current WorkflowState dict
        run   : Run ORM instance or None (reserved for future cost cross-check)
        """
        iteration_count: int = state.get("iteration_count", 0)
        if iteration_count > agent.max_iterations:
            raise GuardrailViolation(
                f"Iteration limit exceeded for agent '{agent.name}': "
                f"{iteration_count} > {agent.max_iterations}"
            )

        current_cost: float = state.get("total_cost_usd", 0.0) or 0.0
        if current_cost > agent.max_cost_usd:
            raise GuardrailViolation(
                f"Cost limit exceeded for agent '{agent.name}': "
                f"${current_cost:.4f} > ${agent.max_cost_usd:.2f}"
            )

    def filter_tool(self, agent, tool_name: str) -> None:
        """
        Raise GuardrailViolation if tool_name is not in agent.tools_enabled
        (check is skipped when tools_enabled is empty / None — agent has no
        tool restriction in that case).
        """
        allowed: list[str] = agent.tools_enabled or []
        if allowed and tool_name not in allowed:
            raise GuardrailViolation(
                f"Tool '{tool_name}' is not in agent '{agent.name}'.tools_enabled: {allowed}"
            )
