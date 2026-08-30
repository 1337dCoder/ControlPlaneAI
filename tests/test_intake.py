"""Unit tests for Stage 1b 4-question structured intake."""

import pytest
from app.intake import IntakeNormalizer


def test_clear_prompt_inferred_intake():
    normalizer = IntakeNormalizer()
    prompt = "Summarize this article under 100 words in markdown: The history of quantum computing..."
    result = normalizer.normalize(prompt)

    assert result.source == "inferred"
    assert "Summarize" in result.task
    assert "under 100 words" in result.constraints.lower()
    assert result.expected_output in ["MARKDOWN", "SUMMARY"]


def test_json_constraint_detection():
    normalizer = IntakeNormalizer()
    prompt = "Extract all dates and events from this log file and return as valid JSON."
    result = normalizer.normalize(prompt)

    assert result.source == "inferred"
    assert result.expected_output == "JSON"


def test_ambiguous_short_prompt_asks_user():
    normalizer = IntakeNormalizer()
    prompt = "do stuff"
    result = normalizer.normalize(prompt)

    assert result.source == "asked_user"
    assert result.task == "do stuff"
