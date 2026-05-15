const savedTheme = localStorage.getItem("webitgpt-theme");
if (savedTheme === "dark") document.documentElement.dataset.theme = "dark";

document.getElementById("themeToggle")?.addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "";
  localStorage.setItem("webitgpt-theme", dark ? "dark" : "light");
});

document.addEventListener("keydown", (event) => {
  if (!event.altKey) return;
  const key = event.key.toLowerCase();
  const routes = {
    h: "/hosts",
    n: "/hosts/new",
    s: "/security_audit",
    r: "/reports",
    d: "/dependencies",
    a: "/superadmin",
  };
  if (routes[key]) {
    event.preventDefault();
    window.location.href = routes[key];
  }
});

const nav = document.querySelector(".nav");
const navStorageKey = "webitgpt-nav-order";
if (nav) {
  const orderedKeys = JSON.parse(localStorage.getItem(navStorageKey) || "[]");
  const navItems = Array.from(nav.querySelectorAll("[data-nav-key]"));
  const itemByKey = new Map(navItems.map((item) => [item.dataset.navKey, item]));
  orderedKeys.forEach((key) => {
    const item = itemByKey.get(key);
    if (item) nav.appendChild(item);
  });

  let draggedKey = "";
  nav.addEventListener("dragstart", (event) => {
    const item = event.target.closest("[data-nav-key]");
    if (!item) return;
    draggedKey = item.dataset.navKey;
    item.classList.add("nav-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedKey);
  });

  nav.addEventListener("dragover", (event) => {
    const target = event.target.closest("[data-nav-key]");
    if (!target || target.dataset.navKey === draggedKey) return;
    event.preventDefault();
    target.classList.add("nav-drop-target");
  });

  nav.addEventListener("dragleave", (event) => {
    const target = event.target.closest("[data-nav-key]");
    if (target) target.classList.remove("nav-drop-target");
  });

  nav.addEventListener("drop", (event) => {
    const target = event.target.closest("[data-nav-key]");
    const source = nav.querySelector(`[data-nav-key="${draggedKey}"]`);
    if (!target || !source || source === target) return;
    event.preventDefault();
    target.classList.remove("nav-drop-target");
    const targetBox = target.getBoundingClientRect();
    const placeAfter = event.clientX > targetBox.left + targetBox.width / 2;
    nav.insertBefore(source, placeAfter ? target.nextSibling : target);
    const nextOrder = Array.from(nav.querySelectorAll("[data-nav-key]")).map((item) => item.dataset.navKey);
    localStorage.setItem(navStorageKey, JSON.stringify(nextOrder));
  });

  nav.addEventListener("dragend", () => {
    nav.querySelectorAll(".nav-dragging, .nav-drop-target").forEach((item) => {
      item.classList.remove("nav-dragging", "nav-drop-target");
    });
    draggedKey = "";
  });
}

function restoreSortableItems(container, selector, keyName, storageKey) {
  const orderedKeys = JSON.parse(localStorage.getItem(storageKey) || "[]");
  const items = Array.from(container.querySelectorAll(selector));
  const itemByKey = new Map(items.map((item) => [item.dataset[keyName], item]));
  orderedKeys.forEach((key) => {
    const item = itemByKey.get(key);
    if (item) container.appendChild(item);
  });
}

function enableSortableTabs(container, selector, keyName, storageKey) {
  restoreSortableItems(container, selector, keyName, storageKey);
  let draggedKey = "";

  container.addEventListener("dragstart", (event) => {
    const item = event.target.closest(selector);
    if (!item) return;
    draggedKey = item.dataset[keyName];
    item.classList.add("nav-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedKey);
  });

  container.addEventListener("dragover", (event) => {
    const target = event.target.closest(selector);
    if (!target || target.dataset[keyName] === draggedKey) return;
    event.preventDefault();
    target.classList.add("nav-drop-target");
  });

  container.addEventListener("dragleave", (event) => {
    const target = event.target.closest(selector);
    if (target) target.classList.remove("nav-drop-target");
  });

  container.addEventListener("drop", (event) => {
    const target = event.target.closest(selector);
    const source = container.querySelector(`[data-${keyName.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}="${draggedKey}"]`);
    if (!target || !source || source === target) return;
    event.preventDefault();
    target.classList.remove("nav-drop-target");
    const targetBox = target.getBoundingClientRect();
    const placeAfter = event.clientX > targetBox.left + targetBox.width / 2;
    container.insertBefore(source, placeAfter ? target.nextSibling : target);
    const nextOrder = Array.from(container.querySelectorAll(selector)).map((item) => item.dataset[keyName]);
    localStorage.setItem(storageKey, JSON.stringify(nextOrder));
  });

  container.addEventListener("dragend", () => {
    container.querySelectorAll(".nav-dragging, .nav-drop-target").forEach((item) => {
      item.classList.remove("nav-dragging", "nav-drop-target");
    });
    draggedKey = "";
  });
}

function enableDevPanelTabs(tabs) {
  const storageKey = tabs.dataset.tabStorage;
  const activeKey = `${storageKey}-panel-active`;

  const activatePanel = (panelKey) => {
    const nextTab = tabs.querySelector(`[data-dev-panel="${panelKey}"]`);
    const nextPanel = document.querySelector(`[data-dev-panel-target="${panelKey}"]`);
    if (!nextTab || !nextPanel) return;
    tabs.querySelectorAll("[data-dev-panel]").forEach((item) => item.classList.toggle("active", item === nextTab));
    document.querySelectorAll("[data-dev-panel-target]").forEach((panel) => {
      panel.classList.toggle("active", panel === nextPanel);
    });
    localStorage.setItem(activeKey, panelKey);
    if (history.replaceState) history.replaceState(null, "", `#${panelKey}`);
  };

  tabs.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-dev-panel]");
    if (!tab) return;
    const nextPanel = document.querySelector(`[data-dev-panel-target="${tab.dataset.devPanel}"]`);
    if (!nextPanel) return;
    event.preventDefault();
    activatePanel(tab.dataset.devPanel);
  });

  const hashPanel = window.location.hash ? window.location.hash.slice(1) : "";
  const savedPanel = localStorage.getItem(activeKey);
  activatePanel(hashPanel || savedPanel || tabs.querySelector("[data-dev-panel]")?.dataset.devPanel);
}

