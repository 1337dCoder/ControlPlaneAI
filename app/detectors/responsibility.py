"""Stage 2c: Responsibility & Safety Detector.

Performs dual-pass (input and output) regex scanning for PII / secrets and
enforces corporate policy rulesets.
"""

import re
from typing import Dict, Any, List, Tuple


class ResponsibilityDetector:
    """Scans text for sensitive PII entities and banned safety policy rules."""

    DEFAULT_PII_REGEX = {
        "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "phone": r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "api_key": r"\b(?:sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})\b",
    }

    def __init__(self, policy_config: Dict[str, Any] = None):
        self.policy = policy_config or {}
        resp_cfg = self.policy.get("responsibility", {})
        self.pii_regex = resp_cfg.get("pii_regex", self.DEFAULT_PII_REGEX)
        self.banned_topics = resp_cfg.get("banned_topics", [])

    def scan_pii(self, text: str) -> List[str]:
        """
        Scans text for PII entity types.
        Returns list of entity type names found (e.g. ['email', 'ssn']), never raw secrets.
        """
        entities_found = set()
        for entity_type, pattern in self.pii_regex.items():
            if re.search(pattern, text, re.IGNORECASE):
                entities_found.add(entity_type)
        return sorted(list(entities_found))

    def scan_policy_violations(self, text: str) -> List[str]:
        """
        Scans text for banned keywords and policy rule triggers.
        Returns list of triggered rule IDs.
        """
        triggered_rules = []
        text_lower = text.lower()
        for rule in self.banned_topics:
            rule_id = rule.get("rule_id", "UNKNOWN_RULE")
            keywords = rule.get("keywords", [])
            for kw in keywords:
                if kw.lower() in text_lower:
                    triggered_rules.append(rule_id)
                    break
        return triggered_rules

    def scan_all(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Run complete scan returning (pii_entities, policy_hits).
        """
        pii = self.scan_pii(text)
        policy_hits = self.scan_policy_violations(text)
        return pii, policy_hits

    def redact_pii(self, text: str) -> Tuple[str, List[str]]:
        """
        Deterministically redacts sensitive PII entities from text.
        Returns (redacted_text, list_of_redactions_applied).
        """
        redacted = text
        applied = []
        for entity_type, pattern in self.pii_regex.items():
            replacement = f"[REDACTED_{entity_type.upper()}]"
            new_text, count = re.subn(pattern, replacement, redacted, flags=re.IGNORECASE)
            if count > 0:
                redacted = new_text
                applied.append(f"redacted_{entity_type}")
        return redacted, applied
