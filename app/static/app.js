document.addEventListener("DOMContentLoaded", () => {
  initChatInput();
  initSidebar();
  fetchHealth();
  fetchAuditLogs();
  fetchReviewQueue();

  // Hidden Developer Mode Toggle
  const proxyTitle = document.getElementById("proxy-title");
  if (proxyTitle) {
    let clicks = 0;
    proxyTitle.addEventListener("click", () => {
      clicks++;
      if (clicks >= 2) {
        document.body.classList.toggle("dev-mode");
        clicks = 0;
      }
      setTimeout(() => clicks = 0, 1000);
    });
  }
});

const STARTER_PROMPTS = {
  normal: "Explain the time complexity of quicksort in markdown with best, average, and worst cases.",
  dedup: "Explain the time complexity of quicksort in markdown with best, average, and worst cases.",
  pii: "My email is test@company.internal and API key is sk-1234567890abcdef1234567890abcdef. Please save my credentials.",
  proof: "Provide a formal step-by-step mathematical proof of the convergence of gradient descent with Lipschitz continuous gradients."
};

function useStarterPrompt(key) {
  const promptInput = document.getElementById("user-prompt");
  if (STARTER_PROMPTS[key]) {
    promptInput.value = STARTER_PROMPTS[key];
    promptInput.focus();
    autoResizeTextarea(promptInput);
  }
}

let conversationPrompts = [];
let pendingTopicPrompt = "";

function checkTopicShift(newPrompt) {
  if (conversationPrompts.length === 0) return false;
  const lastPrompt = conversationPrompts[conversationPrompts.length - 1];

  const stopWords = new Set([
    'the','a','an','is','are','was','were','in','on','at','to','for','of','with',
    'how','what','why','who','where','when','can','you','please','explain','tell',
    'give','me','do','does','did','and','or','but','if','then','as','my','it','its','this','that'
  ]);

  const extractKeywords = (str) => {
    return new Set(
      str.toLowerCase()
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length > 2 && !stopWords.has(w))
    );
  };

  const setA = extractKeywords(lastPrompt);
  const setB = extractKeywords(newPrompt);

  if (setA.size >= 2 && setB.size >= 2) {
    let intersection = 0;
    for (const item of setB) {
      if (setA.has(item)) intersection++;
    }
    const union = new Set([...setA, ...setB]).size;
    const similarity = union > 0 ? intersection / union : 1;
    // If less than 15% keyword overlap, a topic shift occurred
    return similarity < 0.15;
  }
  return false;
}

function showTopicOffer(newPrompt) {
  pendingTopicPrompt = newPrompt;
  const popup = document.getElementById("topic-switch-popup");
  if (popup) {
    popup.style.display = "block";
  }
}

function dismissTopicOffer() {
  const popup = document.getElementById("topic-switch-popup");
  if (popup) {
    popup.style.display = "none";
  }
}

function acceptNewChatOffer() {
  dismissTopicOffer();
  resetToNewChat();
}

function resetToNewChat() {
  conversationPrompts = [];
  dismissTopicOffer();
  switchView('chat');
  const messagesList = document.getElementById("messages-list");
  messagesList.innerHTML = "";
  document.getElementById("welcome-hero").style.display = "flex";
  document.getElementById("user-prompt").value = "";
  document.getElementById("user-prompt").focus();
}

function switchView(viewName) {
  document.querySelectorAll(".view-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));

  const targetPanel = document.getElementById(`view-${viewName}`);
  const targetNav = document.querySelector(`.nav-item[data-view="${viewName}"]`);
  const chatDock = document.getElementById("chat-dock");

  if (targetPanel) targetPanel.classList.add("active");
  if (targetNav) targetNav.classList.add("active");

  if (viewName === "chat") {
    chatDock.style.display = "block";
  } else {
    chatDock.style.display = "none";
  }

  if (viewName === "audit") {
    fetchAuditLogs();
  } else if (viewName === "review") {
    fetchReviewQueue();
  }
}

function initSidebar() {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", () => {
      const view = item.getAttribute("data-view");
      if (view) switchView(view);
    });
  });
}

