# ControlPlane Wrapper — context.md

This is the "why" document. `plan.md` tells you what to build and in what order; this explains why each piece exists, so decisions made under time pressure don't accidentally cut something load-bearing.

---

## 1. The problem, restated

LLMs give wrong answers **while sounding completely confident**, so nobody questions them until after a decision's already been made on it. Separately, teams routinely burn money using an expensive model for work a cheap one could do, and then burn more money again having employees manually double-check outputs. The wrapper's job is to catch both failure modes — wrong-but-confident, and expensive-but-unnecessary — before either one costs anything.

Everything below exists to serve one of those two goals. If a proposed feature doesn't clearly serve one of them, it doesn't belong in v1.

## 2. Core design principle

The wrapper is **a thin orchestration layer, not a new model**. It sits between the caller and the LLM API: pre-processes the request going in, post-processes the response coming out. This matters for three reasons:

- **Fast to ship.** You're not training or fine-tuning anything. You're writing deterministic code around an existing model call.
- **Replaceable internals.** The detectors (PII scan, dedup check, etc.) can be swapped for better versions later without touching the contract around them.
- **Explainable.** Everything downstream of "generate a candidate answer" should be deterministic rule-matching wherever possible, not another LLM call guessing at a judgment. A rule you can point to is a rule you can defend and debug; a second LLM call judging the first is just more surface area for the same failure mode.

## 3. Stage 1: Prevention

The idea behind Prevention is to catch problems **before** a token of the real answer is generated — because by the time you're checking the *output*, the expensive/risky work has already happened.

### 3a. TruthPrompt

A standing instruction injected ahead of every single query, with no exceptions. It tells the model to:

1. Decompose the request
2. Separate what it actually knows (verified fact) from what it's inferring, assuming, or guessing
3. Solve the task
4. Verify its own answer against what it separated out in step 2
5. Attach a confidence score
6. If that confidence is below threshold, **flag it** rather than present it as settled fact

This is the direct fix for "wrong answer, sounds confident" — the model is forced to show its own uncertainty instead of smoothing over it. It's versioned (`truth_prompt_v1`, `v2`, ...) so you can change the wording later and know exactly which version produced which historical answer — useful for debugging when behavior shifts.

The **bias-neutral standing instruction** (gender-neutral framing, no unsupported demographic assumptions) lives inside this same template rather than as a separate system. It's cheap to include and doesn't need its own detector — it's a prevention-side instruction, not a post-hoc check.

### 3b. Structured 4-question intake

Every raw user message gets normalized into four fields before the model is asked to answer anything: **Task, Context, Constraints, Expected Output**. (You described these as task/action/context/result in your message — same idea, this is just the naming used consistently across the slides and the existing blueprint, so the plan sticks with it.)

Why this exists: a huge fraction of wasted LLM spend is re-prompting — the model answers the wrong question, or answers a right-but-underspecified question, and you pay for a second round trip to fix it. Capturing these four fields up front means the model gets a fully-specified request on the *first* call.

The important design choice here is **how** these four fields get filled:

- **Silently inferred**, using cheap rule-based heuristics, whenever the request is clear enough — this costs zero extra tokens.
- **Asked directly**, as one clarifying question to the user, only when the request is genuinely ambiguous.

These two paths are mutually exclusive per request. The reason to never mix them: if you both guess *and* ask, you've spent the tokens of an extra round trip while also potentially asking the user something you could have inferred — worst of both. Pick one path and commit to it per request.

## 4. Stage 2: Detection

Detection runs on the **candidate answer**, after generation, and is grouped into three categories — matching the three groupings on your solution slide: Performance, Cost, Responsibility.

### 4a. Performance — logprob/entropy scan

This is the **cheapest possible first-pass filter**, applied to every single response. If the provider exposes token-level logprobs, a low mean logprob or high entropy on the generated tokens is a statistical signal that the model itself was "unsure" at the token level — independent of whether it *said* it was unsure in the TruthPrompt's self-reported confidence field. Cheap because it's math on numbers you already got back from the API call, not a second model call.

If logprobs aren't available (some providers don't expose them), the fallback is the self-rated confidence number the TruthPrompt already asked the model to produce — which is why that field exists in the output schema, not just as a nice-to-have.

