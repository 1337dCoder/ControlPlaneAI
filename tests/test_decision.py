"""Unit tests for Confidence State Machine and Decision Engine."""

import pytest
from app.core_types import DetectionFindings, ConfidenceResult
from app.confidence import ConfidenceStateMachine
from app.decision import DecisionEngine


def test_high_confidence_allows():
    conf_sm = ConfidenceStateMachine()
    engine = DecisionEngine()

    findings = DetectionFindings(performance_score=0.92, pii_found=[], policy_hits=[])
    confidence = conf_sm.evaluate(findings)

    assert confidence.state == "HIGH"

    decision = engine.decide(confidence, findings)
    assert decision.action == "ALLOW"
    assert decision.warning_banner is None


def test_pii_forces_edit_redaction():
    conf_sm = ConfidenceStateMachine()
    engine = DecisionEngine()

    findings = DetectionFindings(performance_score=0.95, pii_found=["email", "ssn"])
    confidence = conf_sm.evaluate(findings)

    assert confidence.state == "LOW"

    decision = engine.decide(confidence, findings)
    assert decision.action == "EDIT"
    assert "redacted_email" in decision.edits_applied
    assert "redacted_ssn" in decision.edits_applied
    assert any("PII" in r or "email" in r for r in decision.reasons)


def test_qualified_confidence_edits_with_caveat():
    conf_sm = ConfidenceStateMachine()
    engine = DecisionEngine()

    findings = DetectionFindings(performance_score=0.65, pii_found=[], policy_hits=[])
    confidence = conf_sm.evaluate(findings)

    assert confidence.state == "QUALIFIED"

    decision = engine.decide(confidence, findings)
    assert decision.action == "EDIT"
    assert decision.warning_banner is not None
    assert "appended_qualified_caveat" in decision.edits_applied
    assert "caveat" in decision.warning_banner.lower() or "qualified" in decision.warning_banner.lower()


def test_low_confidence_escalates_to_review():
    conf_sm = ConfidenceStateMachine()
    engine = DecisionEngine()

    findings = DetectionFindings(performance_score=0.20, pii_found=[], policy_hits=[])
    confidence = conf_sm.evaluate(findings)

    assert confidence.state == "LOW"

    decision = engine.decide(confidence, findings)
    assert decision.action == "ESCALATE"
    assert decision.review_id is not None
    assert decision.review_id.startswith("rev_")
    assert decision.warning_banner is not None


def test_policy_hit_forces_block():
    conf_sm = ConfidenceStateMachine()
    engine = DecisionEngine()

    findings = DetectionFindings(performance_score=0.95, policy_hits=["POL-001"])
    confidence = conf_sm.evaluate(findings)

    decision = engine.decide(confidence, findings)
    assert decision.action == "BLOCK"
