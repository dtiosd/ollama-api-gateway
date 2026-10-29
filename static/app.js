const ADMIN_TOKEN_HEADER = "X-Admin-Token";
const ADMIN_TOKEN_STORAGE_KEY = "ollamaAdminToken";

function getAdminToken() {
  return localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
}

function setAdminToken(token) {
  if (token) {
    localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
  }
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getAdminToken();
  if (token) headers[ADMIN_TOKEN_HEADER] = token;
  const resp = await fetch(path, { ...options, headers });
  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!resp.ok) {
    const msg = data?.detail
      ? typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail)
      : resp.statusText;
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  return data;
}

// 管理接口返回 403/503 时引导用户回到口令输入框
function handleAuthError(e) {
  if (e.status === 403 || e.status === 503) {
    const input = document.getElementById("admin-token");
    input?.classList.add("is-invalid");
    showToast(e.message, "danger");
    input?.focus();
    return true;
  }
  return false;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const COPY_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
const QUOTA_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>`;
const DISABLE_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 7l10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
const ENABLE_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5L16.5 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const DELETE_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M10 11v6M14 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;

function formatDateTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return String(value).replace("T", " ").slice(0, 19);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const cls =
    type === "success"
      ? "text-bg-success"
      : type === "warning"
        ? "text-bg-warning"
        : "text-bg-danger";
  const icon =
    type === "success"
      ? "bi-check-circle"
      : type === "warning"
        ? "bi-exclamation-triangle"
        : "bi-x-circle";
  const el = document.createElement("div");
  el.className = `toast align-items-center ${cls} border-0`;
  el.setAttribute("role", "alert");
  el.innerHTML = `
    <div class="d-flex">
      <div class="toast-body"><i class="bi ${icon} me-2"></i>${esc(message)}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;
  container.appendChild(el);
  const toast = new bootstrap.Toast(el, { delay: 2800 });
  el.addEventListener("hidden.bs.toast", () => el.remove());
  toast.show();
}

function showConfirm({ title = "确认操作", message, okText = "确定", okClass = "btn-danger" } = {}) {
  const modalEl = document.getElementById("confirm-modal");
  const okBtn = document.getElementById("confirm-ok");
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").textContent = message;
  okBtn.textContent = okText;
  okBtn.className = `modal-btn ${okClass === "btn-success" ? "modal-btn-ok" : "modal-btn-danger"}`;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      okBtn.removeEventListener("click", onOk);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      if (value) modal.hide();
      resolve(value);
    };
    const onOk = () => finish(true);
    const onHidden = () => finish(false);
    okBtn.addEventListener("click", onOk);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    modal.show();
  });
}

function showQuotaDialog(current) {
  const modalEl = document.getElementById("quota-modal");
  const input = document.getElementById("quota-input");
  const okBtn = document.getElementById("quota-ok");
  input.classList.remove("is-invalid");
  input.value = current ?? "";
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      okBtn.removeEventListener("click", onOk);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      input.removeEventListener("keydown", onKey);
      if (value !== null) modal.hide();
      resolve(value);
    };
    const onOk = () => {
      const n = Number(input.value);
      if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
        input.classList.add("is-invalid");
        return;
      }
      finish(n);
    };
    const onHidden = () => finish(null);
    const onKey = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onOk();
      }
    };
    okBtn.addEventListener("click", onOk);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    input.addEventListener("keydown", onKey);
    modal.show();
    setTimeout(() => input.focus(), 200);
  });
}

function showCreateDialog() {
  const modalEl = document.getElementById("create-modal");
  const usernameInput = document.getElementById("create-username");
  const modelSelect = document.getElementById("create-model");
  const quotaInput = document.getElementById("create-quota");
  const okBtn = document.getElementById("create-ok");
  usernameInput.classList.remove("is-invalid");
  modelSelect.classList.remove("is-invalid");
  quotaInput.classList.remove("is-invalid");
  usernameInput.value = "";
  quotaInput.value = "100000";
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  const fillModels = async () => {
    modelSelect.innerHTML = `<option value="">加载中…</option>`;
    let names = [];
    try {
      const data = await api("/backend/api-keys/models");
      names = data.models || [];
    } catch {
      names = ["qwen2.5:7b", "llama3.2:3b"];
    }
    if (!names.length) {
      names = ["qwen2.5:7b", "llama3.2:3b"];
    }
    modelSelect.innerHTML =
      `<option value="">请选择模型</option>` +
      names.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
  };

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      okBtn.removeEventListener("click", onOk);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      if (value) modal.hide();
      resolve(value);
    };
    const onOk = () => {
      const username = usernameInput.value.trim();
      const model = modelSelect.value.trim();
      const token_quota = Number(quotaInput.value);
      let valid = true;
      if (!username) {
        usernameInput.classList.add("is-invalid");
        valid = false;
      }
      if (!model) {
        modelSelect.classList.add("is-invalid");
        valid = false;
      }
      if (!Number.isInteger(token_quota) || token_quota < 1) {
        quotaInput.classList.add("is-invalid");
        valid = false;
      }
      if (!valid) return;
      finish({ username, model, token_quota });
    };
    const onHidden = () => finish(null);
    okBtn.addEventListener("click", onOk);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    modal.show();
    fillModels();
    setTimeout(() => usernameInput.focus(), 200);
  });
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    showToast("复制失败，请手动复制", "danger");
    return false;
  }
}

