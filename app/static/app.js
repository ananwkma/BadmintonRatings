// Two-step game recorder: players & winner first, then a full-screen
// pair of vertical score wheels.
(function () {
  const form = document.getElementById("match-form");
  if (!form) return;
  form.classList.add("js");

  const MAX_SCORE = 30;
  const inputs = {
    A: form.querySelector("input[name=score_a]"),
    B: form.querySelector("input[name=score_b]"),
  };
  const overlay = form.querySelector(".score-overlay");
  const wheels = {
    A: overlay.querySelector(".wheel[data-side=A]"),
    B: overlay.querySelector(".wheel[data-side=B]"),
  };
  const error = form.querySelector(".form-error");
  let currentWinner =
    (form.querySelector("input[name=winner]:checked") || {}).value || null;
  let itemHeight = 0;
  const settleTimers = {};

  /* ── build the number wheels ── */
  ["A", "B"].forEach(function (side) {
    const wheel = wheels[side];
    wheel.appendChild(spacer());
    for (let v = 0; v <= MAX_SCORE; v++) {
      const num = document.createElement("div");
      num.className = "num";
      num.textContent = v;
      wheel.appendChild(num);
    }
    wheel.appendChild(spacer());
  });

  function spacer() {
    const el = document.createElement("div");
    el.className = "spacer";
    return el;
  }

  function measure() {
    itemHeight = wheels.A.querySelector(".num").offsetHeight || 1;
    ["A", "B"].forEach(function (side) {
      const pad = Math.max(0, (wheels[side].clientHeight - itemHeight) / 2);
      wheels[side].querySelectorAll(".spacer").forEach(function (sp) {
        sp.style.height = pad + "px";
      });
    });
  }

  function wheelValue(side) {
    const raw = Math.round(wheels[side].scrollTop / itemHeight);
    return Math.min(MAX_SCORE, Math.max(0, raw));
  }

  function setWheel(side, value, smooth) {
    wheels[side].scrollTo({
      top: value * itemHeight,
      behavior: smooth ? "smooth" : "auto",
    });
    inputs[side].value = value;
    highlight(side, value);
  }

  function highlight(side, value) {
    wheels[side].querySelectorAll(".num").forEach(function (el, i) {
      el.classList.toggle("sel", i === value);
    });
  }

  function loserLimit() {
    const winnerVal = parseInt(inputs[currentWinner].value, 10);
    return Math.max(0, winnerVal >= MAX_SCORE ? MAX_SCORE - 1 : winnerVal - 2);
  }

  /* the loser can never reach the winner's score: win by 2, except a
     30-29 finish at the cap */
  function clampLoser(smooth) {
    if (!currentWinner) return;
    const loser = currentWinner === "A" ? "B" : "A";
    if (parseInt(inputs[loser].value, 10) > loserLimit()) {
      setWheel(loser, loserLimit(), smooth);
    }
  }

  ["A", "B"].forEach(function (side) {
    wheels[side].addEventListener("scroll", function () {
      const value = wheelValue(side);
      inputs[side].value = value;
      highlight(side, value);
      clearTimeout(settleTimers[side]);
      settleTimers[side] = setTimeout(function () {
        clampLoser(true);
      }, 160);
    });
  });

  /* ── overlay open / close ── */
  function openOverlay() {
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("overlay-open");
    requestAnimationFrame(function () {
      measure();
      setWheel("A", parseInt(inputs.A.value, 10) || 0, false);
      setWheel("B", parseInt(inputs.B.value, 10) || 0, false);
    });
  }

  function closeOverlay() {
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overlay-open");
  }

  /* ── step 1: type, names, winner ── */
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
      const tag = overlay.querySelector(`.win-tag[data-side=${side}]`);
      tag.classList.toggle("show", side === currentWinner);
    });
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
        inputs[side].value = 21;
        inputs[side === "A" ? "B" : "A"].value = 15;
      }
      updateNames();
      openOverlay();
    });
  });

  overlay.querySelector(".back-btn").addEventListener("click", closeOverlay);

  /* "game to 21" / "game to 11" presets for the winning side */
  overlay.querySelectorAll(".preset-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const winner = currentWinner || "A";
      setWheel(winner, parseInt(btn.dataset.to, 10), true);
      setTimeout(function () { clampLoser(true); }, 180);
    });
  });

  form.querySelectorAll("input[name=match_type]").forEach(function (radio) {
    radio.addEventListener("change", updateType);
  });
  form.querySelectorAll(".sides select").forEach(function (select) {
    select.addEventListener("change", updateNames);
  });
  window.addEventListener("resize", function () {
    if (overlay.classList.contains("open")) {
      measure();
      setWheel("A", parseInt(inputs.A.value, 10) || 0, false);
      setWheel("B", parseInt(inputs.B.value, 10) || 0, false);
    }
  });

  updateType();
})();
