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
      clearTimeout(entry.timer);
      entry.timer = setTimeout(function () { resolveConflict(entry); }, 150);
    });
    nameWheels.push(entry);
  });

  /* ── a player can't be on two wheels (or play themselves) ── */
  function activeEntries() {
    return nameWheels.filter(function (entry) {
      return !(entry.partner && !isDoubles());
    });
  }

  function takenBy(entry) {
    const taken = new Set();
    activeEntries().forEach(function (other) {
      if (other === entry) return;
      const idx = other.select.selectedIndex - 1;
      if (idx >= 0) taken.add(idx);
    });
    return taken;
  }

  function refreshTaken() {
    activeEntries().forEach(function (entry) {
      const taken = takenBy(entry);
      entry.wheel.querySelectorAll(".num").forEach(function (el, i) {
        el.classList.toggle("taken", taken.has(i));
      });
    });
  }

  /* if a wheel settles on a player who is already on another wheel,
     glide to the nearest free player instead */
  function resolveConflict(entry) {
    const taken = takenBy(entry);
    let idx = entry.select.selectedIndex - 1;
    if (taken.has(idx)) {
      const count = entry.select.options.length - 1;
      for (let step = 1; step < count; step++) {
        if (idx + step < count && !taken.has(idx + step)) { idx += step; break; }
        if (idx - step >= 0 && !taken.has(idx - step)) { idx -= step; break; }
      }
      if (!taken.has(idx)) {
        entry.select.selectedIndex = idx + 1;
        entry.wheel.scrollTo({ top: idx * entry.item, behavior: "smooth" });
        highlight(entry.wheel, idx);
      }
    }
    refreshTaken();
    updateNames();
  }

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
    refreshTaken();
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

  function clampInt(v) {
    return Math.min(MAX_SCORE, Math.max(0, parseInt(v, 10) || 0));
  }

  let adjusting = false;

  /* deuce auto-fill: a winning score of 22+ sets the loser to that
     score minus 2, and a losing score of 20+ sets the winner to that
     score plus 2. Otherwise the loser simply can't reach the winner
     (win by 2, except a 30-29 finish at the cap). */
  function applyScoreRules(movedSide) {
    if (!currentWinner) return;
    const w = currentWinner;
    const l = w === "A" ? "B" : "A";
    let wv = clampInt(scoreInputs[w].value);
    let lv = clampInt(scoreInputs[l].value);

    if (movedSide === w && wv >= 22) {
      lv = wv - 2;
    } else if (movedSide === l && lv >= 20) {
      wv = Math.min(MAX_SCORE, lv + 2);
    } else {
      const cap = wv >= MAX_SCORE ? MAX_SCORE - 1 : wv - 2;
      if (lv > cap) lv = Math.max(0, cap);
    }
    if (lv >= wv) lv = Math.max(0, wv - 1);

    adjusting = true;
    if (clampInt(scoreInputs[w].value) !== wv) setScoreWheel(w, wv, true);
    if (clampInt(scoreInputs[l].value) !== lv) setScoreWheel(l, lv, true);
    clearTimeout(settleTimers.adjust);
    settleTimers.adjust = setTimeout(function () { adjusting = false; }, 400);
  }

  ["A", "B"].forEach(function (side) {
    scoreWheels[side].addEventListener("scroll", function () {
      if (!scoreItem) return;
      const value = clampInt(Math.round(scoreWheels[side].scrollTop / scoreItem));
      scoreInputs[side].value = value;
      highlight(scoreWheels[side], value);
      if (adjusting) return;
      clearTimeout(settleTimers[side]);
      settleTimers[side] = setTimeout(function () { applyScoreRules(side); }, 160);
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
      setTimeout(function () { applyScoreRules(winner); }, 200);
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