async function loadKeys() {
  const username = document.getElementById("filter-username").value.trim();
  const qs = username ? `?username=${encodeURIComponent(username)}` : "";
  const tbody = document.getElementById("keys-tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="muted">加载中…</td></tr>`;
  try {
    const rows = await api(`/backend/api-keys${qs}`);
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted">暂无密钥</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const active = r.is_active !== false;
        const status = active ? "启用" : "禁用";
        const toggleLabel = active ? "禁用" : "启用";
        const toggleIcon = active ? DISABLE_ICON : ENABLE_ICON;
        return `
      <tr data-id="${r.id}" class="${active ? "" : "row-disabled"}">
        <td>${r.id}</td>
        <td>${esc(r.username)}</td>
        <td>
          <div class="key-with-copy">
            <span class="key-cell mono" title="${esc(r.api_key)}">${esc(r.api_key)}</span>
            <button class="icon-btn" data-action="copy" data-key="${esc(r.api_key)}" title="复制 API Key">${COPY_ICON}</button>
          </div>
        </td>
        <td class="mono">${esc(r.model || "—")}</td>
        <td>${r.token_quota}</td>
        <td><span class="status ${active ? "on" : "off"}">${status}</span></td>
        <td>${esc(formatDateTime(r.created_at))}</td>
        <td class="actions">
          <button class="icon-btn" data-action="quota" data-id="${r.id}" data-quota="${r.token_quota}" title="改额度">${QUOTA_ICON}</button>
          <button class="icon-btn ${active ? "danger" : "success"}" data-action="toggle" data-id="${r.id}" data-username="${esc(r.username)}" data-active="${active}" title="${toggleLabel}">${toggleIcon}</button>
          <button class="icon-btn danger" data-action="delete" data-id="${r.id}" data-username="${esc(r.username)}" title="删除">${DELETE_ICON}</button>
        </td>
      </tr>`;
      })
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="error">${esc(e.message)}</td></tr>`;
    if (!handleAuthError(e)) showToast(e.message, "danger");
  }
}

const USAGE_ENDPOINTS = {
  day: { path: "/backend/api-keys/usage/daily", label: "日期" },
  week: { path: "/backend/api-keys/usage/weekly", label: "周" },
  month: { path: "/backend/api-keys/usage", label: "年月" },
  year: { path: "/backend/api-keys/usage/yearly", label: "年份" },
};

let currentGranularity = "day";
let currentGroup = "username";

function usageColumns() {
  const periodLabel = USAGE_ENDPOINTS[currentGranularity].label;
  if (currentGroup === "model") {
    return ["模型", "用户名", periodLabel, "Prompt", "Completion", "Total", "请求次数"];
  }
  if (currentGroup === "username") {
    return ["用户名", periodLabel, "Prompt", "Completion", "Total", "请求次数"];
  }
  return ["用户名", periodLabel, "模型", "Prompt", "Completion", "Total", "请求次数"];
}

function renderUsageHeader() {
  document.getElementById("usage-thead-row").innerHTML = usageColumns()
    .map((c) => `<th>${esc(c)}</th>`)
    .join("");
}

function renderUsageRows(rows, emptyText) {
  const colCount = usageColumns().length;
  if (!rows.length) {
    return `<tr><td colspan="${colCount}" class="muted">${emptyText}</td></tr>`;
  }
  const metrics = (r) =>
    `<td>${r.prompt_tokens}</td><td>${r.completion_tokens}</td><td>${r.total_tokens}</td><td>${r.request_count}</td>`;
  return rows
    .map((r) => {
      if (currentGroup === "model") {
        return `<tr><td>${esc(r.model || "—")}</td><td>${esc(r.username || "—")}</td><td>${esc(
          r.period
        )}</td>${metrics(r)}</tr>`;
      }
      if (currentGroup === "username") {
        return `<tr><td>${esc(r.username)}</td><td>${esc(r.period)}</td>${metrics(r)}</tr>`;
      }
      return `<tr><td>${esc(r.username)}</td><td>${esc(r.period)}</td><td>${esc(
        r.model || "—"
      )}</td>${metrics(r)}</tr>`;
    })
    .join("");
}

async function loadUsage() {
  const username = document.getElementById("usage-username").value.trim();
  const conf = USAGE_ENDPOINTS[currentGranularity];
  const colCount = usageColumns().length;
  renderUsageHeader();
  const params = new URLSearchParams({ group_by: currentGroup });
  if (username) params.set("username", username);
  const tbody = document.getElementById("usage-tbody");
  tbody.innerHTML = `<tr><td colspan="${colCount}" class="muted">加载中…</td></tr>`;
  try {
    const rows = await api(`${conf.path}?${params.toString()}`);
    const emptyText =
      currentGranularity === "day" ? "今日暂无用量记录" : "暂无用量记录";
    tbody.innerHTML = renderUsageRows(rows, emptyText);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="${colCount}" class="error">${esc(e.message)}</td></tr>`;
    if (!handleAuthError(e)) showToast(e.message, "danger");
  }
}

