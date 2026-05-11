document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-api-post]");
  if (!button) return;
  const result = document.getElementById("apiResult");
  const payload = button.dataset.payload ? JSON.parse(button.dataset.payload) : {};
  button.disabled = true;
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
    if (!response.ok) {
      if (result) {
        result.hidden = false;
        result.textContent = data.error || `操作失敗：HTTP ${response.status}`;
      }
      if (response.status === 401 || response.status === 403) {
        alert("權限不足，請使用有權限的帳號操作。");
      }
      return;
    }
    if (button.dataset.reloadOnSuccess === "true") {
      window.location.reload();
      return;
    }
    if (result) {
      result.hidden = false;
      result.textContent = data.message || `完成，處理 ${data.count ?? 0} 筆。`;
    }
  } finally {
    button.disabled = false;
  }
});
