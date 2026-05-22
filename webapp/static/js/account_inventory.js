document.addEventListener("click", (event) => {
  const mainTab = event.target.closest("[data-account-main-tab]");
  if (mainTab) {
    activateAccountMainTab(mainTab.dataset.accountMainTab);
    history.replaceState(null, "", `#${mainTab.dataset.accountMainTab}`);
    return;
  }

  const tab = event.target.closest("[data-account-tab]");
  if (tab) {
    activateAccountTab(tab.dataset.accountTab);
    return;
  }

  const metricJump = event.target.closest("[data-account-tab-jump]");
  if (metricJump) {
    event.preventDefault();
    const name = metricJump.dataset.accountTabJump;
    activateAccountTab(name);
    history.replaceState(null, "", `#${name}`);
    return;
  }

  const edit = event.target.closest(".account-edit-note");
  if (edit) {
    const drawer = document.getElementById("accountNoteDrawer");
    const form = drawer.querySelector("form");
    form.hostname.value = edit.dataset.hostname || "";
    form.asset_seq.value = edit.dataset.assetSeq || "";
    form.name.value = edit.dataset.accountName || "";
    form.platform_scope.value = edit.dataset.platformScope || "";
    form.owner.value = edit.dataset.owner === "-" ? "" : (edit.dataset.owner || "");
    form.pam_managed.checked = edit.dataset.pamManaged === "1";
    form.apply_all.checked = false;
    form.apply_all.disabled = edit.dataset.platformBulkSupported !== "1";
    form.usage_note.value = edit.dataset.usageNote || "";
    document.getElementById("accountDrawerTitle").textContent = `${edit.dataset.hostname || edit.dataset.assetSeq} / ${edit.dataset.accountName}`;
    document.getElementById("accountDrawerScope").textContent =
      edit.dataset.platformBulkSupported === "1"
        ? `套用範圍：單一主機；勾選後套用到 ${edit.dataset.platformScope || "unknown"} 平台同帳號`
        : `套用範圍：單一主機；${edit.dataset.platformScope || "unknown"} 平台目前不支援同帳號批次套用`;
    drawer.classList.add("active");
    drawer.setAttribute("aria-hidden", "false");
    form.usage_note.focus();
    return;
  }

  if (event.target.closest("[data-close-account-drawer]")) {
    const drawer = document.getElementById("accountNoteDrawer");
    drawer.classList.remove("active");
    drawer.setAttribute("aria-hidden", "true");
  }
});

function activateAccountTab(name) {
  document.querySelectorAll("[data-account-tab]").forEach((item) => item.classList.toggle("active", item.dataset.accountTab === name));
  document.querySelectorAll("[data-account-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.accountPanel === name));
}

function activateAccountMainTab(name) {
  document.querySelectorAll("[data-account-main-tab]").forEach((item) => item.classList.toggle("active", item.dataset.accountMainTab === name));
  document.querySelectorAll("[data-account-main-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.accountMainPanel === name));
}

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("tab") && document.querySelector(`[data-account-main-panel="${params.get("tab")}"]`)) {
    activateAccountMainTab(params.get("tab"));
  }
  const initial = window.location.hash.replace("#", "");
  if (initial && document.querySelector(`[data-account-main-panel="${initial}"]`)) {
    activateAccountMainTab(initial);
    return;
  }
  if (initial && document.querySelector(`[data-account-panel="${initial}"]`)) {
    activateAccountMainTab("actual");
    activateAccountTab(initial);
    return;
  }
  if (params.get("metric")) {
    activateAccountMainTab("actual");
    activateAccountTab("list");
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const drawer = document.getElementById("accountNoteDrawer");
  if (!drawer) return;
  drawer.classList.remove("active");
  drawer.setAttribute("aria-hidden", "true");
});
