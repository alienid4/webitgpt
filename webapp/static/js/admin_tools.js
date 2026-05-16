const OPENING_SYSTEM_KEY = "webitgpt.opening.lastSystem";

function rememberOpeningSystem(value) {
  if (!value) return;
  try {
    localStorage.setItem(OPENING_SYSTEM_KEY, value);
  } catch {
    // localStorage may be blocked in strict browser modes.
  }
}

function lastOpeningSystem() {
  try {
    return localStorage.getItem(OPENING_SYSTEM_KEY) || "";
  } catch {
    return "";
  }
}

function applyLastOpeningSystem() {
  const form = document.querySelector("form [data-opening-system-select]")?.closest("form");
  const select = form?.querySelector("[data-opening-system-select]");
  if (!form || !select) return;

  const params = new URLSearchParams(window.location.search);
  const current = params.get("system");
  if (current) {
    rememberOpeningSystem(current);
    return;
  }

  const remembered = lastOpeningSystem();
  if (!remembered || remembered === select.value) return;
  const exists = Array.from(select.options).some((option) => option.value === remembered);
  if (!exists) return;

  select.value = remembered;
  form.requestSubmit();
}

document.addEventListener("input", (event) => {
  const search = event.target.closest("[data-opening-system-search]");
  if (!search) return;

  const form = search.closest("form");
  const select = form?.querySelector("[data-opening-system-select]");
  if (!select) return;

  const keyword = search.value.trim().toLowerCase();
  Array.from(select.options).forEach((option) => {
    if (option.value === "__all__") {
      option.hidden = false;
      return;
    }
    const label = option.textContent.toLowerCase();
    option.hidden = Boolean(keyword) && !label.includes(keyword);
  });
});

document.addEventListener("change", (event) => {
  const select = event.target.closest("[data-opening-system-select]");
  if (!select) return;
  rememberOpeningSystem(select.value);
});

document.addEventListener("submit", (event) => {
  const select = event.target.querySelector?.("[data-opening-system-select]");
  if (!select) return;
  rememberOpeningSystem(select.value);
});

function refreshScoreRings() {
  document.querySelectorAll("[data-score-ring]").forEach((ring) => {
    const raw = Number.parseFloat(ring.dataset.score || "0");
    const score = Math.max(0, Math.min(100, Number.isFinite(raw) ? raw : 0));
    ring.style.setProperty("--score-angle", `${score * 3.6}deg`);
    ring.setAttribute("aria-label", `健康分數 ${score}`);
  });
}

document.addEventListener("DOMContentLoaded", applyLastOpeningSystem);
document.addEventListener("DOMContentLoaded", refreshScoreRings);

function findApiStatus(button) {
  if (button.dataset.statusTarget) {
    return document.getElementById(button.dataset.statusTarget);
  }

  const localStatus = button.closest("section, article, tr, .panel")?.querySelector(".submit-status");
  if (localStatus) return localStatus;

  const next = button.parentElement?.nextElementSibling;
  if (next?.classList.contains("submit-status")) return next;

  const result = document.getElementById(button.dataset.resultTarget || "apiResult");
  if (result) return result;

  const status = document.createElement("div");
  status.className = "submit-status";
  status.hidden = true;
  status.setAttribute("aria-live", "polite");
  (button.closest("form") || button).insertAdjacentElement("afterend", status);
  return status;
}

function setApiStatus(status, message, tone = "info", busy = false) {
  if (!status) return;
  status.hidden = false;
  status.classList.toggle("danger", tone === "error");
  const spinner = busy ? '<span class="spinner-sm" aria-hidden="true"></span>' : "";
  if (status.tagName === "PRE") {
    status.textContent = message;
    return;
  }
  status.innerHTML = `${spinner}<span>${message}</span>`;
}

document.addEventListener("click", async (event) => {
  const l3Filter = event.target.closest("[data-l3-filter]");
  if (l3Filter) {
    event.preventDefault();
    const panel = l3Filter.closest(".l3-panel");
    const verdict = l3Filter.dataset.l3Filter;
    panel?.querySelectorAll("[data-l3-filter]").forEach((item) => item.classList.toggle("active", item === l3Filter));
    const history = panel?.querySelector(".diagnostic-history");
    if (history) history.open = true;
    panel?.querySelectorAll("[data-l3-verdict]").forEach((item) => {
      const matched = item.dataset.l3Verdict === verdict;
      item.hidden = !matched;
      if (matched && verdict !== "PASS") item.open = true;
    });
    return;
  }

  const button = event.target.closest("[data-api-post]");
  if (!button) return;

  const result = document.getElementById(button.dataset.resultTarget || "apiResult");
  const status = findApiStatus(button);
  const payload = button.dataset.payload ? JSON.parse(button.dataset.payload) : {};
  const originalText = button.textContent;
  button.disabled = true;
  button.classList.add("is-busy");
  button.textContent = button.dataset.busyText || "處理中";
  setApiStatus(status || result, button.dataset.submitMessage || "已送出，正在處理中，請稍候。", "info", true);

  try {
    const response = await fetch(button.dataset.apiPost, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const text = await response.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = { status: response.status, body: text.slice(0, 1000) };
    }

    if (!response.ok || data.success === false) {
      const message = data.error || `操作失敗：HTTP ${response.status}`;
      setApiStatus(status || result, message, "error", false);
      if (!status && !result) alert(message);
      return;
    }

    if (button.dataset.reloadOnSuccess === "true") {
      setApiStatus(status || result, data.message || "處理完成，正在重新整理畫面。", "ok", false);
      window.location.reload();
      return;
    }

    setApiStatus(status || result, data.message || `處理完成：${data.count ?? data.job_id ?? "ok"}`, "ok", false);
  } catch (error) {
    const message = `操作失敗：${error.message || error}`;
    setApiStatus(status || result, message, "error", false);
    if (!status && !result) alert(message);
  } finally {
    button.disabled = false;
    button.classList.remove("is-busy");
    button.textContent = originalText;
  }
});
