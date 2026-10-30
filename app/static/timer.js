"use strict";
window.WallboardTimer = (() => {
  const $ = (id) => document.getElementById(id);
  let value = null,
    received = performance.now(),
    announced = false,
    fire = false,
    booted = false;
  const format = (seconds) => {
    seconds = Math.max(0, Math.ceil(seconds));
    const h = Math.floor(seconds / 3600),
      m = Math.floor((seconds % 3600) / 60),
      s = seconds % 60;
    return (
      (h ? h + ":" : "") +
      String(m).padStart(2, "0") +
      ":" +
      String(s).padStart(2, "0")
    );
  };
  function remaining() {
    return value?.status === "running"
      ? Math.max(0, value.remaining - (performance.now() - received) / 1000)
      : value?.remaining || 0;
  }
  function open() {
    if (!value && state?.timer) update(state);
    if (fire) return;
    wake();
    $("timer-panel").hidden = false;
    render();
    $("timer-close").focus({ preventScroll: true });
  }
  function close() {
    if (value?.status === "finished") {
      command({ action: "dismiss" }).then((ok) => {
        if (ok) $("timer-panel").hidden = true;
      });
      return;
    }
    $("timer-panel").hidden = true;
    WallboardKeyboard.hide();
  }
  async function command(body) {
    if (fire) return;
    $("timer-error").textContent = "";
    try {
      const r = await fetch("/api/timer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
        b = await r.json();
      if (!r.ok)
        throw Error(b.error || WallboardI18n.t("Timern kunde inte ändras."));
      value = b.timer;
      received = performance.now();
      if (state) state.timer = value;
      render();
      return true;
    } catch (e) {
      $("timer-error").textContent = WallboardI18n.t(e.message);
      return false;
    }
  }
  function render() {
    if (!value) return;
    const status = value.status,
      time = format(remaining());
    $("timer-countdown").textContent =
      status === "idle"
        ? format(
            Number($("timer-minutes").value) * 60 +
              Number($("timer-seconds").value),
          )
        : time;
    $("timer-tile-time").textContent =
      status === "idle"
        ? WallboardI18n.t("Starta timer")
        : status === "finished"
          ? WallboardI18n.t("Tiden är ute")
          : time;
    $("timer-tile-status").textContent =
      status === "running"
        ? WallboardI18n.t("Pågår · Tryck för att öppna")
        : status === "paused"
          ? WallboardI18n.t("Pausad")
          : status === "finished"
            ? WallboardI18n.t("Tryck för att kvittera")
            : WallboardI18n.t("Tryck för att välja tid");
    $("timer-status").textContent =
      status === "finished"
        ? WallboardI18n.t("Tiden är ute!")
        : status === "paused"
          ? WallboardI18n.t("Timern är pausad.")
          : status === "running"
            ? WallboardI18n.t("Nedräkningen fortsätter även när du byter vy.")
            : WallboardI18n.t(
                "Välj tid och tryck Starta. Skärmen väcks när tiden är ute.",
              );
    $("timer-form").hidden = status !== "idle";
    document.querySelector(".timer-running-actions").hidden = ![
      "running",
      "paused",
    ].includes(status);
    $("timer-dismiss").hidden = status !== "finished";
    $("timer-pause").textContent =
      status === "paused"
        ? WallboardI18n.t("Fortsätt")
        : WallboardI18n.t("Pausa");
    $("timer-panel").classList.toggle("timer-finished", status === "finished");
    $("open-timer").classList.toggle("timer-running", status === "running");
  }
  function update(s) {
    fire = !!s.fire?.active;
    value = s.timer || value;
    received = performance.now();
    if (!value) return;
    if (!booted) {
      booted = true;
      $("timer-minutes").value = Math.floor(value.duration / 60);
      $("timer-seconds").value = value.duration % 60;
    }
    if (fire) {
      $("timer-panel").hidden = true;
      announced = false;
    } else if (value.status === "finished" && !announced) {
      announced = true;
      manualPhotos = false;
      document.body.classList.remove("sleep");
      WallboardKeyboard.hide();
      window.WallboardSettings?.isOpen && WallboardSettings.close();
      open();
    }
    if (value.status !== "finished") announced = false;
    render();
  }
  $("open-timer").onclick = open;
  $("timer-close").onclick = close;
  $("timer-form").onsubmit = async (e) => {
    e.preventDefault();
    const seconds =
      Number($("timer-minutes").value) * 60 + Number($("timer-seconds").value);
    if (!Number.isInteger(seconds) || seconds < 1 || seconds > 86400) {
      $("timer-error").textContent = WallboardI18n.t(
        "Välj en tid mellan 1 sekund och 24 timmar.",
      );
      return;
    }
    WallboardKeyboard.hide();
    await command({ action: "start", seconds });
  };
  for (const b of document.querySelectorAll("[data-timer-minutes]"))
    b.onclick = () => {
      $("timer-minutes").value = b.dataset.timerMinutes;
      $("timer-seconds").value = 0;
      render();
    };
  for (const id of ["timer-minutes", "timer-seconds"]) $(id).oninput = render;
  $("timer-pause").onclick = () =>
    command({ action: value?.status === "paused" ? "resume" : "pause" });
  $("timer-reset").onclick = () => command({ action: "reset" });
  $("timer-dismiss").onclick = async () => {
    if (await command({ action: "dismiss" })) {
      $("timer-panel").hidden = true;
      wake();
    }
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("timer-panel").hidden) close();
  });
  document.addEventListener("DOMContentLoaded", () => {
    if (state?.timer) update(state);
  });
  setInterval(render, 250);
  return Object.freeze({ update, open, close });
})();
