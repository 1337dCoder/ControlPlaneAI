# ControlPlane Wrapper — plan.md

## 0. Scope (read this first)

A thin wrapper service that sits between the user and an LLM API. Two stages, in order:

1. **Prevention** (before generation) — TruthPrompt + 4-question structured intake
2. **Detection** (after generation) — performance / cost / responsibility checks, then a confidence-gated decision

Not a new model. Not the full 11-stage blueprint. This is the minimum version of the two slides you uploaded, buildable in days not weeks. Everything cut is listed in §6, with reasoning in `context.md` §8 — nothing is cut because it's a bad idea, only because it isn't needed for v1.

---

## 1. Tech stack (minimal, fast to ship)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | fastest path to LLM SDKs + regex/NLP tooling |
| API | FastAPI, single process | one `/v1/chat` route, no microservices |
| LLM access | direct provider SDK behind a 20-line `providers.py` | swap to LiteLLM later *only if* you actually add a 2nd provider |
| Storage | SQLite (stdlib `sqlite3` or SQLModel) | zero ops, one file, enough for audit log + dedup cache + spend log |
| Dedup/embeddings | provider's embedding endpoint, or a local `sentence-transformers` model | pick one — don't build both |
| Config | `policy.yaml` | thresholds, banned patterns, model tiers — tune without redeploying |
| Frontend | one static HTML+JS page, no framework, served directly by FastAPI | enough to see the pipeline work — no build step, no npm, no separate deploy |

## 2. Folder structure

```
controlplane-wrapper/
├── app/
│   ├── main.py                # FastAPI app, /v1/chat endpoint, serves static/
│   ├── static/
│   │   └── index.html         # Day 7: single-page UI (chat + audit trail + review queue)
│   ├── truth_prompt.py        # Stage 1a: TruthPrompt template + builder
│   ├── intake.py               # Stage 1b: 4-question structured intake
│   ├── router.py                # tiered model routing (cheap vs capable)
│   ├── detectors/
│   │   ├── performance.py     # logprob/entropy confidence scan
│   │   ├── cost.py             # dedup cache + spend anomaly check
│   │   └── responsibility.py  # PII/secrets regex + policy ruleset
│   ├── confidence.py           # Stage 2: confidence state machine
│   ├── decision.py             # maps confidence+findings -> ALLOW/FLAG/BLOCK
│   ├── providers.py            # thin LLM client wrapper
│   ├── db.py                    # SQLite: conversations, audit, spend, dedup cache
│   └── policy.yaml              # thresholds, banned patterns, model tiers
├── tests/
│   ├── test_intake.py
│   ├── test_detectors.py
│   └── test_decision.py
├── requirements.txt
└── README.md
```

## 3. Data contracts — write these first, before any logic

```python
# app/core_types.py (Pydantic)

class IntakeResult(BaseModel):
    task: str
    context: str
    constraints: str
    expected_output: str
    source: Literal["inferred", "asked_user"]

class TruthPromptEnvelope(BaseModel):
    version: str                 # e.g. "truth_prompt_v1"
    known_facts: list[str]
    assumptions: list[str]
    unknowns: list[str]
    intake: IntakeResult
    confidence_threshold: float

class DetectionFindings(BaseModel):
    performance_score: float | None     # mean logprob / entropy, if available
    self_rated_confidence: float | None # fallback when no logprobs
    is_duplicate: bool
    spend_anomaly: bool
    pii_found: list[str]                # entity types found — always fixable by redaction
    policy_hits: list[PolicyHit]        # each hit tagged fixable or not, see below
    contradiction_detected: bool        # TruthPrompt's own verify step found the answer
                                         # actively disagrees with a known/supplied fact —
                                         # distinct from "unsupported" (§5 explains why)

class PolicyHit(BaseModel):
    rule_id: str
    fixable: bool   # True: apply a defined remediation and send. False: cannot be
                     # salvaged by editing — this rule can only ever lead to BLOCK.

class ConfidenceResult(BaseModel):
    state: Literal["HIGH", "QUALIFIED", "LOW"]
    reasons: list[str]

class Decision(BaseModel):
    action: Literal["ALLOW", "EDIT", "ESCALATE", "BLOCK"]
    reasons: list[str]
    edits_applied: list[str] = []   # e.g. ["redacted_pii", "appended_low_confidence_caveat"]
    review_id: str | None = None    # set when action == ESCALATE, points to the review_queue row
```

Locking these first means every module below can be built and unit-tested independently — that's what keeps this "practical" instead of a tangle.

