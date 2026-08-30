/**
 * ControlPlane AI — Claude-Inspired Interactive Client Logic
 * Features: Typewriter streaming animation, Live Reasoning Inspector Drawer, 
 * Markdown/KaTeX rendering, Review Queue resolution, Topic Switch Auto-Offer.
 */

let conversationPrompts = [];
let pendingTopicPrompt = "";
let lastResponseData = null;
let activeInspectorTab = "summary";

function getApiBaseUrl() {
  const custom = localStorage.getItem("cp_backend_url");
  if (custom) return custom.replace(/\/$/, "");
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.hostname.startsWith("192.168.")) {
    return "";
  }
  // Default to local network IP when on Firebase Hosting if not specified
  return "http://192.168.1.33:8000";
}

function promptForBackendUrl() {
  const current = localStorage.getItem("cp_backend_url") || "http://192.168.1.33:8000";
  const url = prompt("Enter ControlPlane Backend Proxy URL (e.g. http://192.168.1.33:8000 or your Cloud URL):", current);
  if (url !== null) {
    localStorage.setItem("cp_backend_url", url.trim());
    fetchHealth();
    fetchAuditLogs();
    fetchReviewQueue();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initHeroGreeting();
  initChatInput();
  initSidebar();
  fetchHealth();
  fetchAuditLogs();
  fetchReviewQueue();

  // Configure Marked for code highlighting
  if (window.marked) {
    marked.setOptions({
      highlight: function (code, lang) {
        if (window.hljs && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return code;
      },
      breaks: true,
      gfm: true
    });
  }
});

function initHeroGreeting() {
  const greetingEl = document.getElementById("hero-greeting");
  if (!greetingEl) return;
  const hour = new Date().getHours();
  let text = "Good evening";
  if (hour >= 5 && hour < 12) text = "Good morning";
  else if (hour >= 12 && hour < 17) text = "Good afternoon";
  else if (hour >= 17 && hour < 22) text = "Good evening";
  else text = "Good night";
  greetingEl.innerText = text;
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (sidebar) {
    sidebar.classList.toggle("collapsed");
  }
}

function toggleInspectorPanel(data = null) {
  const drawer = document.getElementById("inspector-drawer");
  const toggleBtn = document.getElementById("btn-inspector-toggle");
  if (!drawer) return;

  if (data) {
    lastResponseData = data;
    renderInspectorContent();
    drawer.classList.add("open");
    if (toggleBtn) toggleBtn.classList.add("active");
    return;
  }

  drawer.classList.toggle("open");
  if (toggleBtn) toggleBtn.classList.toggle("active", drawer.classList.contains("open"));
  if (drawer.classList.contains("open") && lastResponseData) {
    renderInspectorContent();
  }
}

function switchInspectorTab(tabName, btn) {
  activeInspectorTab = tabName;
  document.querySelectorAll(".insp-tab-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderInspectorContent();
}

function renderInspectorContent() {
  const body = document.getElementById("inspector-body");
  if (!body) return;

  if (!lastResponseData) {
    body.innerHTML = `
      <div class="inspector-empty">
        <p>Send a prompt to inspect live 4-question intake, TruthPrompt envelope, model telemetry, and deterministic decision rules.</p>
      </div>
    `;
    return;
  }

  const d = lastResponseData;

  if (activeInspectorTab === "summary") {
    body.innerHTML = `
      <div class="insp-card">
        <div class="insp-card-title">
          <span>Decision Overview</span>
          <span class="cp-pill cp-pill-${d.decision.action.toLowerCase()}">${d.decision.action}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Confidence State</span>
          <span class="insp-val" style="color: var(--pink-light);">${d.confidence.state}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Model / Tier</span>
          <span class="insp-val">${d.tier.toUpperCase()} (${d.model_used})</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Tokens Consumed</span>
          <span class="insp-val">${d.tokens_used} tokens</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Estimated Cost</span>
          <span class="insp-val">$${(d.estimated_cost_usd || 0).toFixed(6)} USD</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Pipeline Latency</span>
          <span class="insp-val">${d.latency_ms} ms</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Cache Status</span>
          <span class="insp-val">${d.cached ? "⚡ DEDUP HIT (0 tokens)" : "Generation Miss"}</span>
        </div>
      </div>

      <div class="insp-card">
        <div class="insp-card-title">Deterministic Reasons</div>
        <ul style="margin-left: 1.25rem; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6;">
          ${(d.decision.reasons || []).map(r => `<li>${escapeHtml(r)}</li>`).join("")}
        </ul>
      </div>
    `;
  } else if (activeInspectorTab === "stage1") {
    body.innerHTML = `
      <div class="insp-card">
        <div class="insp-card-title">4-Question Structured Intake</div>
        <div class="insp-kv-row">
          <span class="insp-key">Task</span>
          <span class="insp-val">${escapeHtml(d.intake.task || "N/A")}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Context</span>
          <span class="insp-val">${escapeHtml(d.intake.context || "Not specified")}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Constraints</span>
          <span class="insp-val">${escapeHtml(d.intake.constraints || "Strict facts")}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Expected Output</span>
          <span class="insp-val">${escapeHtml(d.intake.expected_output || "Text")}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Extraction Source</span>
          <span class="insp-val" style="color: var(--blue-light);">${d.intake.source}</span>
        </div>
      </div>

      <div class="insp-card">
        <div class="insp-card-title">TruthPrompt Envelope</div>
        <div class="insp-kv-row">
          <span class="insp-key">Version</span>
          <span class="insp-val">truth_prompt_v1</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Decomposition</span>
          <span class="insp-val">Fact / Assumption / Inference Separation</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Routing Rule</span>
          <span class="insp-val">${d.tier === 'capable' ? 'Complex proof / reasoning keywords triggered capable tier' : 'Default cheap tier applied'}</span>
        </div>
      </div>
    `;
  } else if (activeInspectorTab === "stage2") {
    body.innerHTML = `
      <div class="insp-card">
        <div class="insp-card-title">Detection Findings</div>
        <div class="insp-kv-row">
          <span class="insp-key">Performance / Entropy Score</span>
          <span class="insp-val">${(d.findings.performance_score || d.findings.self_rated_confidence || 1.0).toFixed(2)}</span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">PII Entities Detected</span>
          <span class="insp-val" style="color: ${d.findings.pii_found && d.findings.pii_found.length ? 'var(--pink-light)' : 'var(--text-muted)'};">
            ${d.findings.pii_found && d.findings.pii_found.length ? d.findings.pii_found.join(', ') : 'None (Clean)'}
          </span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Policy Rule Violations</span>
          <span class="insp-val" style="color: ${d.findings.policy_hits && d.findings.policy_hits.length ? 'var(--color-block)' : 'var(--text-muted)'};">
            ${d.findings.policy_hits && d.findings.policy_hits.length ? d.findings.policy_hits.join(', ') : 'None'}
          </span>
        </div>
        <div class="insp-kv-row">
          <span class="insp-key">Spend Anomaly Alarm</span>
          <span class="insp-val">${d.findings.spend_anomaly ? '🚨 ANOMALY FLAGGED' : 'Normal Rate'}</span>
        </div>
      </div>

      <div class="insp-card">
        <div class="insp-card-title">Applied In-Memory Edits</div>
        <div style="font-size: 0.82rem; color: var(--text-secondary);">
          ${d.decision.edits_applied && d.decision.edits_applied.length ? 
            `<ul style="margin-left: 1.25rem;">${d.decision.edits_applied.map(e => `<li><code>${e}</code></li>`).join('')}</ul>` : 
            'No modifications required.'}
        </div>
      </div>
    `;
  } else if (activeInspectorTab === "json") {
    body.innerHTML = `
      <pre class="insp-json-pre">${escapeHtml(JSON.stringify(d, null, 2))}</pre>
    `;
  }
}

const STARTER_PROMPTS = {
  normal: "Explain the time complexity of quicksort in markdown with best, average, and worst cases.",
  dedup: "Explain the time complexity of quicksort in markdown with best, average, and worst cases.",
  pii: "My email is test@company.internal and SSN is 000-12-3456 and API key is sk-1234567890abcdef1234567890abcdef. Please assist.",
  proof: "Provide a step-by-step mathematical proof of the convergence of gradient descent with Lipschitz continuous gradients."
};

function useStarterPrompt(key) {
  const promptInput = document.getElementById("user-prompt");
  if (STARTER_PROMPTS[key]) {
    promptInput.value = STARTER_PROMPTS[key];
    promptInput.focus();
    autoResizeTextarea(promptInput);
  }
}

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
    return similarity < 0.15;
  }
  return false;
}

