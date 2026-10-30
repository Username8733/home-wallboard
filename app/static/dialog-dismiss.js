"use strict";
(() => {
  const panels = {
    "light-panel": () => WallboardLightControls.close(),
    "settings-panel": () => WallboardSettings.close(),
    "event-overview": () => WallboardPlannerOverview.close(),
    "timer-panel": () => WallboardTimer.close(),
  };
  for (const [id, close] of Object.entries(panels)) {
    const panel = document.getElementById(id);
    let outside = false;
    panel.addEventListener("pointerdown", (e) => {
      outside = e.target === panel;
    });
    panel.addEventListener("click", (e) => {
      if (outside && e.target === panel && !state?.fire?.active) close();
      outside = false;
    });
  }
  function installNative(doc) {
    for (const dialog of doc.querySelectorAll("dialog")) {
      if (dialog.dataset.wallboardBackdrop) return;
      dialog.dataset.wallboardBackdrop = "1";
      const outside = (e) => {
        const r = dialog.getBoundingClientRect();
        return (
          e.clientX < r.left ||
          e.clientX > r.right ||
          e.clientY < r.top ||
          e.clientY > r.bottom
        );
      };
      let beganOutside = false;
      dialog.addEventListener("pointerdown", (e) => {
        beganOutside = outside(e);
      });
      dialog.addEventListener("click", (e) => {
        if (beganOutside && outside(e)) dialog.close("cancel");
        beganOutside = false;
      });
    }
  }
  installNative(document);
  try {
    installNative(document.getElementById("planner-frame").contentDocument);
  } catch {}
  document.getElementById("planner-frame").addEventListener("load", () => {
    try {
      installNative(document.getElementById("planner-frame").contentDocument);
    } catch {}
  });
})();