document.querySelectorAll(".dev-tabs[data-tab-storage]").forEach((tabs) => {
  enableSortableTabs(tabs, "[data-dev-tab-key]", "devTabKey", tabs.dataset.tabStorage);
  if (tabs.querySelector("[data-dev-panel]")) enableDevPanelTabs(tabs);
});

document.querySelectorAll(".dev-admin-tabs[data-tab-storage]").forEach((tabs) => {
  enableSortableTabs(tabs, "[data-dev-panel]", "devPanel", tabs.dataset.tabStorage);
  enableDevPanelTabs(tabs);
});

document.querySelectorAll("form[data-submit-status]").forEach((form) => {
  form.addEventListener("submit", () => {
    if (form.dataset.submitting === "true") return;
    form.dataset.submitting = "true";

    let status = form.nextElementSibling?.classList.contains("submit-status")
      ? form.nextElementSibling
      : form.querySelector(".submit-status") || form.closest("section, article, tr, .panel")?.querySelector(".submit-status");
    if (!status) {
      status = document.createElement("div");
      status.className = "submit-status";
      status.hidden = true;
      status.setAttribute("aria-live", "polite");
      form.insertAdjacentElement("afterend", status);
    }
    if (status) {
      status.hidden = false;
      status.innerHTML = `<span class="spinner-sm" aria-hidden="true"></span><span>${form.dataset.submitMessage || "已送出，正在處理中，請稍候。"}</span>`;
    }

    form.querySelectorAll("button[type='submit']").forEach((button) => {
      button.dataset.originalText = button.textContent || "";
      button.disabled = true;
      button.classList.add("is-busy");
      button.textContent = button.dataset.busyText || "處理中";
    });
  });
});

function setTopologyFullscreen(panel, enabled) {
  if (!panel) return;
  panel.classList.toggle("topology-client-fullscreen", enabled);
  document.body.classList.toggle("body-topology-fullscreen", enabled);
}

document.querySelectorAll("[data-topology-fullscreen-enter]").forEach((button) => {
  button.addEventListener("click", async () => {
    const panel = document.querySelector("[data-topology-panel]");
    if (!panel) {
      const fallback = button.dataset.fullscreenUrl;
      if (fallback) window.location.href = fallback;
      return;
    }
    setTopologyFullscreen(panel, true);
    try {
      if (panel.requestFullscreen && !document.fullscreenElement) {
        await panel.requestFullscreen();
      }
    } catch (error) {
      // Browser fullscreen can be blocked; the fixed overlay still gives a usable full-screen workspace.
    }
  });
});

document.querySelectorAll("[data-topology-fullscreen-exit]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement && document.exitFullscreen) {
        await document.exitFullscreen();
      }
    } catch (error) {
      // Keep local overlay cleanup below even if the browser API refuses the request.
    }
    setTopologyFullscreen(document.querySelector("[data-topology-panel]"), false);
  });
});

document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) {
    setTopologyFullscreen(document.querySelector("[data-topology-panel]"), false);
  }
});

document.querySelectorAll("[data-topology-canvas]").forEach((canvas) => {
  const stage = canvas.querySelector("[data-topology-stage]");
  const value = document.querySelector("[data-topology-zoom-value]");
  const zoomIn = document.querySelector("[data-topology-zoom-in]");
  const zoomOut = document.querySelector("[data-topology-zoom-out]");
  const zoomReset = document.querySelector("[data-topology-zoom-reset]");
  if (!stage) return;

  let scale = 0.8;
  const setScale = (nextScale) => {
    scale = Math.min(1.6, Math.max(0.45, Math.round(nextScale * 100) / 100));
    stage.style.setProperty("--topology-scale", String(scale));
    if (value) value.textContent = `${Math.round(scale * 100)}%`;
  };

  zoomIn?.addEventListener("click", () => setScale(scale + 0.1));
  zoomOut?.addEventListener("click", () => setScale(scale - 0.1));
  zoomReset?.addEventListener("click", () => {
    setScale(0.8);
    canvas.scrollTo({ left: 0, top: 0, behavior: "smooth" });
  });

  canvas.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    setScale(scale + (event.deltaY < 0 ? 0.08 : -0.08));
  }, { passive: false });

  let dragging = false;
  let startX = 0;
  let startY = 0;
  let scrollLeft = 0;
  let scrollTop = 0;
  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    startX = event.clientX;
    startY = event.clientY;
    scrollLeft = canvas.scrollLeft;
    scrollTop = canvas.scrollTop;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    canvas.scrollLeft = scrollLeft - (event.clientX - startX);
    canvas.scrollTop = scrollTop - (event.clientY - startY);
  });
  canvas.addEventListener("pointerup", () => { dragging = false; });
  canvas.addEventListener("pointercancel", () => { dragging = false; });

  canvas.querySelectorAll("[data-topology-node-id]").forEach((node) => {
    node.addEventListener("click", () => {
      const form = document.querySelector("[data-topology-filter]");
      const input = form?.querySelector('input[name="failed_node"]');
      if (!form || !input) return;
      input.value = node.dataset.topologyNodeId || "";
      form.requestSubmit();
    });
  });

  setScale(scale);
});