function showTopicOffer(newPrompt) {
  pendingTopicPrompt = newPrompt;
  const popup = document.getElementById("topic-switch-popup");
  if (popup) popup.style.display = "block";
}

function dismissTopicOffer() {
  const popup = document.getElementById("topic-switch-popup");
  if (popup) popup.style.display = "none";
  if (pendingTopicPrompt) {
    const p = pendingTopicPrompt;
    pendingTopicPrompt = "";
    conversationPrompts.push(p);
    executePrompt(p);
  }
}

function acceptNewChatOffer() {
  const p = pendingTopicPrompt;
  pendingTopicPrompt = "";
  const popup = document.getElementById("topic-switch-popup");
  if (popup) popup.style.display = "none";
  resetToNewChat();
  if (p) {
    setTimeout(() => {
      conversationPrompts.push(p);
      executePrompt(p);
    }, 100);
  }
}

function executePrompt(text) {
  const textarea = document.getElementById("user-prompt");
  const form = document.getElementById("chat-form");
  if (textarea && form) {
    textarea.value = text;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
  }
}

function resetToNewChat() {
  conversationPrompts = [];
  dismissTopicOffer();
  switchView('chat');
  const messagesList = document.getElementById("messages-list");
  messagesList.innerHTML = "";
  document.getElementById("welcome-hero").style.display = "flex";
  const textarea = document.getElementById("user-prompt");
  textarea.value = "";
  textarea.focus();
  lastResponseData = null;
  renderInspectorContent();
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

    if (checkTopicShift(prompt)) {
      showTopicOffer(prompt);
      return;
    }

    conversationPrompts.push(prompt);
    const modelOverride = document.getElementById("tier-select").value || null;

    document.getElementById("welcome-hero").style.display = "none";

    appendUserMessage(prompt);
    textarea.value = "";
    autoResizeTextarea(textarea);

    const loadingId = appendLoadingAssistant();
    const sendBtn = document.getElementById("btn-send");
    sendBtn.disabled = true;

    try {
      const res = await fetch(`${getApiBaseUrl()}/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt,
          user_id: "claude_user",
          model_override: modelOverride
        })
      });

      if (!res.ok) {
        throw new Error(`API returned HTTP ${res.status}`);
      }

      const data = await res.json();
      lastResponseData = data;
      renderAssistantResponseWithTypewriter(loadingId, data);
      fetchAuditLogs();
    } catch (err) {
      const loadingEl = document.getElementById(loadingId);
      if (loadingEl) {
        const isHttpsMixedContent = window.location.protocol === "https:" && getApiBaseUrl().startsWith("http://");
        if (isHttpsMixedContent) {
          loadingEl.innerHTML = `
            <div class="blocked-callout" style="line-height: 1.6;">
              <div style="font-weight: 700; margin-bottom: 0.35rem;">🔒 Browser Mixed Content Restriction</div>
              <div>Your browser is on a secure <code>https://</code> page and blocked the connection to the local <code>http://</code> backend.</div>
              <div style="margin-top: 0.6rem; display: flex; flex-wrap: wrap; gap: 0.5rem;">
                <a href="http://192.168.1.33:8000" class="btn-topic-new" style="text-decoration: none; display: inline-block;">📱 Open via Local Network (http://192.168.1.33:8000)</a>
                <a href="http://localhost:8000" class="btn-topic-dismiss" style="text-decoration: none; display: inline-block;">💻 Open localhost:8000</a>
                <button onclick="promptForBackendUrl()" class="btn-topic-dismiss">⚙️ Change Backend URL</button>
              </div>
            </div>
          `;
        } else {
          loadingEl.innerHTML = `
            <div class="blocked-callout">
              <div>⚠️ Connection Error: ${escapeHtml(err.message)}</div>
              <div style="font-size: 0.8rem; margin-top: 0.4rem; color: var(--text-secondary);">Make sure the ControlPlane server is running (<code>uvicorn app.main:app --host 0.0.0.0 --port 8000</code>).</div>
              <div style="margin-top: 0.5rem;">
                <button onclick="promptForBackendUrl()" class="btn-topic-dismiss" style="font-size: 0.76rem;">⚙️ Set Backend Gateway URL</button>
              </div>
            </div>
          `;
        }
      }
    } finally {
      sendBtn.disabled = false;
      textarea.focus();
    }
  });
}

function appendUserMessage(text) {
  const list = document.getElementById("messages-list");
  const row = document.createElement("div");
  row.className = "message-row";
  row.innerHTML = `<div class="message-user">${escapeHtml(text)}</div>`;
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
      <div style="display: flex; align-items: center; gap: 0.75rem; color: var(--text-secondary); font-size: 0.88rem; padding: 0.5rem 0;">
        <div class="pill-dot"></div>
        <span>Evaluating prevention rules, truth envelope, and tiered router...</span>
      </div>
    </div>
  `;
  list.appendChild(row);
  scrollToBottom();
  return id;
}

/**
 * Renders assistant response with smooth Claude-style typewriter streaming animation
 */
function renderAssistantResponseWithTypewriter(loadingId, resp) {
  const row = document.getElementById(loadingId);
  if (!row) return;

  const actionClass = resp.decision.action.toLowerCase();
  const score = resp.findings.performance_score || resp.findings.self_rated_confidence || 1.0;

  // Header badges
  let badgesHtml = `
    <div class="assistant-header-pillbox">
      <span class="cp-pill cp-pill-${actionClass}">DECISION: ${resp.decision.action}</span>
      <span class="cp-pill cp-pill-tier">${resp.tier.toUpperCase()} (${resp.model_used})</span>
      <span class="cp-pill" style="color: var(--pink-light); background: var(--pink-soft);">CONFIDENCE: ${resp.confidence.state} (${(score * 100).toFixed(0)}%)</span>
  `;
  if (resp.cached) {
    badgesHtml += `<span class="cp-pill cp-pill-cache">⚡ DEDUP HIT (0 Tokens)</span>`;
  }
  if (resp.decision.edits_applied && resp.decision.edits_applied.length > 0) {
    badgesHtml += `<span class="cp-pill cp-pill-edit">EDITS: ${resp.decision.edits_applied.join(", ")}</span>`;
  }
  badgesHtml += `</div>`;

  // Check for ASK_USER clarification response
  if (resp.decision.action === "ASK_USER" && resp.decision.clarifying_questions) {
    row.innerHTML = `
      <div class="message-assistant">
        ${badgesHtml}
        <div class="assistant-body">
          <p>${escapeHtml(resp.content)}</p>
          <div class="clarify-box">
            <div class="clarify-title">Select your preferred focus area (0 extra tokens):</div>
            ${resp.decision.clarifying_questions.map((opt, idx) => `
              <button class="clarify-option-btn" onclick="submitClarificationChoice('${escapeHtml(opt)}')">
                ${escapeHtml(opt)}
              </button>
            `).join('')}
          </div>
        </div>
      </div>
    `;
    scrollToBottom();
    return;
  }

  // Create skeleton with streaming container
  const rawText = resp.content || "";
  const contentContainerId = `content-${Date.now()}`;

  row.innerHTML = `
    <div class="message-assistant">
      ${badgesHtml}
      <div class="assistant-body" id="${contentContainerId}">
        <span class="streaming-text"></span><span class="streaming-cursor"></span>
      </div>
      <div class="assistant-toolbar">
        <button class="toolbar-btn" onclick="copyMessageText(this, \`${escapeJsString(rawText)}\`)">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span>Copy</span>
        </button>
        <button class="toolbar-btn" onclick="toggleInspectorPanel()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <span>Inspect Reasoning</span>
        </button>
        <span class="toolbar-metrics">${resp.tokens_used} tokens • $${(resp.estimated_cost_usd || 0).toFixed(5)} • ${resp.latency_ms} ms</span>
      </div>
    </div>
  `;

  // Start word-by-word streaming animation
  const container = document.getElementById(contentContainerId);
  const streamTextEl = container.querySelector(".streaming-text");
  const cursorEl = container.querySelector(".streaming-cursor");

  const words = rawText.split(" ");
  let wordIndex = 0;
  const streamSpeedMs = resp.cached ? 5 : 18; // Faster for cache hits

  function streamStep() {
    if (wordIndex < words.length) {
      const chunk = words.slice(0, wordIndex + 1).join(" ");
      streamTextEl.innerText = chunk;
      wordIndex++;
      scrollToBottom();
      setTimeout(streamStep, streamSpeedMs);
    } else {
      // Completed streaming: render full Markdown, code highlight, math
      if (cursorEl) cursorEl.remove();
      const renderedHtml = window.marked ? marked.parse(rawText) : escapeHtml(rawText);
      container.innerHTML = renderedHtml;

      // Enhance code blocks with copy buttons
      container.querySelectorAll("pre code").forEach(block => {
        if (window.hljs) hljs.highlightElement(block);
      });
      addCodeCopyButtons(container);

      // Render math equations if KaTeX is present
      if (window.renderMathInElement) {
        renderMathInElement(container, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "$", right: "$", display: false }
          ]
        });
      }
      scrollToBottom();
    }
  }

  streamStep();
}