document.getElementById("keys-tbody").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;

  if (action === "copy") {
    const ok = await copyText(btn.dataset.key);
    if (ok) {
      btn.classList.add("copied");
      showToast("API Key 已复制");
      setTimeout(() => btn.classList.remove("copied"), 1200);
    }
    return;
  }

  if (action === "quota") {
    const token_quota = await showQuotaDialog(Number(btn.dataset.quota));
    if (token_quota === null) return;
    try {
      await api(`/backend/api-keys/${btn.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ token_quota }),
      });
      showToast("额度已更新");
      await loadKeys();
    } catch (e) {
      showToast(e.message, "danger");
    }
    return;
  }

  if (action === "toggle") {
    const active = btn.dataset.active === "true";
    const next = !active;
    const label = next ? "启用" : "禁用";
    const ok = await showConfirm({
      title: `${label}密钥`,
      message: `确认${label} ${btn.dataset.username}的API Key？`,
      okText: label,
      okClass: next ? "btn-success" : "btn-danger",
    });
    if (!ok) return;
    try {
      await api(`/backend/api-keys/${btn.dataset.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: next }),
      });
      showToast(`已${label}`);
      await loadKeys();
    } catch (e) {
      showToast(e.message, "danger");
    }
    return;
  }

  if (action === "delete") {
    const ok = await showConfirm({
      title: "删除密钥",
      message: `确认删除 ${btn.dataset.username}的API Key？此操作不可恢复。`,
      okText: "删除",
      okClass: "btn-danger",
    });
    if (!ok) return;
    try {
      await api(`/backend/api-keys/${btn.dataset.id}`, { method: "DELETE" });
      showToast("已删除");
      await loadKeys();
    } catch (e) {
      showToast(e.message, "danger");
    }
  }
});