Only when severity and confidence both cross a threshold does this escalate to something more expensive (in the full blueprint, a RAG grounding check — deliberately out of scope for v1, see §8).

### 4b. Cost — dedup interception + spend anomaly

Two checks, both aimed directly at the "burning money re-doing the same work" problem:

- **Semantic duplicate interception**: if a new request is a near-duplicate of a recent one, serve the cached answer instead of calling the model again. This is the single highest-leverage cost control in the whole system — it eliminates spend on repeat work entirely, rather than just routing it to a cheaper model.
- **Spend rate anomaly detection**: track a rolling counter of spend (tokens × price) and flag sudden spikes relative to the recent average. This catches runaway loops, retry storms, or a caller unexpectedly hammering the expensive tier — before it shows up as a surprise bill.

### 4c. Responsibility — PII/secrets + policy ruleset

Run on **both** input and output, because a leak can originate from either direction: the user pasting something sensitive into the prompt, or the model reproducing something sensitive in its answer. For v1 this is regex/keyword matching for obviously-shaped data (emails, phone numbers, ID-like strings, API-key-shaped strings) plus a small YAML ruleset of banned topics/phrases — deliberately not a full ML-based PII classifier (see §8 for why that’s deferred, not skipped).

This layer is described as "fastest available" for a reason: it should never be the bottleneck. A regex scan is milliseconds; it should run in parallel with, not after, the other detectors.

## 5. Confidence state machine + decision engine

Detector outputs get combined into one confidence state — **HIGH / QUALIFIED / LOW** for v1 (a simplified version of the 5-state VERIFIED/HIGH/QUALIFIED/LOW/UNVERIFIABLE machine in the full blueprint). The critical design rule, worth repeating because it's the whole point of the project: **confidence is evidence-based, never "the model sounded confident."** A fluent, assertive answer with a low logprob score or an unresolved PII hit is still LOW confidence — tone is not evidence.

The decision engine then maps confidence + findings → one of four actions, evaluated **in strict priority order**. The order matters more than any individual rule — it's what keeps BLOCK reserved for genuine wrongness instead of catching every uncertain case:

1. **BLOCK** — *"dangerous → stop it."* Fires **if and only if** something is confirmed wrong or unsafe *and* cannot be fixed by editing: the TruthPrompt's own verify step detected an actual contradiction against a known fact (not just an unsupported claim — see the distinction below), or a policy rule marked non-fixable fired. This is deliberately the narrowest bucket. It is not what fires on low confidence, on "we're not sure," or on a rule that could be fixed with a redaction — those go to EDIT or ESCALATE instead.
2. **EDIT** — *"small fix → auto-correct, send anyway."* Fires when a specific, fixable issue exists and nothing above fired: PII gets redacted, a fixable policy hit gets its defined remediation applied, or a QUALIFIED confidence state gets a short caveat appended. The core answer is still trustworthy once fixed — this is deterministic string manipulation on the already-generated text, no regeneration, no extra tokens.
3. **ESCALATE** — *"risky + unsure → human decides."* Fires only when nothing above fired and confidence is LOW: not confirmed wrong, just genuinely insufficient evidence to know either way. This is where a human belongs — not because the system found something bad, but because the system doesn't know, and guessing either way (ALLOW or BLOCK) would be worse than admitting the uncertainty. See §6 for how this is actually implemented.
4. **ALLOW** — nothing above fired; deliver as-is.

**Why "contradicted" and "unsupported" have to be different signals.** A claim with no evidence path either way (unsupported) is not the same as a claim that evidence actively disagrees with (contradicted). Confusing the two is exactly what causes over-blocking: most low-confidence answers aren't *wrong*, they're just *unverified* — and unverified deserves a human's judgment call (ESCALATE), while actually-contradicted deserves to be stopped (BLOCK). Conflating them either blocks too much (killing genuinely useful, merely-unverified answers) or escalates too little (letting confirmed-wrong answers through with just a caveat). The `contradiction_detected` flag exists specifically to keep these separate.