function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function initChatInput() {
  const textarea = document.getElementById("user-prompt");
  const form = document.getElementById("chat-form");
  if (!textarea || !form) return;

  textarea.addEventListener("input", () => autoResizeTextarea(textarea));

  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      document.getElementById("btn-send").click();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = textarea.value.trim();
    if (!prompt) return;

    // Check for topic switch
    if (checkTopicShift(prompt)) {
      showTopicOffer(prompt);
      return;
    }

    conversationPrompts.push(prompt);
    const modelOverride = document.getElementById("tier-select").value || null;

    // Hide hero
    document.getElementById("welcome-hero").style.display = "none";

    // Append User Message Bubble
    appendUserMessage(prompt);
    textarea.value = "";
    autoResizeTextarea(textarea);

    // Append Loading Assistant Card
    const loadingId = appendLoadingAssistant();
    const sendBtn = document.getElementById("btn-send");
    sendBtn.disabled = true;

    try {
      const payload = {
        prompt: prompt,
        user_id: "demo_user",
        model_override: modelOverride
      };

      const res = await fetch("/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`API returned HTTP ${res.status}`);
      }

      const data = await res.json();
      replaceLoadingWithResponse(loadingId, data);
      fetchAuditLogs();
    } catch (err) {
      const loadingEl = document.getElementById(loadingId);
      if (loadingEl) {
        loadingEl.innerHTML = `<div class="blocked-callout">⚠️ Error: ${err.message}</div>`;
      }
    } finally {
      sendBtn.disabled = false;
      sendBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      `;
      textarea.focus();
    }
  });
}

function appendUserMessage(text) {
  const list = document.getElementById("messages-list");
  const row = document.createElement("div");
  row.className = "message-row";
  row.innerHTML = `
    <div class="message-user">${escapeHtml(text)}</div>
  `;
  list.appendChild(row);
  scrollToBottom();
}

function appendLoadingAssistant() {
  const list = document.getElementById("messages-list");
  const row = document.createElement("div");
  const id = `msg-loading-${Date.now()}`;
  row.className = "message-row";
  row.id = id;
  row.innerHTML = `
    <div class="message-assistant">
      <div style="display: flex; align-items: center; gap: 0.75rem; color: var(--text-secondary); font-size: 0.88rem;">
        <div class="pill-dot"></div>
        <span>Evaluating prevention rules, deduplication cache, and model tier...</span>
      </div>
    </div>
  `;
  list.appendChild(row);
  scrollToBottom();
  return id;
}

function replaceLoadingWithResponse(loadingId, resp) {
  const row = document.getElementById(loadingId);
  if (!row) return;

  const actionClass = resp.decision.action.toLowerCase();
  const confClass = resp.confidence.state.toLowerCase();
  const score = resp.findings.performance_score || resp.findings.self_rated_confidence || 1.0;

  // Badges Header
  let badgesHtml = `
    <span class="cp-pill cp-pill-${actionClass}">DECISION: ${resp.decision.action}</span>
    <span class="cp-pill cp-pill-tier">${resp.tier.toUpperCase()} (${resp.model_used})</span>
    <span class="cp-pill" style="color: var(--pink-light); background: var(--pink-soft);">CONFIDENCE: ${resp.confidence.state} (${(score * 100).toFixed(0)}%)</span>
  `;

  if (resp.cached) {
    badgesHtml += `<span class="cp-pill cp-pill-cache">DEDUP CACHE HIT (0 Tokens)</span>`;
  }
  if (resp.decision.edits_applied && resp.decision.edits_applied.length > 0) {
    badgesHtml += `<span class="cp-pill cp-pill-edit">EDITS: ${resp.decision.edits_applied.join(", ")}</span>`;
  }
  if (resp.decision.review_id) {
    badgesHtml += `<span class="cp-pill cp-pill-escalate">REVIEW QUEUED: ${resp.decision.review_id}</span>`;
  }

  // Warning Banner or Block Notice
  let calloutHtml = "";
  if (resp.decision.action === "BLOCK") {
    calloutHtml = `<div class="blocked-callout">${escapeHtml(resp.decision.reasons.join("; "))}</div>`;
  } else if (resp.decision.warning_banner) {
    calloutHtml = `<div class="warning-callout">${escapeHtml(resp.decision.warning_banner)}</div>`;
  }

  // Response Text Content or Clarification Form
  let contentHtml = "";
  if (resp.decision.action === "ASK_USER" && resp.decision.clarifying_questions && resp.decision.clarifying_questions.length > 0) {
    const qHtml = resp.decision.clarifying_questions.map((q, i) => `
      <div style="margin-bottom: 0.75rem;">
        <label style="display: block; font-size: 0.85rem; color: var(--blue-light); margin-bottom: 0.25rem;">${escapeHtml(q)}</label>
        <input type="text" class="clarification-input" data-q="${escapeHtml(q)}" style="width: 100%; padding: 0.5rem; background: rgba(0,0,0,0.2); border: 1px solid var(--border-medium); border-radius: 4px; color: white;" placeholder="Your answer...">
      </div>
    `).join("");
    
    contentHtml = `
      <div class="assistant-prose">${renderMarkdown(resp.content || "I need some clarification:")}</div>
      <div class="clarification-form" style="margin-top: 1rem; background: var(--bg-surface-elevated); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--border-medium);">
        ${qHtml}
        <button onclick="submitClarifications(this, '${escapeHtml(resp.intake.task)}')" style="margin-top: 0.5rem; padding: 0.5rem 1rem; background: var(--pink-primary); border: none; border-radius: 4px; color: white; cursor: pointer; font-weight: 600;">Submit Clarifications</button>
      </div>
    `;
  } else {
    contentHtml = `<div class="assistant-prose">${renderMarkdown(resp.content || "")}</div>`;
  }

  // Collapsible Inspection Drawer
  const drawerId = `drawer-${Date.now()}`;
  const inspectionHtml = `
    <div class="pipeline-drawer" id="${drawerId}">
      <button class="pipeline-drawer-toggle" onclick="toggleDrawer('${drawerId}')">
        <span>ControlPlane Inspection Pipeline Details</span>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Latency: ${resp.latency_ms}ms • Tokens: ${resp.tokens_used} ▾</span>
      </button>
      <div class="pipeline-drawer-content">
        <div class="drawer-grid">
          <div class="drawer-col">
            <h4>1. Stage 1: Prevention</h4>
            <p><strong>Intake Task:</strong> ${escapeHtml(resp.intake.task || "(Auto-inferred)")}</p>
            <p><strong>Context/Constraints:</strong> ${escapeHtml(resp.intake.context || "None")} / ${escapeHtml(resp.intake.constraints || "None")}</p>
            <p><strong>Dedup Status:</strong> ${resp.cached ? 'Hit (0 token spend)' : 'Miss (Fresh execution)'}</p>
          </div>
          <div class="drawer-col">
            <h4>2. Router & Provider</h4>
            <p><strong>Tier Selected:</strong> ${resp.tier} (via deterministic rule)</p>
            <p><strong>Model:</strong> <code>${resp.model_used}</code></p>
            <p><strong>Est. Cost:</strong> $${resp.estimated_cost_usd} USD</p>
          </div>
          <div class="drawer-col">
            <h4>3. Stage 2: Detection</h4>
            <p><strong>Statistical Certainty:</strong> ${(score * 100).toFixed(1)}%</p>
            <p><strong>PII Detected:</strong> ${resp.findings.pii_found.length > 0 ? resp.findings.pii_found.join(", ") : 'None'}</p>
            <p><strong>Policy Triggers:</strong> ${resp.findings.policy_hits.length > 0 ? resp.findings.policy_hits.join(", ") : 'None'}</p>
          </div>
        </div>
        ${resp.final_system_prompt ? `
        <div class="drawer-prompts" style="margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
          <h4>4. Final Constructed Prompt (Sent to LLM)</h4>
          <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05); padding: 0.75rem; border-radius: 6px; margin-top: 0.5rem;">
            <p style="margin-bottom: 0.25rem; color: var(--pink-light); font-size: 0.8rem; font-weight: 600;">SYSTEM PROMPT (TruthPrompt Envelope):</p>
            <pre style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary); white-space: pre-wrap; margin: 0 0 1rem 0;">${escapeHtml(resp.final_system_prompt)}</pre>
            <p style="margin-bottom: 0.25rem; color: var(--blue-light); font-size: 0.8rem; font-weight: 600;">USER PROMPT:</p>
            <pre style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-secondary); white-space: pre-wrap; margin: 0;">${escapeHtml(resp.final_user_prompt || "")}</pre>
          </div>
        </div>
        ` : ''}
      </div>
    </div>
  `;

  row.innerHTML = `
    <div class="message-assistant">
      <div class="cp-meta-header">
        <div class="cp-badges-row">${badgesHtml}</div>
        <span style="font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted);">${resp.latency_ms} ms</span>
      </div>
      ${inspectionHtml}
      ${calloutHtml}
      ${contentHtml}
    </div>
  `;

  // Render LaTeX Math with KaTeX
  if (window.renderMathInElement) {
    const proseEl = row.querySelector(".assistant-prose");
    if (proseEl) {
      renderMathInElement(proseEl, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true }
        ],
        throwOnError: false
      });
    }
  }

  scrollToBottom();
}

function toggleDrawer(id) {
  const drawer = document.getElementById(id);
  if (drawer) {
    drawer.classList.toggle("open");
  }
}

function scrollToBottom() {
  const container = document.querySelector(".chat-stream-container");
  container.scrollTop = container.scrollHeight;
}

// Fetch health
async function fetchHealth() {
  try {
    const res = await fetch("/health");
    if (res.ok) {
      const data = await res.json();
      document.getElementById("header-status-text").textContent = `Proxy Active (${data.database})`;
    }
  } catch (e) {
    document.getElementById("header-status-text").textContent = "Proxy Offline";
  }
}

// Fetch Audit Traces & Update Sidebar Metrics
async function fetchAuditLogs() {
  try {
    const res = await fetch("/audit?limit=20");
    if (!res.ok) return;
    const logs = await res.json();

    const tbody = document.getElementById("audit-rows");
    if (!tbody) return;

    if (!logs || logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">No audit records found.</td></tr>';
      return;
    }

    let cacheCount = 0;
    let total = logs.length;
    let totalSpend = 0;

    tbody.innerHTML = "";
    logs.forEach(log => {
      if (log.cached) cacheCount++;
      totalSpend += (log.estimated_cost_usd || 0);

      const tr = document.createElement("tr");
      const timeStr = log.timestamp ? log.timestamp.split("T")[1]?.slice(0, 8) || log.timestamp : "--";
      const action = (log.decision_action || "ALLOW").toLowerCase();
      
      tr.innerHTML = `
        <td style="font-family: var(--font-mono); color: var(--text-muted);">${timeStr}</td>
        <td style="font-family: var(--font-mono); font-size: 0.78rem;">${log.request_id.slice(0, 8)}...</td>
        <td><span class="cp-pill cp-pill-${action}">${log.decision_action}</span></td>
        <td><span class="cp-pill" style="background: rgba(255,255,255,0.05);">${log.confidence_state}</span></td>
        <td><code>${log.model_name || log.model_tier}</code></td>
        <td>${log.cached ? '<span style="color: var(--blue-light); font-weight: 600;">HIT (0 tok)</span>' : '<span style="color: var(--text-muted);">MISS</span>'}</td>
        <td style="font-family: var(--font-mono);">${parseFloat(log.latency_ms || 0).toFixed(1)}ms</td>
        <td style="max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(log.raw_prompt || "")}</td>
      `;
      tbody.appendChild(tr);
    });

    const cachePercent = total > 0 ? Math.round((cacheCount / total) * 100) : 0;
    const sideCache = document.getElementById("side-cache-rate");
    if (sideCache) {
      sideCache.textContent = `${cachePercent}% (${cacheCount} queries)`;
    }

    const sideSpend = document.getElementById("side-spend-val");
    if (sideSpend) {
      sideSpend.textContent = `$${totalSpend.toFixed(4)} / $10.00`;
    }

  } catch (e) {
    console.error("Failed to load audit logs", e);
  }
}

function renderMarkdown(str) {
  if (!str) return "";
  if (typeof marked !== "undefined") {
    try {
      marked.setOptions({
        gfm: true,
        breaks: true,
        highlight: function(code, lang) {
          if (typeof hljs !== "undefined") {
            const validLanguage = hljs.getLanguage(lang) ? lang : 'plaintext';
            return hljs.highlight(code, { language: validLanguage }).value;
          }
          return code;
        }
      });
      return marked.parse(str);
    } catch (e) {
      console.warn("Marked parse error, fallback to escapeHtml", e);
    }
  }
  return escapeHtml(str);
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function submitClarifications(btn, originalTask) {
  const form = btn.parentElement;
  const inputs = form.querySelectorAll(".clarification-input");
  let enrichedPrompt = `Original Request: ${originalTask}\n\n`;
  
  let allAnswered = true;
  inputs.forEach(input => {
    const q = input.getAttribute("data-q");
    const a = input.value.trim();
    if (!a) {
      allAnswered = false;
      input.style.borderColor = "var(--pink-primary)";
    } else {
      input.style.borderColor = "var(--border-medium)";
      enrichedPrompt += `Q: ${q}\nA: ${a}\n\n`;
    }
  });

  if (!allAnswered) return;

  btn.disabled = true;
  btn.textContent = "Submitting...";

  // Append User Message Bubble
  appendUserMessage("Clarification Provided");
  
  // Append Loading Assistant Card
  const loadingId = appendLoadingAssistant();

  const modelOverride = document.getElementById("tier-select").value || null;

  try {
    const payload = {
      prompt: enrichedPrompt,
      user_id: "demo_user",
      model_override: modelOverride,
      metadata: { is_clarification_response: true }
    };

    const res = await fetch("/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      throw new Error(`API returned HTTP ${res.status}`);
    }

    const data = await res.json();
    replaceLoadingWithResponse(loadingId, data);
    fetchAuditLogs();
    
    // Disable the old form
    form.innerHTML = `<p style="color: var(--color-allow); font-size: 0.85rem; font-weight: 600;">Clarifications submitted successfully.</p>`;
  } catch (err) {
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) {
      loadingEl.innerHTML = `<div class="blocked-callout">Error: ${err.message}</div>`;
    }
    btn.disabled = false;
    btn.textContent = "Submit Clarifications";
  }
}

// --- REVIEW QUEUE DASHBOARD (Day 7) ---

let currentReviewFilter = "all";

async function fetchReviewQueue(status = currentReviewFilter) {
  currentReviewFilter = status;
  const container = document.getElementById("review-cards-container");
  if (!container) return;

  try {
    const query = status === "all" ? "" : `?status=${status}`;
    const res = await fetch(`/v1/reviews${query}`);
    if (!res.ok) throw new Error("Failed to fetch reviews");
    const data = await res.json();
    const reviews = data.reviews || [];

    // Update pending badge in sidebar
    const pendingCount = reviews.filter(r => r.status === "pending").length;
    const badge = document.getElementById("nav-review-badge");
    if (badge) {
      if (pendingCount > 0) {
        badge.textContent = pendingCount;
        badge.style.display = "inline-block";
      } else {
        badge.style.display = "none";
      }
    }

    if (reviews.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; color: var(--text-muted); padding: 3rem; background: var(--bg-surface); border-radius: var(--radius-md); border: 1px solid var(--border-subtle);">
          No ${status === 'all' ? '' : status} items in the human review queue.
        </div>
      `;
      return;
    }

    container.innerHTML = reviews.map(r => {
      const isPending = r.status === "pending";
      const statusPill = isPending
        ? `<span class="cp-pill cp-pill-escalate">STATUS: PENDING REVIEW</span>`
        : `<span class="cp-pill cp-pill-allow">STATUS: ${r.status.toUpperCase()}</span>`;

      return `
        <div class="review-card" id="card-${r.id}">
          <div class="review-card-header">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span style="font-weight: 700; color: #fff;">Review ID: ${r.id}</span>
              ${statusPill}
            </div>
            <span style="font-size: 0.75rem;">${formatTime(r.created_at)}</span>
          </div>

          <div>
            <div style="font-size: 0.75rem; color: var(--blue-light); font-weight: 600; margin-bottom: 0.35rem;">USER PROMPT</div>
            <div class="review-prompt-box">${escapeHtml(r.raw_prompt)}</div>
          </div>

          <div>
            <div style="font-size: 0.75rem; color: var(--pink-light); font-weight: 600; margin-bottom: 0.35rem;">CANDIDATE ANSWER</div>
            <div class="review-answer-box">${escapeHtml(r.candidate_answer)}</div>
          </div>

          <div style="font-size: 0.8rem; color: var(--text-muted);">
            <strong>Reason:</strong> ${escapeHtml((r.reasons || []).join("; "))}
          </div>

          ${isPending ? `
            <div class="review-actions-row">
              <input type="text" class="review-note-input" id="note-${r.id}" placeholder="Optional reviewer feedback/reason...">
              <button class="btn-approve" onclick="resolveReview('${r.id}', 'approve', this)">Approve</button>
              <button class="btn-reject" onclick="resolveReview('${r.id}', 'reject', this)">Reject</button>
            </div>
          ` : `
            <div style="font-size: 0.8rem; color: var(--text-secondary); padding-top: 0.5rem; border-top: 1px solid var(--border-subtle);">
              <strong>Resolution:</strong> ${r.status.toUpperCase()} ${r.reviewer_note ? `— <em>"${escapeHtml(r.reviewer_note)}"</em>` : ''} 
              <span style="color: var(--text-muted); font-size: 0.72rem; margin-left: 0.5rem;">(${formatTime(r.resolved_at)})</span>
            </div>
          `}
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("Failed to load review queue", e);
  }
}

function filterReviewQueue(status, btn) {
  document.querySelectorAll("#view-review .filter-pill").forEach(p => p.classList.remove("active"));
  if (btn) btn.classList.add("active");
  fetchReviewQueue(status);
}

async function resolveReview(reviewId, action, btn) {
  const row = btn.closest(".review-actions-row");
  const noteInput = document.getElementById(`note-${reviewId}`);
  const note = noteInput ? noteInput.value.trim() : "";

  btn.disabled = true;
  btn.textContent = "...";

  try {
    const res = await fetch(`/v1/review/${reviewId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, note: note })
    });

    if (!res.ok) throw new Error("Resolution failed");
    fetchReviewQueue(currentReviewFilter);
  } catch (e) {
    alert(`Failed to resolve review: ${e.message}`);
    btn.disabled = false;
    btn.textContent = action.charAt(0).toUpperCase() + action.slice(1);
  }
}
