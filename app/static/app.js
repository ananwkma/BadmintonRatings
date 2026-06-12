// Two-step game recorder: players & winner first, then score sliders.
(function () {
  const form = document.getElementById("match-form");
  if (!form) return;

  const sliders = {
    A: form.querySelector("input[name=score_a]"),
    B: form.querySelector("input[name=score_b]"),
  };
  const error = form.querySelector(".form-error");
  let currentWinner =
    (form.querySelector("input[name=winner]:checked") || {}).value || null;

  /* singles / doubles partner fields */
  function updateType() {
    const doubles =
      form.querySelector("input[name=match_type]:checked").value === "doubles";
    form.querySelectorAll(".doubles-only").forEach(function (input) {
      input.style.display = doubles ? "" : "none";
      input.required = doubles;
      if (!doubles) input.value = "";
    });
    updateNames();
  }

  /* side labels shown on the winner buttons and score readouts */
  function sideLabel(side) {
    const key = side === "A" ? "a" : "b";
    const names = ["1", "2"]
      .map(function (slot) {
        const select = form.querySelector(`select[name=side_${key}_${slot}]`);
        const option = select && select.selectedOptions[0];
        return option && option.value ? option.textContent.trim() : null;
      })
      .filter(Boolean);
    return names.length ? names.join(" & ") : `Side ${side === "A" ? 1 : 2}`;
  }

  function updateNames() {
    ["A", "B"].forEach(function (side) {
      form.querySelectorAll(`.winner-name[data-side=${side}], .score-name[data-side=${side}]`)
        .forEach(function (el) { el.textContent = sideLabel(side); });
    });
  }

  function updateValues() {
    document.getElementById("score_a_value").textContent = sliders.A.value;
    document.getElementById("score_b_value").textContent = sliders.B.value;
  }

  function playersChosen() {
    const doubles =
      form.querySelector("input[name=match_type]:checked").value === "doubles";
    const fields = doubles
      ? ["side_a_1", "side_a_2", "side_b_1", "side_b_2"]
      : ["side_a_1", "side_b_1"];
    const values = fields.map(function (f) {
      return form.querySelector(`select[name=${f}]`).value;
    });
    if (values.some(function (v) { return !v; })) {
      return "Select all the players first.";
    }
    if (new Set(values).size !== values.length) {
      return "A player can only appear once in a game.";
    }
    return null;
  }

  function goToStep(step) {
    form.classList.toggle("step-2", step === 2);
  }

  /* winner buttons: validate players, preset sliders, slide to scores */
  form.querySelectorAll(".winner-btn").forEach(function (label) {
    label.addEventListener("click", function (event) {
      const problem = playersChosen();
      if (problem) {
        event.preventDefault();
        error.textContent = problem;
        error.hidden = false;
        return;
      }
      error.hidden = true;
      const side = label.querySelector("input").value;
      if (side !== currentWinner) {
        currentWinner = side;
        sliders[side].value = 21;
        sliders[side === "A" ? "B" : "A"].value = 15;
        updateValues();
      }
      updateNames();
      goToStep(2);
    });
  });

  form.querySelector(".back-btn").addEventListener("click", function () {
    goToStep(1);
  });

  /* "game to 21" / "game to 11" presets for the winning side */
  form.querySelectorAll(".preset-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const to = parseInt(btn.dataset.to, 10);
      const winner = currentWinner || "A";
      const loser = winner === "A" ? "B" : "A";
      sliders[winner].value = to;
      sliders[loser].value = Math.min(
        parseInt(sliders[loser].value, 10), to - 2
      );
      updateValues();
    });
  });

  ["A", "B"].forEach(function (side) {
    sliders[side].addEventListener("input", updateValues);
  });
  form.querySelectorAll("input[name=match_type]").forEach(function (radio) {
    radio.addEventListener("change", updateType);
  });
  form.querySelectorAll(".sides select").forEach(function (select) {
    select.addEventListener("change", updateNames);
  });

  updateType();
  updateValues();
  /* editing an existing game opens straight on the players step but with
     everything prefilled; recording starts there anyway */
})();