document.getElementById("btn-refresh").addEventListener("click", loadKeys);
document.getElementById("filter-username").addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadKeys();
});
document.getElementById("btn-usage").addEventListener("click", loadUsage);
document.getElementById("btn-usage-refresh").addEventListener("click", loadUsage);
document.getElementById("usage-username").addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadUsage();
});
document.getElementById("usage-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("[data-granularity]");
  if (!tab) return;
  document.querySelectorAll("#usage-tabs .nav-link").forEach((el) => el.classList.remove("active"));
  tab.classList.add("active");
  currentGranularity = tab.dataset.granularity;
  loadUsage();
});
document.getElementById("usage-group-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("[data-group]");
  if (!tab) return;
  document
    .querySelectorAll("#usage-group-tabs .nav-link")
    .forEach((el) => el.classList.remove("active"));
  tab.classList.add("active");
  currentGroup = tab.dataset.group;
  loadUsage();
});
document.getElementById("btn-add-key").addEventListener("click", async () => {
  const payload = await showCreateDialog();
  if (!payload) return;
  try {
    const row = await api("/backend/api-keys", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast(`已生成密钥（用户名 ${row.username}，模型 ${row.model}）`);
    await loadKeys();
  } catch (e) {
    showToast(e.message, "danger");
  }
});

loadKeys();
loadUsage();

// 示例代码统一用当前访问地址，避免把部署主机写死在前端
const ORIGIN = window.location.origin;

const EXAMPLE_SNIPPETS = {
  openai: {
    curl: `curl ${ORIGIN}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-xxx" \\
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "你好"}]
  }'`,
    python: `from openai import OpenAI

client = OpenAI(
    api_key="sk-xxx",
    base_url="${ORIGIN}/v1",
)

resp = client.chat.completions.create(
    model="qwen2.5:7b",  # 或 llama3.2:3b
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)`,
    nodejs: `import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-xxx",
  baseURL: "${ORIGIN}/v1",
});

const resp = await client.chat.completions.create({
  model: "qwen2.5:7b", // 或 llama3.2:3b
  messages: [{ role: "user", content: "你好" }],
});
console.log(resp.choices[0].message.content);`,
  },
  anthropic: {
    curl: `curl -N ${ORIGIN}/anthropic/v1/messages \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: sk-xxx" \\
  -H "anthropic-version: 2023-06-01" \\
  -d '{
    "model": "qwen2.5:7b",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "你好"}]
  }'`,
    python: `from anthropic import Anthropic

client = Anthropic(
    api_key="sk-xxx",
    base_url="${ORIGIN}/anthropic",
)

with client.messages.stream(
    model="qwen2.5:7b",  # 或 llama3.2:3b
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    print()`,
    nodejs: `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  apiKey: "sk-xxx",
  baseURL: "${ORIGIN}/anthropic",
});

const stream = client.messages.stream({
  model: "qwen2.5:7b", // 或 llama3.2:3b
  max_tokens: 1024,
  messages: [{ role: "user", content: "你好" }],
});

for await (const event of stream) {
  if (
    event.type === "content_block_delta" &&
    event.delta.type === "text_delta"
  ) {
    process.stdout.write(event.delta.text);
  }
}
console.log();`,
  },
};

const EXAMPLE_META = {
  "meta-openai-base": `${ORIGIN}/v1`,
  "meta-openai-endpoint": `POST ${ORIGIN}/v1/chat/completions`,
  "meta-anthropic-base": `${ORIGIN}/anthropic`,
  "meta-anthropic-endpoint": `POST ${ORIGIN}/anthropic/v1/messages`,
};

function renderExampleMeta() {
  Object.entries(EXAMPLE_META).forEach(([id, text]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  });
}

let currentExampleApi = "openai";

function renderExampleSnippets() {
  const snippets = EXAMPLE_SNIPPETS[currentExampleApi] || {};
  document.querySelectorAll(".example-code").forEach((el) => {
    el.textContent = snippets[el.dataset.lang] || "";
  });
}

function currentExampleLang() {
  return document.querySelector("#example-tabs .code-tab.active")?.dataset.lang || "curl";
}

function showExample(lang) {
  document.querySelectorAll("#example-tabs .code-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.lang === lang);
  });
  document.querySelectorAll(".example-code").forEach((el) => {
    el.hidden = el.dataset.lang !== lang;
  });
}

document.getElementById("example-api-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("[data-api]");
  if (!tab) return;
  currentExampleApi = tab.dataset.api;
  document.querySelectorAll("#example-api-tabs .code-tab").forEach((el) => {
    el.classList.toggle("active", el === tab);
  });
  renderExampleSnippets();
});

document.getElementById("example-tabs").addEventListener("click", (e) => {
  const tab = e.target.closest("[data-lang]");
  if (!tab) return;
  showExample(tab.dataset.lang);
});

document.getElementById("btn-copy-example").addEventListener("click", async () => {
  const lang = currentExampleLang();
  const ok = await copyText(EXAMPLE_SNIPPETS[currentExampleApi][lang]);
  if (ok) showToast("示例代码已复制");
});

renderExampleSnippets();
renderExampleMeta();
showExample("curl");

// 管理口令输入：只存在浏览器 localStorage，不写入服务端配置
const adminTokenInput = document.getElementById("admin-token");
if (adminTokenInput) {
  adminTokenInput.value = getAdminToken();
  const saveToken = async () => {
    setAdminToken(adminTokenInput.value.trim());
    adminTokenInput.classList.remove("is-invalid");
    await loadKeys();
    await loadUsage();
  };
  document.getElementById("btn-token-save").addEventListener("click", saveToken);
  adminTokenInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") saveToken();
  });
}
