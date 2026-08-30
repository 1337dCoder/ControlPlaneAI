"""Tiered model routing engine (cheap vs capable).

Uses deterministic rule matching (task type, character length, reasoning keywords)
to route requests without wasting tokens on an intermediate LLM classification call.
"""

from typing import Dict, Any, Tuple, Literal
from app.core_types import IntakeResult


class TieredRouter:
    """Routes requests to the optimal model tier based on deterministic heuristics."""

    def __init__(self, policy_config: Dict[str, Any] = None):
        self.policy = policy_config or {}
        model_tiers = self.policy.get("model_tiers", {})
        self.cheap_model = model_tiers.get("cheap", {}).get("default_model", "gpt-3.5-turbo")
        self.capable_model = model_tiers.get("capable", {}).get("default_model", "gpt-4o")
        
        triggers = self.policy.get("routing_triggers", {})
        self.capable_keywords = triggers.get("capable_keywords", [
            "step-by-step proof",
            "mathematical proof",
            "formal verification",
            "architectural review",
            "security audit",
            "multi-variable optimization"
        ])
        self.max_cheap_chars = triggers.get("max_prompt_length_for_cheap", 1200)

    def route(
        self,
        raw_prompt: str,
        intake: IntakeResult,
        model_override: str = None
    ) -> Tuple[Literal["cheap", "capable"], str, str]:
        """Determine model tier, model name, and routing rationale."""
        # 1. Direct user override
        if model_override:
            tier: Literal["cheap", "capable"] = "capable" if "4" in model_override or "pro" in model_override else "cheap"
            return tier, model_override, "Explicit user model override"

        # 2. Length-based check
        if len(raw_prompt) > self.max_cheap_chars:
            return "capable", self.capable_model, f"Prompt length ({len(raw_prompt)} chars) exceeds cheap tier threshold ({self.max_cheap_chars})"

        # 3. Complexity & keyword triggers
        prompt_lower = raw_prompt.lower()
        for kw in self.capable_keywords:
            if kw.lower() in prompt_lower:
                return "capable", self.capable_model, f"Trigger keyword matched: '{kw}'"

        # 4. Default: cheap tier
        return "cheap", self.cheap_model, "Standard task routed to cost-optimized cheap tier"
