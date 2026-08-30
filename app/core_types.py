"""Core data contracts for the ControlPlane wrapper."""

from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


class IntakeResult(BaseModel):
    """Normalized 4-question intake representation."""
    task: str = Field(description="The primary action or goal requested.")
    context: str = Field(default="", description="Relevant context or domain background.")
    constraints: str = Field(default="", description="Formatting, length, or logical constraints.")
    expected_output: str = Field(default="", description="Specified return format or structure.")
    source: Literal["inferred", "asked_user"] = Field(
        default="inferred",
        description="Whether fields were silently inferred or queried from the user."
    )


class TruthPromptEnvelope(BaseModel):
    """Payload carrying the standing TruthPrompt instructions and intake."""
    version: str = Field(default="truth_prompt_v1", description="Template version identifier.")
    known_facts: List[str] = Field(default_factory=list, description="Verified facts separated from assumptions.")
    assumptions: List[str] = Field(default_factory=list, description="Explicitly identified inferences or assumptions.")
    unknowns: List[str] = Field(default_factory=list, description="Explicitly identified unknowns or missing data.")
    intake: IntakeResult = Field(description="The 4-question normalized intake.")
    confidence_threshold: float = Field(default=0.75, description="Threshold below which output must be flagged.")
    bias_neutral: bool = Field(default=True, description="Enforce bias-neutral standing instructions.")


class DetectionFindings(BaseModel):
    """Post-generation and pre-generation findings across performance, cost, and responsibility."""
    performance_score: Optional[float] = Field(
        default=None,
        description="Calculated token-level logprob mean or entropy metric (0.0 to 1.0)."
    )
    self_rated_confidence: Optional[float] = Field(
        default=None,
        description="Self-reported confidence rating extracted from TruthPrompt output (0.0 to 1.0)."
    )
    is_duplicate: bool = Field(default=False, description="True if query matched recent semantic/hash cache.")
    spend_anomaly: bool = Field(default=False, description="True if request spend exceeded velocity/spike threshold.")
    pii_found: List[str] = Field(default_factory=list, description="PII entity types detected (e.g., 'email', 'ssn').")
    policy_hits: List[str] = Field(default_factory=list, description="Policy rule IDs triggered.")


class ConfidenceResult(BaseModel):
    """Synthesized 3-state evidence-based confidence result."""
    state: Literal["HIGH", "QUALIFIED", "LOW"]
    reasons: List[str] = Field(default_factory=list)


class Decision(BaseModel):
    """Deterministic policy outcome."""
    action: Literal["ALLOW", "EDIT", "ESCALATE", "BLOCK", "ASK_USER"]
    reasons: List[str] = Field(default_factory=list)
    warning_banner: Optional[str] = Field(
        default=None,
        description="User-facing banner prepended to responses when action is FLAG or EDIT/ESCALATE."
    )
    edits_applied: List[str] = Field(
        default_factory=list,
        description="List of deterministic edits applied (e.g., 'redacted_pii', 'appended_caveat')."
    )
    review_id: Optional[str] = Field(
        default=None,
        description="Set when action == ESCALATE, references review_queue item ID."
    )
    clarifying_questions: List[str] = Field(
        default_factory=list,
        description="List of clarifying questions if action is ASK_USER."
    )


class ReviewItem(BaseModel):
    """Model representing an escalated candidate response in review queue."""
    id: str
    request_id: str
    raw_prompt: str
    candidate_answer: str
    findings: Dict[str, Any]
    confidence_state: str
    reasons: List[str]
    status: Literal["pending", "approved", "rejected", "edited"] = "pending"
    reviewer_note: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


class ReviewResolution(BaseModel):
    """Payload for human review resolution."""
    action: Literal["approve", "reject", "edit"]
    note: Optional[str] = ""
    edited_content: Optional[str] = None


class ChatRequest(BaseModel):
    """Incoming request payload to the ControlPlane wrapper."""
    prompt: str = Field(..., description="The user's prompt text.")
    model_override: Optional[str] = Field(default=None, description="Optional explicit model name override.")
    user_id: Optional[str] = Field(default="anonymous", description="Caller/User identifier.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")


class ChatResponse(BaseModel):
    """Outgoing response payload from the ControlPlane wrapper."""
    request_id: str
    content: Optional[str] = Field(default=None, description="Candidate response text, or redacted/banner text.")
    decision: Decision
    confidence: ConfidenceResult
    findings: DetectionFindings
    intake: IntakeResult
    tier: Literal["cheap", "capable"]
    model_used: str
    cached: bool = False
    tokens_used: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    final_system_prompt: Optional[str] = Field(default=None, description="The exact system instructions (TruthPrompt) sent to the model.")
    final_user_prompt: Optional[str] = Field(default=None, description="The exact user input sent to the model.")


class AuditLogRecord(BaseModel):
    """Schema for records persisted to SQLite audit storage."""
    request_id: str
    timestamp: str
    user_id: str
    raw_prompt: str
    normalized_intake: Dict[str, Any]
    truth_prompt_version: str
    model_tier: str
    model_name: str
    findings: Dict[str, Any]
    confidence_state: str
    decision_action: str
    decision_reasons: List[str]
    tokens_used: int
    estimated_cost_usd: float
    latency_ms: float
    cached: bool
