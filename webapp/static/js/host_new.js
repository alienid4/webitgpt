(function () {
  function initNetworkFill() {
    document.querySelectorAll("[data-fill-target]").forEach(function (select) {
      select.addEventListener("change", function () {
        var targetName = select.getAttribute("data-fill-target");
        var form = select.closest("form");
        if (!form || !targetName || !select.value) {
          return;
        }
        var input = form.querySelector('[name="' + targetName + '"]');
        if (input) {
          input.value = select.value;
          input.focus();
        }
      });
    });
  }

  function openHashTarget() {
    if (!window.location.hash) {
      return;
    }
    var target = document.querySelector(window.location.hash);
    if (target && target.tagName === "DETAILS") {
      target.open = true;
      target.scrollIntoView({ block: "start" });
    }
  }

  function initStepLinks() {
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
      link.addEventListener("click", function () {
        window.setTimeout(openHashTarget, 0);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initNetworkFill();
    initStepLinks();
    openHashTarget();
  });
  window.addEventListener("hashchange", openHashTarget);
})();
