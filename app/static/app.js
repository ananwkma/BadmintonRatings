// Game recorder: big type buttons, player name wheels, tap the winning
// side, then full-screen score wheels.
(function () {
  const form = document.getElementById("match-form");
  if (!form) return;
  form.classList.add("js");

  const MAX_SCORE = 30;
  const scoreInputs = {
    A: form.querySelector("input[name=score_a]"),
    B: form.querySelector("input[name=score_b]"),
  };
  const winnerRadios = {
    A: form.querySelector("input[name=winner][value=A]"),
    B: form.querySelector("input[name=winner][value=B]"),
  };
  const overlay = form.querySelector(".score-overlay");
  const scoreWheels = {
    A: overlay.querySelector(".wheel[data-side=A]"),
    B: overlay.querySelector(".wheel[data-side=B]"),
  };
  const error = form.querySelector(".form-error");
  let currentWinner =
    (form.querySelector("input[name=winner]:checked") || {}).value || null;
  const settleTimers = {};

  /* ── shared wheel helpers ── */
  function spacer() {
    const el = document.createElement("div");
    el.className = "spacer";
    return el;
  }

  function fillWheel(wheel, labels) {
    wheel.appendChild(spacer());
    labels.forEach(function (text) {
      const num = document.createElement("div");
      num.className = "num";
      num.textContent = text;
      wheel.appendChild(num);
    });
    wheel.appendChild(spacer());
  }

  function measure(wheel) {
    const num = wheel.querySelector(".num");
    const item = num ? num.offsetHeight : 0;
    if (item) {
      const pad = Math.max(0, (wheel.clientHeight - item) / 2);
      wheel.querySelectorAll(".spacer").forEach(function (sp) {
        sp.style.height = pad + "px";
      });
    }
    return item;
  }

  function highlight(wheel, idx) {
    wheel.querySelectorAll(".num").forEach(function (el, i) {
      el.classList.toggle("sel", i === idx);
    });
  }

  function isDoubles() {
    return form.querySelector("input[name=match_type]:checked").value === "doubles";
  }

  /* ── player name wheels ── */
  const nameWheels = [];
  [["side_a_1", "A", false], ["side_a_2", "A", true],
   ["side_b_1", "B", false], ["side_b_2", "B", true]].forEach(function (cfg) {
    const select = form.querySelector(`select[name=${cfg[0]}]`);
    const container = form.querySelector(`.name-wheels[data-side=${cfg[1]}]`);
    if (!select || !container) return;
    const labels = Array.from(select.options).slice(1).map(function (o) {
      return o.textContent.trim();
    });
    const wheel = document.createElement("div");
    wheel.className = "nwheel" + (cfg[2] ? " partner" : "");
    fillWheel(wheel, labels);
    container.appendChild(wheel);
    const entry = { select: select, wheel: wheel, partner: cfg[2], item: 0 };

    wheel.addEventListener("scroll", function () {
      if (!entry.item) return;
      const idx = Math.min(
        labels.length - 1,
        Math.max(0, Math.round(wheel.scrollTop / entry.item))
      );
      select.selectedIndex = idx + 1;
      highlight(wheel, idx);
      clearTimeout(settleTimers.names);
      settleTimers.names = setTimeout(updateNames, 120);
    });
    /* tapping a name that isn't centered selects it instead of
       declaring the winner */
    wheel.addEventListener("click", function (event) {
      const num = event.target.closest(".num");
      if (num && !num.classList.contains("sel")) {
        event.stopPropagation();
        const idx = Array.from(wheel.querySelectorAll(".num")).indexOf(num);
        wheel.scrollTo({ top: idx * entry.item, behavior: "smooth" });
      }
    });
    nameWheels.push(entry);
  });

  function initNameWheels() {
    const active = nameWheels.filter(function (entry) {
      return !(entry.partner && !isDoubles());
    });
    const used = new Set(active
      .map(function (entry) { return entry.select.selectedIndex - 1; })
      .filter(function (idx) { return idx >= 0; }));
    active.forEach(function (entry) {
      entry.item = measure(entry.wheel) || entry.item;
      if (!entry.item) return;
      let idx = entry.select.selectedIndex - 1;
      if (idx < 0) {
        // default to the first player not already on another wheel
        const count = entry.select.options.length - 1;
        idx = 0;
        while (used.has(idx) && idx < count - 1) idx += 1;
        used.add(idx);
      }
      entry.select.selectedIndex = idx + 1;
      entry.wheel.scrollTo({ top: idx * entry.item });
      highlight(entry.wheel, idx);
    });
    updateNames();
  }

  /* ── side labels everywhere ── */
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
      form.querySelectorAll(`.score-name[data-side=${side}]`)
        .forEach(function (el) { el.textContent = sideLabel(side); });
      const tag = overlay.querySelector(`.win-tag[data-side=${side}]`);
      tag.classList.toggle("show", side === currentWinner);
    });
  }

  function playersChosen() {
    const fields = isDoubles()
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

  /* ── tap a side to declare the winner ── */
  form.querySelectorAll(".pick-half").forEach(function (half) {
    half.addEventListener("click", function () {
      const problem = playersChosen();
      if (problem) {
        error.textContent = problem;
        error.hidden = false;
        return;
      }
      error.hidden = true;
      const side = half.dataset.side;
      winnerRadios[side].checked = true;
      if (side !== currentWinner) {
        currentWinner = side;
        scoreInputs[side].value = 21;
        scoreInputs[side === "A" ? "B" : "A"].value = 15;
      }
      form.querySelectorAll(".pick-half").forEach(function (h) {
        h.classList.toggle("win-sel", h === half);
      });
      updateNames();
      setTimeout(openOverlay, 170);
    });
  });

  /* ── match type ── */
  function updateType() {
    const doubles = isDoubles();
    form.dataset.type = doubles ? "doubles" : "singles";
    form.querySelectorAll(".native-pick.doubles-only").forEach(function (sel) {
      sel.required = doubles;
      if (!doubles) sel.value = "";
    });
    requestAnimationFrame(initNameWheels);
  }
  form.querySelectorAll("input[name=match_type]").forEach(function (radio) {
    radio.addEventListener("change", updateType);
  });

  /* ── full-screen score wheels ── */
  let scoreItem = 0;
  ["A", "B"].forEach(function (side) {
    const labels = [];
    for (let v = 0; v <= MAX_SCORE; v++) labels.push(v);
    fillWheel(scoreWheels[side], labels);
  });

  function setScoreWheel(side, value, smooth) {
    scoreWheels[side].scrollTo({
      top: value * scoreItem,
      behavior: smooth ? "smooth" : "auto",
    });
    scoreInputs[side].value = value;
    highlight(scoreWheels[side], value);
  }

  function loserLimit() {
    const winnerVal = parseInt(scoreInputs[currentWinner].value, 10);
    return Math.max(0, winnerVal >= MAX_SCORE ? MAX_SCORE - 1 : winnerVal - 2);
  }

  /* the loser can never reach the winner's score: win by 2, except a
     30-29 finish at the cap */
  function clampLoser(smooth) {
    if (!currentWinner) return;
    const loser = currentWinner === "A" ? "B" : "A";
    if (parseInt(scoreInputs[loser].value, 10) > loserLimit()) {
      setScoreWheel(loser, loserLimit(), smooth);
    }
  }

  ["A", "B"].forEach(function (side) {
    scoreWheels[side].addEventListener("scroll", function () {
      if (!scoreItem) return;
      const value = Math.min(
        MAX_SCORE,
        Math.max(0, Math.round(scoreWheels[side].scrollTop / scoreItem))
      );
      scoreInputs[side].value = value;
      highlight(scoreWheels[side], value);
      clearTimeout(settleTimers[side]);
      settleTimers[side] = setTimeout(function () { clampLoser(true); }, 160);
    });
  });

  function openOverlay() {
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("overlay-open");
    requestAnimationFrame(function () {
      scoreItem = measure(scoreWheels.A) || scoreItem;
      measure(scoreWheels.B);
      setScoreWheel("A", parseInt(scoreInputs.A.value, 10) || 0, false);
      setScoreWheel("B", parseInt(scoreInputs.B.value, 10) || 0, false);
    });
  }

  function closeOverlay() {
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overlay-open");
  }

  overlay.querySelector(".back-btn").addEventListener("click", closeOverlay);

  overlay.querySelectorAll(".preset-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const winner = currentWinner || "A";
      setScoreWheel(winner, parseInt(btn.dataset.to, 10), true);
      setTimeout(function () { clampLoser(true); }, 180);
    });
  });

  window.addEventListener("resize", function () {
    initNameWheels();
    if (overlay.classList.contains("open")) {
      scoreItem = measure(scoreWheels.A) || scoreItem;
      measure(scoreWheels.B);
      setScoreWheel("A", parseInt(scoreInputs.A.value, 10) || 0, false);
      setScoreWheel("B", parseInt(scoreInputs.B.value, 10) || 0, false);
    }
  });

  updateType();
})();
