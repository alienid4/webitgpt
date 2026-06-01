document.addEventListener("click", async (event) => {
  const selectDrafts = event.target.closest("[data-select-drafts]");
  if (selectDrafts) {
    document.querySelectorAll("[data-draft-checkbox]").forEach((checkbox) => {
      checkbox.checked = selectDrafts.checked;
    });
    return;
  }

  const selectAssets = event.target.closest("[data-select-assets]");
  if (selectAssets) {
    document.querySelectorAll("[data-asset-checkbox]").forEach((checkbox) => {
      checkbox.checked = selectAssets.checked;
    });
    return;
  }

  const detailToggle = event.target.closest("[data-asset-detail-toggle]");
  if (detailToggle) {
    const detailRow = document.getElementById(detailToggle.dataset.assetDetailToggle);
    if (!detailRow) return;
    const nextHidden = !detailRow.hidden;
    detailRow.hidden = nextHidden;
    detailToggle.textContent = nextHidden ? "展開" : "收合";
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

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-draft-bulk-form]");
  const assetForm = event.target.closest("[data-asset-bulk-form]");
  if (!form && !assetForm) return;
  if (assetForm) {
    assetForm.querySelectorAll("input[data-asset-bulk-copy]").forEach((node) => node.remove());
    document.querySelectorAll("[data-asset-checkbox]:checked").forEach((checkbox) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "asset_seq";
      input.value = checkbox.value;
      input.dataset.assetBulkCopy = "1";
      assetForm.appendChild(input);
    });
    return;
  }
  form.querySelectorAll("input[data-draft-bulk-copy]").forEach((node) => node.remove());
  document.querySelectorAll("[data-draft-checkbox]:checked").forEach((checkbox) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "asset_seq";
    input.value = checkbox.value;
    input.dataset.draftBulkCopy = "1";
    form.appendChild(input);
  });
});