Deterministic here means: given the same findings twice, you get the same decision twice. That's what makes the system testable and explainable — you can write a unit test for "contradiction detected → BLOCK" and a separate one for "LOW confidence, no contradiction → ESCALATE" and know neither outcome will silently drift into the other.

## 6. Human involvement (the ESCALATE path)

It's easy to write "escalate to a human" on a slide and much harder to make it real in a small wrapper with no ops team watching a queue. The honest design has two modes, and which one applies depends entirely on whether the caller can tolerate waiting:

- **Async / decision-support use cases** (internal tools, back-office workflows) — a human genuinely *can* be in the loop, because nobody's staring at a chat window waiting on the reply. Here ESCALATE really does hold the response: the full record (request, candidate answer, findings, confidence, reasons) gets written to a review queue, and a human calls a one-line approve/reject/edit endpoint to resolve it. A timeout falls back to BLOCK rather than leaving the request hanging indefinitely — silence should never resolve to ALLOW.
- **Live chat** — a real person is waiting on the other end in real time, so genuinely blocking on human review isn't viable for v1. ESCALATE instead means: immediately apply the safest available fallback (the same redaction/caveat logic as EDIT, or BLOCK if nothing can be safely salvaged), deliver that right away, and *still* log the full record to the review queue. The human's role shifts from gatekeeping that one message to reviewing the log afterward and tightening `policy.yaml` so the same pattern is handled better next time.

The thing both modes share, and the reason this section exists at all: **ESCALATE must never silently degrade into ALLOW.** If nothing else is built yet, the fallback for "risky and unsure" is always "safer," never "delivered as if nothing happened."

## 7. Tiered model routing (cost lever)

Simple tasks (scraping, summarizing, reformatting) get routed to a lightweight/cheap model automatically. Only tasks that the intake step marked as genuinely complex reasoning consume premium-model tokens. This is the direct lever against the "sledgehammer model for a job a small one could handle" waste described in the problem statement — and it's a **rule-based** routing decision (task type, length, reasoning keywords from the intake step), not an LLM call, so classifying which tier to use doesn't itself burn tokens.

## 8. What's deferred for v1, and why

Everything below is cut **only** because of the time constraint, not because it's wrong — each one maps onto the fuller pipeline in the original blueprint and can be added later without changing the core contract (TruthPrompt → intake → route → generate → detect → confidence → decision → audit):

| Deferred | Why it's safe to defer |
|---|---|
| RAG/document grounding | Needs a document corpus + vector store; the performance detector's logprob/entropy scan already catches a meaningful share of low-confidence cases without it |
| Multi-provider abstraction (LiteLLM) | You only need one provider to prove the pipeline works; add abstraction when you actually have a second provider to route to |
| Postgres/pgvector/Redis | SQLite handles audit logs, dedup cache, and spend tracking at demo scale with zero ops overhead |
| NeMo Guardrails / Presidio | Regex + keyword rules cover the PII/policy demo cases; swap in a proper library later — the `responsibility.py` module's interface doesn't need to change |
| Multi-user dashboard (auth, history search, charts) | The Day 7 single-page UI already makes the pipeline's reasoning visible and lets a human resolve reviews — a persistent, multi-user dashboard is a scale problem, not a demo problem |
| 5-state confidence machine | 3 states (HIGH/QUALIFIED/LOW) cover the same "don't present low-confidence as fact" behavior with a smaller decision table to test |
| Context-switch-awareness auto-offer | A genuine nice-to-have, not part of the two core stages — add once Prevention and Detection are both working end-to-end |

## 9. Glossary

- **TruthPrompt** — the versioned standing system-prompt template injected ahead of every query; the "core IP" of the wrapper.
- **Intake** — the Task/Context/Constraints/Expected Output normalization step, done silently or by asking, never both, per request.
- **Detector** — an independent, swappable module that inspects a request or response and returns structured findings (not a decision).
- **Confidence state** — HIGH / QUALIFIED / LOW; an evidence-based summary of how much the combined detector findings support the answer.
- **Decision** — ALLOW / FLAG / BLOCK; the deterministic outcome of applying `policy.yaml`'s rules to a confidence state + findings.
- **Audit record** — the full trace (intake, TruthPrompt version, route, findings, confidence, decision) logged for every request, so any output can be explained after the fact.