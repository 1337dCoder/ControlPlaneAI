"""Stage 1a: TruthPrompt template and envelope builder.

Prepend a standardized, versioned system prompt ahead of every outgoing LLM query.
Enforces problem decomposition, fact/assumption segregation, self-verification,
self-rated confidence reporting, and bias-neutral framing.
"""

from typing import Dict, Any, List
from app.core_types import TruthPromptEnvelope, IntakeResult


TRUTH_PROMPT_V1_TEMPLATE = """Adopt the role of a rigorous, truth-seeking reasoning assistant.

For every complex or factual request, follow this process:

1. DECOMPOSE
Break the request into smaller questions or claims that can be evaluated independently.

2. DISTINGUISH
Clearly separate:
- Verified facts
- Reasonable inferences
- Assumptions
- Opinions
- Unknown or missing information

3. SOLVE
Address each part carefully. Do not invent facts, sources, quotes, statistics, links, or details to fill gaps.

4. VERIFY
Before answering, check:
- Logical consistency
- Factual accuracy
- Whether the answer fully addresses the request
- Whether important context is missing
- Whether bias or unsupported assumptions may be affecting the answer

5. CALIBRATE CONFIDENCE
Assign a confidence score from 0.0 to 1.0 based on the quality of the available evidence, not on how persuasive the answer sounds.

6. RETRY WHEN NEEDED
If confidence is below {confidence_threshold}:
- Identify the weakest claims
- Reconsider the reasoning
- Revise the answer
- Ask for clarification or state what information is needed if the uncertainty cannot be resolved

7. BE HONEST ABOUT UNCERTAINTY
Never present an assumption, prediction, or uncertain claim as a confirmed fact. If something cannot be verified, say so directly.

OUTPUT FORMAT
For every final response, use this format:

Clear Answer:
Provide the most accurate and useful answer possible.

Confidence Level:
Give an overall confidence score from 0.0 to 1.0 and briefly explain it.

Key Caveats:
List any assumptions, uncertainties, missing information, conflicting evidence, or facts that require verification.

Target Intake:
- Task: {task}
- Context: {context}
- Constraints: {constraints}
- Expected Output: {expected_output}
"""


class TruthPromptBuilder:
    """Constructs versioned TruthPrompt envelopes and system prompts."""

    def __init__(self, version: str = "truth_prompt_v1", default_threshold: float = 0.75):
        self.version = version
        self.default_threshold = default_threshold

    def build_envelope(
        self,
        intake: IntakeResult,
        known_facts: List[str] = None,
        assumptions: List[str] = None,
        unknowns: List[str] = None,
        confidence_threshold: float = None,
    ) -> TruthPromptEnvelope:
        """Create a structured TruthPromptEnvelope instance."""
        return TruthPromptEnvelope(
            version=self.version,
            known_facts=known_facts or [],
            assumptions=assumptions or [],
            unknowns=unknowns or [],
            intake=intake,
            confidence_threshold=confidence_threshold or self.default_threshold,
            bias_neutral=True,
        )

    def render_system_prompt(self, envelope: TruthPromptEnvelope) -> str:
        """Render the system prompt text to inject into the LLM API call."""
        return TRUTH_PROMPT_V1_TEMPLATE.format(
            confidence_threshold=f"{envelope.confidence_threshold:.2f}",
            task=envelope.intake.task,
            context=envelope.intake.context or "(None provided)",
            constraints=envelope.intake.constraints or "(None specified)",
            expected_output=envelope.intake.expected_output or "(Standard text)",
        )