## 4. Build order — 5 working days, vertical slices (each day ends in something runnable)

### Day 1 — Skeleton + TruthPrompt (Stage 1a)
- FastAPI app, `/v1/chat` endpoint, wired to a real (or stubbed) LLM call
- Write the TruthPrompt as a static, **versioned** system-prompt template: decompose → separate fact from assumption/inference/opinion → solve → verify → attach confidence → flag anything below threshold
- Prepend it to every outgoing request, no exceptions
- Fold the bias-neutral standing instruction into this same template (don't build a separate module for it — it's one paragraph in the TruthPrompt)
- **Done when:** you can inspect the exact payload sent to the model and see the TruthPrompt in it, every time

### Day 2 — Structured intake (Stage 1b)
- `intake.py`: given the raw user message, try to fill Task / Context / Constraints / Expected Output **silently, with rules first** — regex/keyword heuristics, zero extra LLM calls
- Only when genuinely ambiguous (message too short, missing a clear verb+object, multiple plausible readings) — either ask the user one clarifying question, or make a single cheap-tier model call to fill the gap. Pick one path per request, never both, to keep the token cost bounded
- Merge the result into the TruthPrompt envelope before generation
- **Done when:** a clear prompt gets zero extra round-trips, and a vague one gets exactly one

### Day 3 — Tiered routing + generation
- `router.py`: classify complexity using **rules only** (task type from intake, message length, presence of multi-step/reasoning keywords) — no LLM call spent on classification itself
- Two tiers to start: cheap/default model, capable model (only when rules say so: multi-step reasoning, high-stakes policy tag, or explicit user request for depth)
- Call the model through `providers.py`; capture text, token counts, latency, logprobs (if the provider exposes them)
- **Done when:** you can log, for a batch of test prompts, what fraction got routed to the cheap tier

### Day 4 — Detection stage
- `performance.py`: if logprobs are available, compute mean token logprob / entropy as a cheap first-pass filter; if not, fall back to asking the model to self-report a confidence number in its structured output (already part of the TruthPrompt format — no second call needed)
- `cost.py`: embed/hash the incoming request, check it against a small dedup cache (SQLite table, last N requests); on a near-duplicate, serve the cached answer instead of generating; also track a rolling spend counter and flag anomalies (sudden spike vs. rolling average)
- `responsibility.py`: regex/keyword scan for PII and secrets (emails, phone numbers, ID-like patterns, API-key-shaped strings) on both input and output; load `policy.yaml`'s banned-topic list and do plain string/regex matching — no ML classifier needed for v1
- **Done when:** each detector runs independently and returns a `DetectionFindings` object

### Day 5 — Confidence, decision, audit — wire it together
- `confidence.py`: combine detector outputs into one of **HIGH / QUALIFIED / LOW** — 3 states, deliberately simpler than a 5-state machine; widen later if you need it
- `decision.py`: a deterministic lookup, driven by `policy.yaml`, evaluated **in this priority order** — the order is the whole point, it's what keeps BLOCK from firing on mere uncertainty:
  1. **BLOCK** — fires *only* when something is confirmed wrong or unsafe *and* not fixable: `contradiction_detected == True`, or any `policy_hit` with `fixable == False`. This is deliberately the smallest, hardest-to-reach bucket. Withhold entirely, return a fixed reason code.
  2. **EDIT** — fires when a specific, fixable issue exists and nothing above fired: PII present → redact it; a `policy_hit` with `fixable == True` → apply its defined remediation; confidence is QUALIFIED (useful but has evidence gaps) → append a short caveat. All pure string manipulation on the already-generated text — no regeneration, no extra tokens. Send the edited answer.
  3. **ESCALATE** — fires when nothing above fired *and* confidence is LOW: not confirmed wrong, just genuinely insufficient evidence to know either way. This is a judgment call the system shouldn't make alone — see Day 6.
  4. **ALLOW** — nothing above fired and confidence is HIGH or QUALIFIED-with-caveat-already-applied → return normally.
- Log every stage's output (intake, TruthPrompt version, route taken, findings, confidence, decision, any edits applied) to the SQLite audit table
- Smoke-test five cases: (1) an ordinary question → ALLOW, (2) the same question asked twice → served from dedup cache, no 2nd model call, (3) a question containing a fake SSN/API key → EDIT (redacted), (4) a question where confidence is LOW but nothing is confirmed wrong → ESCALATE, (5) a case where the TruthPrompt's own verify step flags a contradiction → BLOCK

