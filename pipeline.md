# ControlPlane Wrapper — End-to-End Pipeline Specification (`pipeline.md`)

This document provides a comprehensive technical specification of the ControlPlane execution pipeline, detailing data flow, stage contracts, verification mechanisms, and deterministic decision logic.

---

## 1. Executive Pipeline Architecture

ControlPlane acts as a **deterministic, non-invasive orchestration proxy** between client applications and downstream Large Language Model (LLM) providers. It operates in two main sequential stages: **Stage 1 (Prevention)** and **Stage 2 (Detection & Decision)**.

```mermaid
flowchart TD
    Client([Client Request]) --> API["FastAPI /v1/chat"]
    
    subgraph S1 ["Stage 1: Prevention (Pre-Generation)"]
        API --> RespPreCheck{"Pre-Execution PII / Policy Scan"}
        RespPreCheck -->|Banned / Critical Leak| BlockEarly["BLOCK (Early Exit)"]
        RespPreCheck -->|Pass| DedupCheck{"Semantic / Hash Dedup Cache"}
        DedupCheck -->|Cache Hit| ServeCached["Return Cached Response (Zero Token Cost)"]
        DedupCheck -->|Cache Miss| Intake["Structured Intake (Task, Context, Constraints, Output)"]
        Intake --> TruthPrompt["Inject TruthPrompt Template (Versioned System Prompt)"]
        TruthPrompt --> Router["Tiered Model Router (Rule-Based Complexity Classifier)"]
    end

    Router --> LLMProvider["LLM Execution Layer (Cheap Tier or Capable Tier)"]

    subgraph S2 ["Stage 2: Detection & Decision (Post-Generation)"]
        LLMProvider --> PerfDetector["Performance Detector (Logprobs / Entropy / Self-Rating)"]
        LLMProvider --> RespDetector["Responsibility Detector (PII / Secrets / Banned Topics)"]
        LLMProvider --> CostDetector["Cost Detector (Spend Metrics / Anomaly Detection)"]
        
        PerfDetector & RespDetector & CostDetector --> ConfMachine["Confidence State Machine (HIGH / QUALIFIED / LOW)"]
        ConfMachine --> DecisionEngine["Decision Engine (policy.yaml Rule Lookup)"]
    end

    DecisionEngine -->|ALLOW| DeliverNormal["Deliver Verified Response"]
    DecisionEngine -->|FLAG| DeliverFlagged["Deliver Response with Warning & Banner"]
    DecisionEngine -->|BLOCK| WithholdBlock["Withhold Output with Policy Explanation"]

    DeliverNormal & DeliverFlagged & WithholdBlock & ServeCached & BlockEarly --> AuditLogger["SQLite Audit Log & Metrics Recorder"]
    AuditLogger --> ClientResp([Final Client Response Envelope])
```

---

## 2. Stage-by-Stage Breakdown

### Stage 1: Prevention (Before Generation)

The goal of Prevention is to catch ambiguous requests, cost waste, duplicate executions, and policy leaks **before** consuming expensive model tokens.

```mermaid
sequenceDiagram
    autonumber
    actor User as Client
    participant Main as app/main.py
    participant Resp as detectors/responsibility.py
    participant Cost as detectors/cost.py
    participant Intake as app/intake.py
    participant TP as app/truth_prompt.py
    participant Router as app/router.py
    participant Provider as app/providers.py

    User->>Main: POST /v1/chat {prompt, metadata}
    Main->>Resp: Scan input prompt for PII & Policy violations
    alt Critical violation found
        Resp-->>Main: pii_found / policy_hit
        Main-->>User: BLOCK with violation reason
    else Input Clean
        Main->>Cost: Check Dedup Cache (hash/embedding lookup)
        alt Cache Hit (Recent identical or semantically identical query)
            Cost-->>Main: Cached ChatResponse
            Main-->>User: Return Cached Response (0 tokens consumed)
        else Cache Miss
            Main->>Intake: Normalize into 4 fields (Task, Context, Constraints, Expected Output)
            Intake-->>Main: IntakeResult (source: inferred | asked_user)
            Main->>TP: Build TruthPromptEnvelope with Standing Bias-Neutral Rules
            TP-->>Main: System Prompt + Formatted Payload
            Main->>Router: Classify Complexity (Rules on tokens, keywords, task type)
            Router-->>Main: Model Tier Selected ('cheap' | 'capable')
            Main->>Provider: Invoke LLM with System Envelope + User Intake
        end
    end
```

#### 1. Pre-execution Scan (`detectors/responsibility.py`)
- Fast regex and keyword inspection of inbound prompt.
- Prevents leaking secrets or executing explicitly prohibited prompts.

#### 2. Dedup Interception (`detectors/cost.py`)
- Request hashing and semantic similarity matching against recent executions stored in SQLite.
- If match exceeds similarity threshold (e.g. cosine ≥ 0.95 or exact normalized SHA256 match), cached output is returned immediately.

#### 3. Structured 4-Question Intake (`intake.py`)
- Normalizes raw prompt into:
  - **Task**: The core action requested.
  - **Context**: Domain background, inputs, or entities.
  - **Constraints**: Format limitations, length limits, forbidden tools.
  - **Expected Output**: Specific return format (e.g., JSON, markdown list, code block).
- **Resolution Strategy**:
  - *Heuristic Inference*: Fast rule-based keyword/regex parsing (0 extra tokens).
  - *Targeted Clarification*: Returns a single clarification question if genuinely ambiguous.

