// Show/hide the partner inputs depending on singles vs doubles.
(function () {
  const form = document.getElementById("match-form");
  if (!form) return;

  function update() {
    const doubles = form.querySelector("input[name=match_type]:checked").value === "doubles";
    form.querySelectorAll(".doubles-only").forEach(function (input) {
      input.style.display = doubles ? "" : "none";
      input.required = doubles;
      if (!doubles) input.value = "";
    });
  }

  form.querySelectorAll("input[name=match_type]").forEach(function (radio) {
    radio.addEventListener("change", update);
  });
  update();
})();