### Day 6 — Escalation / human-review path
This is the part that's easy to hand-wave, so build it concretely even though it's small:
- Add a `review_queue` SQLite table: `id, request, candidate_answer, findings, confidence, reasons, status (pending/approved/rejected), created_at, resolved_at`
- Two modes, pick based on your use case (both are cheap to support since it's the same table):
  - **Async / decision-support mode**: on ESCALATE, write the row, hold the HTTP response open (or return a `pending` status + `review_id` the caller polls), and expose a bare `POST /v1/review/{id}` endpoint taking `{"action": "approve"|"reject"|"edit", "note": str}` that a human calls. Fine for internal tools where a short wait is acceptable. Add a timeout (e.g. 2 minutes) that falls back to BLOCK if nobody responds — never leave a request hanging forever.
  - **Live-chat / synchronous mode**: you can't make an end user wait on a human. So ESCALATE here means: immediately auto-downgrade to the safest available action (apply the same redaction/caveat logic as EDIT, or BLOCK if nothing safe can be salvaged), deliver that to the user right away, and still write the full row to `review_queue` with status `pending`. A human reviews it later — not to gate that one message, but to catch policy/threshold problems and correct `policy.yaml` going forward.
- **Done when:** an ESCALATE case in async mode actually blocks on the `/v1/review/{id}` call and resolves correctly on approve/reject/timeout; an ESCALATE case in sync mode returns immediately with a downgraded-but-safe answer and still leaves a row a human can review afterward

### Day 7 — Minimal frontend
The point isn't a polished UI — it's making the pipeline's reasoning *visible*, since that's the whole product idea (a confident-but-wrong answer with no trail is exactly the failure mode this project exists to prevent). One static file, no framework, no build step:
- `app/static/index.html`: a single page, two panels
  - **Left — chat.** A text box, send button, message history. Calls `POST /v1/chat`, renders the returned answer (with its EDIT banner/caveat if one was applied, or a BLOCK/ESCALATE-pending message if it wasn't delivered plain).
  - **Right — live trail.** For the most recent request: intake (Task/Context/Constraints/Expected Output, and whether it was inferred or asked), TruthPrompt version, route chosen (cheap/capable), detector findings (performance score, duplicate hit, spend flag, PII types found, policy hits, contradiction flag), confidence state, and the final decision with its reasons. This is just rendering the `Decision`/`DetectionFindings`/`IntakeResult` JSON you're already returning from `/v1/chat` — no new backend logic, just display it.
- A second small tab or section: **review queue** — lists rows from `review_queue` with `status = pending`, each with Approve / Reject buttons that call `POST /v1/review/{id}`. This is what makes Day 6's human-review path actually usable by an actual human instead of only by curl.
- Serve it via FastAPI's `StaticFiles` mount at `/` — no separate frontend server, no CORS setup needed.
- **Done when:** you can open a browser, send a message, and watch the right-hand panel populate with the real intake/route/findings/decision for that exact request — and separately, see a pending ESCALATE item show up in the review queue and resolve it with one click.

## 5. Definition of done for v1

- [ ] Every request carries a TruthPrompt + structured intake before generation
- [ ] Ambiguous prompts trigger at most one clarifying step (ask or infer, never both)
- [ ] Routing sends the majority of simple test prompts to the cheap tier
- [ ] Duplicate/near-duplicate prompts are served from cache, not re-generated
- [ ] PII/secrets in input or output never reach the final response unredacted or unflagged
- [ ] EDIT actions (redaction, caveat) are applied deterministically without a second model call
- [ ] ESCALATE cases never silently fall through to ALLOW — they either genuinely wait for a human (async mode) or auto-downgrade to a safe action and get logged for later review (sync mode)
- [ ] The single-page UI shows the real intake/route/findings/decision trail for each request, and lets a human resolve a pending review with one click
- [ ] Every decision is logged with enough detail to reconstruct why it was made
- [ ] Low-confidence answers are visibly marked — never delivered as plain fact

## 6. Explicitly cut from v1 (why, in context.md §8)

- Grounding/RAG against a document corpus
- Multi-provider LiteLLM abstraction (single provider is enough for now)
- Postgres/pgvector/Redis (SQLite covers this scale)
- NeMo Guardrails / Presidio (regex rules cover the demo; swap in later without changing the contract)
- Multi-user/persistent dashboard with auth, history search, charts (Day 7's single-page UI covers seeing the live trail and resolving reviews — a real dashboard with accounts/analytics is still a later step)
- 5-state confidence machine (start with 3 — HIGH/QUALIFIED/LOW)
- Context-switch-awareness auto-offer ("start a fresh chat?") — nice-to-have, add once the core loop works