function submitClarificationChoice(choiceText) {
  const textarea = document.getElementById("user-prompt");
  if (textarea) {
    textarea.value = `Focus on: ${choiceText}`;
    document.getElementById("btn-send").click();
  }
}

function addCodeCopyButtons(container) {
  container.querySelectorAll("pre").forEach(pre => {
    if (pre.querySelector(".code-block-header")) return;
    const code = pre.querySelector("code");
    const lang = code ? (code.className.match(/language-(\w+)/) || [])[1] || "code" : "text";

    const header = document.createElement("div");
    header.className = "code-block-header";
    header.innerHTML = `
      <span>${lang.toUpperCase()}</span>
      <button class="btn-copy-code" onclick="copyCode(this)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
        <span>Copy Code</span>
      </button>
    `;
    pre.parentNode.insertBefore(header, pre);
  });
}

function copyCode(btn) {
  const pre = btn.closest(".code-block-header").nextElementSibling;
  const code = pre.querySelector("code") ? pre.querySelector("code").innerText : pre.innerText;
  navigator.clipboard.writeText(code).then(() => {
    btn.innerHTML = `<span>✓ Copied</span>`;
    setTimeout(() => {
      btn.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
        <span>Copy Code</span>
      `;
    }, 2000);
  });
}

function copyMessageText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = `<span>✓ Copied</span>`;
    setTimeout(() => btn.innerHTML = orig, 1800);
  });
}

function scrollToBottom() {
  const container = document.getElementById("view-chat");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

/* ==========================================================================
   Audit Logs & Metrics Fetcher
   ========================================================================== */
async function fetchAuditLogs() {
  try {
    const res = await fetch(`${getApiBaseUrl()}/audit?limit=25`);
    if (!res.ok) return;
    const logs = await res.json();

    const tbody = document.getElementById("audit-rows");
    if (!tbody) return;

    if (!logs || logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">No audit logs recorded yet.</td></tr>`;
      return;
    }

    let cacheHits = 0;
    let totalSpend = 0;

    tbody.innerHTML = logs.map(log => {
      if (log.cached) cacheHits++;
      totalSpend += log.estimated_cost_usd || 0;

      const actClass = (log.decision_action || "ALLOW").toLowerCase();
      const timeStr = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 0.76rem; color: var(--text-muted);">${timeStr}</td>
          <td style="font-family: var(--font-mono); font-size: 0.74rem;">${log.request_id.slice(0, 8)}...</td>
          <td><span class="cp-pill cp-pill-${actClass}">${log.decision_action}</span></td>
          <td style="color: var(--pink-light); font-weight: 600;">${log.confidence_state}</td>
          <td><span class="cp-pill cp-pill-tier">${log.model_tier.toUpperCase()}</span></td>
          <td>${log.cached ? '<span style="color: var(--blue-light); font-weight: 700;">YES</span>' : '<span style="color: var(--text-muted);">NO</span>'}</td>
          <td style="font-family: var(--font-mono); font-size: 0.78rem;">${(log.latency_ms || 0).toFixed(1)} ms</td>
          <td style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(log.raw_prompt)}</td>
        </tr>
      `;
    }).join("");

    // Update Mini Metrics
    const cacheRateEl = document.getElementById("side-cache-rate");
    if (cacheRateEl) {
      const rate = logs.length > 0 ? ((cacheHits / logs.length) * 100).toFixed(0) : 0;
      cacheRateEl.innerText = `${rate}% (${cacheHits} hits)`;
    }

    const spendEl = document.getElementById("side-spend-val");
    if (spendEl) {
      spendEl.innerText = `$${totalSpend.toFixed(4)} / $10.00`;
    }

  } catch (e) {
    console.error("Failed to fetch audit logs:", e);
  }
}

/* ==========================================================================
   Review Queue Fetcher & Resolver
   ========================================================================== */
let reviewItemsCache = [];

async function fetchReviewQueue() {
  try {
    const res = await fetch(`${getApiBaseUrl()}/v1/reviews`);
    if (!res.ok) return;
    const data = await res.json();
    reviewItemsCache = data.reviews || [];

    const badge = document.getElementById("nav-review-badge");
    const pendingCount = reviewItemsCache.filter(r => r.status === "pending").length;
    if (badge) {
      badge.innerText = pendingCount;
      badge.style.display = pendingCount > 0 ? "inline-block" : "none";
    }

    renderReviewCards(reviewItemsCache);
  } catch (e) {
    console.error("Failed to fetch review queue:", e);
  }
}

function filterReviewQueue(status, btn) {
  document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
  if (btn) btn.classList.add("active");

  if (status === "all") {
    renderReviewCards(reviewItemsCache);
  } else {
    renderReviewCards(reviewItemsCache.filter(r => r.status === status));
  }
}

function renderReviewCards(items) {
  const container = document.getElementById("review-cards-container");
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state-box">
        No review items matching this filter.
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(item => {
    const isPending = item.status === "pending";
    const statusColor = item.status === "approved" ? "var(--color-allow)" : item.status === "rejected" ? "var(--color-block)" : "var(--color-escalate)";

    return `
      <div class="review-item-card" id="rev-card-${item.id}">
        <div class="review-card-top">
          <div class="review-badge-row">
            <span class="cp-pill cp-pill-escalate">REVIEW ID: ${item.id}</span>
            <span class="cp-pill" style="background: rgba(255,255,255,0.06); color: ${statusColor};">${item.status.toUpperCase()}</span>
            <span style="font-size: 0.74rem; color: var(--text-muted); font-family: var(--font-mono);">${new Date(item.created_at).toLocaleString()}</span>
          </div>
        </div>

        <div class="review-prompt-box">
          <strong>Prompt:</strong> ${escapeHtml(item.raw_prompt)}
        </div>

        <div class="review-answer-box">
          <strong>Candidate Answer:</strong> ${escapeHtml(item.candidate_answer)}
        </div>

        ${isPending ? `
          <div class="review-actions-row">
            <button class="btn-review-act btn-act-reject" onclick="resolveReviewItem('${item.id}', 'reject')">✕ Reject</button>
            <button class="btn-review-act btn-act-approve" onclick="resolveReviewItem('${item.id}', 'approve')">✓ Approve Answer</button>
          </div>
        ` : `
          <div style="font-size: 0.76rem; color: var(--text-muted); text-align: right;">
            Resolved at: ${item.resolved_at ? new Date(item.resolved_at).toLocaleString() : 'N/A'} • Note: ${escapeHtml(item.reviewer_note || 'None')}
          </div>
        `}
      </div>
    `;
  }).join("");
}

async function resolveReviewItem(reviewId, action) {
  try {
    const res = await fetch(`${getApiBaseUrl()}/v1/review/${reviewId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: action,
        note: `Resolved via Web UI (${action})`
      })
    });

    if (res.ok) {
      fetchReviewQueue();
    }
  } catch (e) {
    console.error("Failed to resolve review item:", e);
  }
}

async function fetchHealth() {
  try {
    const res = await fetch(`${getApiBaseUrl()}/health`);
    if (res.ok) {
      const data = await res.json();
      const statusText = document.getElementById("header-status-text");
      if (statusText) statusText.innerText = "Governance Active";
    }
  } catch (e) {}
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeJsString(str) {
  if (!str) return "";
  return str.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$');
}
