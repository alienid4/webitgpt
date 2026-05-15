document.addEventListener("click", async (event) => {
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
