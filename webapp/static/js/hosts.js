document.addEventListener("click", async (event) => {
  const selectDrafts = event.target.closest("[data-select-drafts]");
  if (selectDrafts) {
    document.querySelectorAll("[data-draft-checkbox]").forEach((checkbox) => {
      checkbox.checked = selectDrafts.checked;
    });
    return;
  }

  const selfCheck = event.target.closest("[data-self-check]");
  const debug = event.target.closest("[data-debug]");
  if (!selfCheck && !debug) return;

  const source = selfCheck || debug;
  const assetSeq = source.dataset.selfCheck || source.dataset.debug;
  const endpoint = selfCheck
    ? `/api/host/${assetSeq}/self_check`
    : `/api/host/${assetSeq}/debug_snapshot`;

  const response = await fetch(endpoint, { method: "POST" });
  const data = await response.json();
  if (response.status === 403 || response.status === 401) {
    alert("請先使用管理員帳號登入後再執行此操作。");
    window.location.href = "/login";
    return;
  }
  alert(JSON.stringify(data, null, 2));
});