#### 4. TruthPrompt System Envelope (`truth_prompt.py`)
- Injects standardized instructions enforcing:
  1. Systematic decomposition of problem.
  2. Strict segregation of verified facts vs. assumptions/inferences.
  3. Output self-verification step.
  4. Self-reported confidence score (0.0 – 1.0).
  5. Built-in bias-neutral standing instructions.

#### 5. Tiered Model Router (`router.py`)
- Rule-based classifier mapping requests without using an LLM call:
  - **Cheap Tier** (e.g., `gpt-3.5-turbo`, `gemini-1.5-flash`): Simple summaries, extraction, formatting, standard Q&A.
  - **Capable Tier** (e.g., `gpt-4o`, `gemini-1.5-pro`): Complex multi-step reasoning, mathematical derivations, policy-sensitive tasks, or explicit user override.

---

### Stage 2: Detection & Decision (After Generation)

Post-generation, the candidate response undergoes parallel inspection by three specialized detectors.

```mermaid
flowchart LR
    LLMOut["Raw LLM Output + Token Logprobs"] --> P1["Performance Detector"]
    LLMOut --> P2["Responsibility Detector"]
    LLMOut --> P3["Cost & Spend Detector"]

    P1 -->|Logprob entropy & Self-rated conf| F1["Findings.performance"]
    P2 -->|Output PII & Policy keyword scan| F2["Findings.responsibility"]
    P3 -->|Token usage & Rolling spend delta| F3["Findings.cost"]

    F1 & F2 & F3 --> Synth["Confidence State Machine (app/confidence.py)"]
    Synth -->|HIGH / QUALIFIED / LOW| Dec["Decision Engine (app/decision.py)"]
    Dec -->|policy.yaml| Act["ALLOW / FLAG / BLOCK"]
```

#### 1. Performance Detection (`detectors/performance.py`)
- Evaluates token-level log probabilities and sequence entropy if available from the provider.
- Falls back to parsing self-reported confidence from TruthPrompt output schema if logprobs are unavailable.
- Computes `performance_score` and flags low-confidence token clusters.

#### 2. Responsibility Detection (`detectors/responsibility.py`)
- Scans candidate answer for PII leakage (emails, phone numbers, SSNs, credit cards, API keys).
- Matches against banned corporate policy keywords or restricted topics configured in `policy.yaml`.

#### 3. Cost & Spend Anomaly Detection (`detectors/cost.py`)
- Computes exact token cost (prompt tokens + completion tokens × model pricing).
- Updates rolling 1-hour and 24-hour spend window in SQLite.
- Flags anomaly if current request cost or rolling velocity deviates significantly from baseline.

---

## 3. Confidence State Machine & Decision Engine

Confidence is strictly **evidence-based**, never determined by tone or fluently asserted prose.

### Confidence State Transitions

| State | Conditions |
|---|---|
| **HIGH** | `performance_score` ≥ 0.80 (or self_rated ≥ 0.85), 0 PII entities, 0 policy hits, no spend anomaly. |
| **QUALIFIED** | `performance_score` between 0.50 and 0.79, minor non-sensitive policy warnings, or missing token logprobs with moderate self-rated score. |
| **LOW** | `performance_score` < 0.50, high token entropy, unverified factual claims, or detected data anomalies. |

### Decision Mapping (`app/decision.py` via `policy.yaml`)

```mermaid
graph TD
    Start["Evaluate (Confidence, Findings)"] --> PII_Hit{"PII or Critical Policy Hit?"}
    PII_Hit -->|Yes| BlockAction["Action: BLOCK<br/>Redact & Withhold Output"]
    PII_Hit -->|No| StateCheck{"Confidence State"}
    
    StateCheck -->|HIGH| AllowAction["Action: ALLOW<br/>Return Clean Answer"]
    StateCheck -->|QUALIFIED| FlagAction["Action: FLAG<br/>Append Warning Banner & Reasons"]
    StateCheck -->|LOW| LowCheck{"policy.yaml: block_on_low_confidence?"}
    
    LowCheck -->|True| BlockAction
    LowCheck -->|False| FlagAction
```

---

## 4. Data Contracts & Schema Reference

```python
# app/core_types.py

class IntakeResult(BaseModel):
    task: str
    context: str
    constraints: str
    expected_output: str
    source: Literal["inferred", "asked_user"]

class DetectionFindings(BaseModel):
    performance_score: Optional[float] = None
    self_rated_confidence: Optional[float] = None
    is_duplicate: bool = False
    spend_anomaly: bool = False
    pii_found: List[str] = Field(default_factory=list)
    policy_hits: List[str] = Field(default_factory=list)

class ConfidenceResult(BaseModel):
    state: Literal["HIGH", "QUALIFIED", "LOW"]
    reasons: List[str]

class Decision(BaseModel):
    action: Literal["ALLOW", "FLAG", "BLOCK"]
    reasons: List[str]
    warning_banner: Optional[str] = None

class ChatResponse(BaseModel):
    request_id: str
    model_used: str
    tier: Literal["cheap", "capable"]
    intake: IntakeResult
    findings: DetectionFindings
    confidence: ConfidenceResult
    decision: Decision
    content: Optional[str]
    cached: bool = False
    latency_ms: float
```

---

## 5. Persistence & Audit Logging (`app/db.py`)

Every single execution (allowed, flagged, blocked, or cached) writes a non-blocking trace record to SQLite:
- `request_id`, `timestamp`
- `raw_prompt`, `normalized_intake`
- `truth_prompt_version`
- `model_tier`, `provider_latency`
- `token_usage` (input, output, estimated cost)
- `detection_findings_json`
- `confidence_state`, `decision_action`
- `audit_reasons`

This enables complete post-hoc explainability: given any answer, engineers can instantly inspect the exact decision path and detector scores that authorized or flagged it.
