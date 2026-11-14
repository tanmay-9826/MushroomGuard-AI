(function () {
  "use strict";

  // Give file uploads a quick, accessible filename preview without uploading anything.
  document.querySelectorAll('input[type="file"]').forEach(function (input) {
    input.addEventListener("change", function () {
      var help = input.parentElement.querySelector(".field-help");
      if (help && input.files && input.files.length) {
        help.textContent = input.files[0].name;
      }
    });
  });

  // Avoid accidental double-submission of longer forms.
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var submit = form.querySelector('button[type="submit"], button:not([type])');
      if (submit && !submit.disabled && !form.hasAttribute("data-allow-repeat")) {
        submit.dataset.originalText = submit.textContent;
        submit.disabled = true;
        submit.textContent = "Please wait…";
      }
    });
  });
})();
