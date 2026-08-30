"""Stage 2: Evidence-Based Confidence State Machine.

Combines statistical signals (logprobs/entropy), self-rated scores, and safety/cost findings
into one of three states: HIGH / QUALIFIED / LOW.

Rule: Confidence is evidence-based, NEVER based on linguistic tone or fluency.
"""

from typing import Dict, Any, List
from app.core_types import DetectionFindings, ConfidenceResult


class ConfidenceStateMachine:
    """Computes evidence-backed confidence state."""

    def __init__(self, policy_config: Dict[str, Any] = None):
        self.policy = policy_config or {}
        conf_cfg = self.policy.get("confidence", {})
        self.high_threshold = conf_cfg.get("high_threshold", 0.80)
        self.qualified_threshold = conf_cfg.get("qualified_threshold", 0.50)

    def evaluate(self, findings: DetectionFindings) -> ConfidenceResult:
        """Evaluate findings into ConfidenceResult (HIGH, QUALIFIED, LOW)."""
        reasons: List[str] = []

        # 1. PII or Policy violations immediately degrade confidence
        if findings.pii_found:
            reasons.append(f"PII entities detected: {', '.join(findings.pii_found)}")
        if findings.policy_hits:
            reasons.append(f"Safety policy rules fired: {', '.join(findings.policy_hits)}")

        # 2. Spend anomalies note
        if findings.spend_anomaly:
            reasons.append("Spend anomaly threshold exceeded")

        # 3. Determine base numerical confidence metric
        score = findings.performance_score
        if score is None and findings.self_rated_confidence is not None:
            score = findings.self_rated_confidence

        if score is not None:
            reasons.append(f"Effective confidence score: {score:.2f}")

        # 4. State resolution
        if findings.policy_hits or findings.pii_found:
            return ConfidenceResult(state="LOW", reasons=reasons)

        if score is not None:
            if score >= self.high_threshold:
                reasons.append(f"Score {score:.2f} meets HIGH threshold (>= {self.high_threshold})")
                return ConfidenceResult(state="HIGH", reasons=reasons)
            elif score >= self.qualified_threshold:
                reasons.append(f"Score {score:.2f} within QUALIFIED range [{self.qualified_threshold}, {self.high_threshold})")
                return ConfidenceResult(state="QUALIFIED", reasons=reasons)
            else:
                reasons.append(f"Score {score:.2f} below minimum threshold (< {self.qualified_threshold})")
                return ConfidenceResult(state="LOW", reasons=reasons)

        # 5. Default when no logprobs or self-rated confidence is provided
        reasons.append("No statistical or self-reported confidence data available; classified as QUALIFIED")
        return ConfidenceResult(state="QUALIFIED", reasons=reasons)
