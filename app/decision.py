"""Stage 2: Deterministic Decision Engine.

Maps (ConfidenceResult, DetectionFindings) -> Decision (ALLOW / EDIT / ESCALATE / BLOCK)
using a deterministic priority order defined in plan.md:
1. BLOCK — confirmed wrong or unfixable safety policy violation
2. EDIT — fixable issues (PII redaction, qualified confidence caveat)
3. ESCALATE — low confidence (escalates to review_queue in async or safe downgrade in sync mode)
4. ALLOW — high confidence, no issues
"""

import uuid
from typing import Dict, Any, List, Optional
from app.core_types import ConfidenceResult, DetectionFindings, Decision


class DecisionEngine:
    """Evaluates findings and confidence against policy rules to produce a deterministic decision."""

    DEFAULT_QUALIFIED_CAVEAT = "⚠️ [ControlPlane Caveat: This response has qualified evidence. Verification recommended for critical decisions.]"
    DEFAULT_LOW_CAVEAT = "⚠️ [ControlPlane Escalation: Low generation certainty detected. This response has been queued for human review.]"

    def __init__(self, policy_config: Dict[str, Any] = None):
        self.policy = policy_config or {}
        self.decision_matrix = self.policy.get("decision_matrix", [])

    def decide(
        self,
        confidence: ConfidenceResult,
        findings: DetectionFindings
    ) -> Decision:
        """
        Deterministically determine ALLOW, EDIT, ESCALATE, or BLOCK action in strict priority order.
        """
        # 1. BLOCK: Unfixable safety violation or critical policy hit
        if findings.policy_hits:
            return Decision(
                action="BLOCK",
                reasons=[f"Blocked due to safety policy violation: {', '.join(findings.policy_hits)}"],
                warning_banner=None,
                edits_applied=[]
            )

        # 2. EDIT: PII present (always fixable by deterministic redaction)
        if findings.pii_found:
            edits = [f"redacted_{p}" for p in findings.pii_found]
            if confidence.state == "QUALIFIED":
                edits.append("appended_qualified_caveat")
                banner = self._get_banner_for_state("QUALIFIED") or self.DEFAULT_QUALIFIED_CAVEAT
            else:
                banner = None

            return Decision(
                action="EDIT",
                reasons=[f"PII/secrets detected and redacted: {', '.join(findings.pii_found)}"],
                warning_banner=banner,
                edits_applied=edits
            )

        # 3. ESCALATE: Confidence is LOW (insufficient evidence / high uncertainty)
        if confidence.state == "LOW":
            review_id = f"rev_{uuid.uuid4().hex[:10]}"
            banner = self._get_banner_for_state("LOW") or self.DEFAULT_LOW_CAVEAT
            return Decision(
                action="ESCALATE",
                reasons=confidence.reasons + ["Escalated to human review due to low generation certainty."],
                warning_banner=banner,
                edits_applied=["appended_escalation_caveat"],
                review_id=review_id
            )

        # 4. EDIT: Confidence is QUALIFIED (attach caveat)
        if confidence.state == "QUALIFIED":
            banner = self._get_banner_for_state("QUALIFIED") or self.DEFAULT_QUALIFIED_CAVEAT
            return Decision(
                action="EDIT",
                reasons=confidence.reasons + ["Response qualified with evidence caveat."],
                warning_banner=banner,
                edits_applied=["appended_qualified_caveat"]
            )

        # 5. ALLOW: Confidence is HIGH
        return Decision(
            action="ALLOW",
            reasons=["Confidence is HIGH and no policy/PII violations were detected."],
            warning_banner=None,
            edits_applied=[]
        )

    def _get_banner_for_state(self, state: str) -> str:
        """Fetch configured banner message from policy YAML."""
        for rule in self.decision_matrix:
            if rule.get("if", {}).get("confidence_state") == state:
                return rule.get("banner", "")
        return ""
