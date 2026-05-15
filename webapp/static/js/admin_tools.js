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
  const payload = button.dataset.payload ? JSON.parse(button.dataset.payload) : {};
  const originalText = button.textContent;
  button.disabled = true;
  if (button.dataset.busyText) button.textContent = button.dataset.busyText;

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
      const message = data.error || `執行失敗：HTTP ${response.status}`;
      if (result) {
        result.hidden = false;
        result.textContent = message;
      } else {
        alert(message);
      }
      return;
    }

    if (button.dataset.reloadOnSuccess === "true") {
      window.location.reload();
      return;
    }

    if (result) {
      result.hidden = false;
      result.textContent = data.message || `執行完成：${data.count ?? data.job_id ?? "ok"}`;
    }
  } finally {
    button.disabled = false;
    if (button.dataset.busyText) button.textContent = originalText;
  }
});
