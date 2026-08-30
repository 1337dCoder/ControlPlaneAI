"""Stage 2a: Performance & Confidence Detector.

Evaluates token-level log probabilities and sequence entropy if exposed by the provider.
Falls back to extracting self-rated confidence from the TruthPrompt output schema.
"""

import re
import math
from typing import List, Optional, Tuple, Dict, Any


class PerformanceDetector:
    """Evaluates statistical and self-rated confidence signals."""

    CONFIDENCE_PATTERNS = [
        r"(?i)confidence(?:[^\d\n]*\n)?[^\d]{0,25}(\b[01](?:\.\d+)?\b)",
        r"\[CONFIDENCE:\s*([0-9]*\.?[0-9]+)\]",
        r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)',
    ]

    def __init__(self, policy_config: Dict[str, Any] = None):
        self.policy = policy_config or {}
        conf_cfg = self.policy.get("confidence", {})
        self.high_threshold = conf_cfg.get("high_threshold", 0.80)
        self.qualified_threshold = conf_cfg.get("qualified_threshold", 0.50)

    def evaluate(
        self,
        response_text: str,
        token_logprobs: Optional[List[float]] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculates performance_score and extracts self_rated_confidence.
        
        Returns:
            (performance_score, self_rated_confidence)
        """
        perf_score = None
        self_rated = self._extract_self_rated_confidence(response_text)

        if token_logprobs and len(token_logprobs) > 0:
            # Calculate average linear probability from logprobs: mean(exp(lp))
            # Or exponential mean logprob mapped between 0.0 and 1.0
            probs = [math.exp(max(lp, -20.0)) for lp in token_logprobs]
            perf_score = round(sum(probs) / len(probs), 3)
        elif self_rated is not None:
            # Fallback to self-rated confidence
            perf_score = self_rated

        return perf_score, self_rated

    def _extract_self_rated_confidence(self, text: str) -> Optional[float]:
        """Extract explicit self-reported confidence score from response."""
        for pat in self.CONFIDENCE_PATTERNS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    # Handle percentage format if between 1 and 100
                    if val > 1.0 and val <= 100.0:
                        val = val / 100.0
                    return max(0.0, min(1.0, round(val, 3)))
                except ValueError:
                    continue
        return None
