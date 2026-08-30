"""Stage 1b: 4-Question Structured Intake Normalizer.

Normalizes raw user messages into four fields:
- Task: Core action or goal
- Context: Domain/background/input parameters
- Constraints: Length, formatting, or negative constraints
- Expected Output: Specified output format (JSON, markdown, bullet points, etc.)

Uses fast rule-based heuristic inference (0 extra tokens). When genuinely ambiguous,
flags for clarification rather than making wasteful repetitive LLM calls.
"""

import re
from typing import Dict, Any, Tuple
from app.core_types import IntakeResult


class IntakeNormalizer:
    """Heuristic intake parser for incoming user requests."""

    FORMAT_PATTERNS = {
        "json": r"\b(json|as json|in json format|valid json)\b",
        "markdown": r"\b(markdown|md|bullet points?|bulleted list)\b",
        "csv": r"\b(csv|comma separated|table format|tabular)\b",
        "code": r"\b(python|javascript|typescript|c\+\+|rust|sql|code snippet|script)\b",
        "summary": r"\b(summary|summarize|tldr|brief overview|in short)\b",
    }

    CONSTRAINT_PATTERNS = [
        r"(?:under|less than|max(?:imum)?|limit to)\s+(\d+\s*(?:words|sentences|paragraphs|tokens|lines))",
        r"(?:do not|don\'t|without|avoid|exclude)\s+([^.,;]+)",
        r"(?:must include|only use|strictly)\s+([^.,;]+)",
    ]

    CONTEXT_PREFIXES = [
        r"(?:given that|context:|background:|assuming|for context,)\s*(.*?)(?=(?:please|do|write|create|solve|$))",
    ]

    def normalize(self, raw_prompt: str) -> IntakeResult:
        """Parse raw prompt into structured IntakeResult."""
        text = raw_prompt.strip()
        
        # Check if raw prompt is too brief / ambiguous
        if len(text.split()) < 3 and not re.search(r"\b(hello|hi|help|explain|what|how|why)\b", text, re.I):
            return IntakeResult(
                task=text,
                context="",
                constraints="Unspecified context",
                expected_output="General clarification",
                source="asked_user"
            )

        task = self._extract_task(text)
        context = self._extract_context(text)
        constraints = self._extract_constraints(text)
        expected_output = self._extract_expected_output(text)

        return IntakeResult(
            task=task,
            context=context,
            constraints=constraints,
            expected_output=expected_output,
            source="inferred"
        )

    def _extract_task(self, text: str) -> str:
        """Extract the main actionable request."""
        # Simple extraction: remove explicit context prefixes if present
        clean_text = text
        for pat in self.CONTEXT_PREFIXES:
            clean_text = re.sub(pat, "", clean_text, flags=re.IGNORECASE).strip()
        
        # If prompt has multiple sentences, first actionable sentence or full prompt
        sentences = [s.strip() for s in re.split(r"[.?!]\s+", clean_text) if s.strip()]
        if sentences:
            return sentences[0]
        return text

    def _extract_context(self, text: str) -> str:
        """Extract contextual notes if indicated by keywords."""
        for pat in self.CONTEXT_PREFIXES:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_constraints(self, text: str) -> str:
        """Extract explicit constraint clauses."""
        found_constraints = []
        for pat in self.CONSTRAINT_PATTERNS:
            matches = re.finditer(pat, text, re.IGNORECASE)
            for m in matches:
                found_constraints.append(m.group(0).strip())
        return "; ".join(found_constraints) if found_constraints else "None specified"

    def _extract_expected_output(self, text: str) -> str:
        """Extract requested output format or structure."""
        for fmt, pat in self.FORMAT_PATTERNS.items():
            if re.search(pat, text, re.IGNORECASE):
                return fmt.upper()
        return "Plain Text / Markdown"
