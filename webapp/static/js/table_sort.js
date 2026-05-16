(() => {
  const NO_SORT_TEXT = new Set([
    "select",
    "action",
    "actions",
    "expand",
    "detail",
    "選取",
    "操作",
    "展開",
    "明細",
  ]);

  function headerLabel(header) {
    return (header.textContent || "").replace(/\s+/g, " ").trim();
  }

  function isSortableHeader(header) {
    if (header.getAttribute("data-sortable") === "false") return false;
    const label = headerLabel(header).replace(/\*/g, "").trim().toLowerCase();
    return Boolean(label) && !NO_SORT_TEXT.has(label);
  }

  function rowGroups(tbody) {
    const groups = [];
    Array.from(tbody.children).forEach((row) => {
      if (row.classList.contains("asset-detail-row") || row.dataset.detailRow === "true") {
        if (groups.length) groups[groups.length - 1].push(row);
        else groups.push([row]);
        return;
      }
      groups.push([row]);
    });
    return groups;
  }

  function cellText(row, index) {
    const cell = row.children[index];
    if (!cell) return "";
    return (cell.dataset.sortValue || cell.textContent || "").replace(/\s+/g, " ").trim();
  }

  function normalizeValue(value) {
    const raw = String(value || "").trim();
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(raw)) {
      return {
        type: "text",
        value: raw
          .split(".")
          .map((part) => String(Number(part)).padStart(3, "0"))
          .join("."),
      };
    }

    const compactNumber = raw.replace(/,/g, "");
    if (/^-?\d+(\.\d+)?%?$/.test(compactNumber)) {
      return { type: "number", value: Number(compactNumber.replace("%", "")) };
    }

    return { type: "text", value: raw.toLocaleLowerCase("zh-Hant") };
  }

  function compareValues(left, right) {
    const a = normalizeValue(left);
    const b = normalizeValue(right);
    if (a.type === "number" && b.type === "number") return a.value - b.value;
    return String(a.value).localeCompare(String(b.value), "zh-Hant", {
      numeric: true,
      sensitivity: "base",
    });
  }

  function applySort(table, header, index) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const nextDirection = header.dataset.sortDirection === "asc" ? "desc" : "asc";
    const groups = rowGroups(tbody);

    groups.sort((groupA, groupB) => {
      const result = compareValues(cellText(groupA[0], index), cellText(groupB[0], index));
      return nextDirection === "asc" ? result : -result;
    });

    table.querySelectorAll("th.sortable-header").forEach((item) => {
      item.classList.remove("sorted-asc", "sorted-desc");
      item.removeAttribute("aria-sort");
      delete item.dataset.sortDirection;
    });
    header.dataset.sortDirection = nextDirection;
    header.classList.add(nextDirection === "asc" ? "sorted-asc" : "sorted-desc");
    header.setAttribute("aria-sort", nextDirection === "asc" ? "ascending" : "descending");

    const fragment = document.createDocumentFragment();
    groups.forEach((group) => group.forEach((row) => fragment.appendChild(row)));
    tbody.appendChild(fragment);
  }

  function enhanceTable(table) {
    if (table.getAttribute("data-no-sort") === "true" || table.dataset.sortEnhanced === "true") return;
    const headerRow = table.tHead?.rows?.[0];
    if (!headerRow || !table.tBodies.length) return;

    Array.from(headerRow.cells).forEach((header, index) => {
      if (!isSortableHeader(header)) return;
      header.classList.add("sortable-header");
      header.tabIndex = 0;
      header.role = "button";
      header.title = `${headerLabel(header)} 排序`;
      header.addEventListener("click", () => applySort(table, header, index));
      header.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        applySort(table, header, index);
      });
    });

    table.dataset.sortEnhanced = "true";
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("table.data-table").forEach(enhanceTable);
  });
})();
