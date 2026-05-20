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

  document.addEventListener("DOMContentLoaded", initNetworkFill);
})();
