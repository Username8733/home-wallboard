"use strict";
window.WallboardPages = (() => {
  const tabs = {
    home: document.getElementById("tab-home"),
    planner: document.getElementById("tab-planner"),
    music: document.getElementById("tab-music"),
    security: document.getElementById("tab-security"),
  };
  const frame = document.getElementById("planner-frame"),
    fireView = document.getElementById("fire-view");
  const dialog = document.getElementById("mute-confirm");
  let page = "home",
    fireActive = false,
    alarmKey = "",
    currentMute = null,
    latest = null;
  function setPage(next) {
    if (fireActive || !tabs[next]) return;
    window.WallboardPlannerOverview?.close();
    window.WallboardKeyboard?.hide();
    window.WallboardSecurity?.closeCamera();
    const changed = page !== next || !document.body.dataset.page;
    page = next;
    window.dispatchEvent(
      new CustomEvent("wallboard-page-change", { detail: { page } }),
    );
    document.body.dataset.page = page;
    document.getElementById("dashboard").hidden = page !== "home";
    document.getElementById("planner-page").hidden = page !== "planner";
    document.getElementById("security-page").hidden = page !== "security";
    document.getElementById("music-page").hidden = page !== "music";
    if (page === "home") window.WallboardHomeAgenda?.refresh();
    if (page === "music") window.WallboardMusic?.show();
    window.WallboardSecurity?.setVisible(page === "security");
    for (const [key, tab] of Object.entries(tabs)) {
      tab.setAttribute("aria-selected", String(key === page));
      tab.tabIndex = key === page ? 0 : -1;
    }
    if (page === "planner" && !frame.getAttribute("src"))
      frame.src = "/planner/";
    if (changed)
      fetch("/api/control/view", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page }),
      }).catch(() => {});
    wake();
  }
  for (const [key, tab] of Object.entries(tabs))
    tab.onclick = () => setPage(key);
  document.getElementById("dashboard-nav").addEventListener("keydown", (e) => {
    if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
      e.preventDefault();
      const keys = Object.keys(tabs),
        step = e.key === "ArrowRight" ? 1 : -1;
      setPage(keys[(keys.indexOf(page) + step + keys.length) % keys.length]);
      tabs[page].focus();
    }
  });
  frame.addEventListener("load", () => {
    try {
      const doc = frame.contentDocument;
      if (!doc || (!doc.querySelector("#app") && !doc.querySelector("script")))
        throw Error("Planner unavailable");
      doc.addEventListener("pointerdown", () => wake(), { passive: true });
      const readyBridge = doc.createElement("script");
      readyBridge.textContent =
        "window.wallboardPlannerReady=()=>sharedSettings.ready;window.wallboardOpenToday=async(date)=>{month=makeDate(date);month.setDate(1);render();await refreshOnline(true);openDay(date);};";
      doc.head.append(readyBridge);
      readyBridge.remove();
      WallboardPlannerOverview.install(frame);
      WallboardKeyboard.attach(doc);
      document.getElementById("planner-retry").hidden = true;
      sendPlannerContext();
    } catch {
      document.getElementById("planner-retry").hidden = false;
    }
  });
  document.getElementById("planner-retry").onclick = () => {
    frame.src = "/planner/";
  };
  function sendPlannerContext() {
    if (!frame.getAttribute("src") || !latest) return;
    const sensors = Object.values(latest.states)
      .filter(
        (s) =>
          s.entity_id.startsWith("sensor.") &&
          s.attributes?.unit_of_measurement === "°C",
      )
      .map((s) => ({
        id: s.entity_id,
        name: s.attributes.friendly_name || s.entity_id,
        state: s.state,
        unit: "°C",
        updated: new Date().toISOString(),
      }));
    frame.contentWindow?.postMessage(
      { type: "hemma-temperature-states-v1", sensors },
      location.origin,
    );
    try {
      const doc = frame.contentDocument;
      if (!doc) return;
      const localeKey = WallboardI18n.language + ":" + WallboardI18n.timeFormat;
      if (
        doc.documentElement.dataset.wallboardLocale !== localeKey &&
        typeof frame.contentWindow.plannerSnapshot === "function"
      ) {
        const bridge = doc.createElement("script");
        bridge.textContent = `(()=>{const language=${JSON.stringify(WallboardI18n.language)}, timeFormat=${JSON.stringify(WallboardI18n.timeFormat)};preferences.language=language;preferences.timeFormat=timeFormat;setLanguage(language);applyStaticLanguage();applyTimePreferences();render();})();`;
        doc.head.append(bridge);
        bridge.remove();
        doc.documentElement.dataset.wallboardLocale = localeKey;
      }
      const accountPanel = doc.getElementById("icloud-connection-panel");
      if (accountPanel) {
        let link = doc.getElementById("wallboard-icloud-account-link");
        if (!link) {
          link = doc.createElement("button");
          link.id = "wallboard-icloud-account-link";
          link.type = "button";
          link.className = "wb-icloud-account-link";
          link.onclick = async () => {
            await WallboardSettings.open();
            WallboardSettingsNavigation.open("accounts");
          };
          accountPanel
            .querySelector("summary")
            ?.insertAdjacentElement("afterend", link);
        }
        link.textContent = WallboardI18n.t("Hantera iCloud i Konton");
        const summary = accountPanel.querySelector("summary");
        if (summary) summary.textContent = WallboardI18n.t("iCloud-kalender");
      }
      const theme = document.documentElement.dataset.theme;
      const mode = ["morning", "day"].includes(theme) ? "light" : "dark";
      // Adapt the embedded view only; never overwrite the family's saved appearance.
      doc.documentElement.dataset.theme = "ios";
      doc.documentElement.dataset.mode = mode;
      doc.documentElement.style.colorScheme = mode;
      let style = doc.getElementById("wallboard-frame-style");
      if (!style) {
        style = doc.createElement("style");
        style.id = "wallboard-frame-style";
        doc.head.append(style);
      }
      const css = window.WallboardPlannerStyle;
      if (css && style.textContent !== css) style.textContent = css;
      doc.documentElement.dataset.wallboardTheme = theme;
      const palette = getComputedStyle(document.documentElement);
      const mapped = {
        "--text": "--text",
        "--muted": "--muted",
        "--accent": "--accent",
        "--focus": "--accent",
        "--surface": "--card",
        "--control": "--tile",
        "--glass": "--card",
        "--glass-line": "--line",
        "--border": "--line",
        "--line": "--line",
        "--wb-bg": "--bg",
        "--wb-shadow": "--shadow",
      };
      for (const [target, source] of Object.entries(mapped))
        doc.documentElement.style.setProperty(
          target,
          palette.getPropertyValue(source),
        );
      doc.documentElement.style.setProperty(
        "--on-accent",
        mode === "light" ? "#fff" : palette.getPropertyValue("--bg"),
      );
    } catch {}
  }
  window.addEventListener("message", (e) => {
    if (
      e.origin === location.origin &&
      e.source === frame.contentWindow &&
      e.data?.type === "hemma-temperature-ready-v1"
    )
      sendPlannerContext();
  });
  function detectorRow(a) {
    const el = document.createElement("article");
    el.className = "fire-detector";
    const info = document.createElement("div"),
      name = document.createElement("h2"),
      kind = document.createElement("p");
    name.textContent = a.name;
    kind.textContent =
      a.kind +
      (a.confirmed
        ? WallboardI18n.t(" · Aktiv signal")
        : WallboardI18n.t(" · Senast kända larm — väntar på bekräftad status"));
    info.append(name, kind);
    el.append(info);
    const control = document.createElement("div");
    control.className = "fire-control";
    const button = document.createElement("button");
    button.textContent = WallboardI18n.t("Tysta / Mute");
    button.disabled = !a.mute_available;
    button.onclick = () => {
      currentMute = a.entity_id;
      document.getElementById("mute-name").textContent = a.name;
      dialog.showModal();
    };
    control.append(button);
    if (a.mute_reason) {
      const reason = document.createElement("small");
      reason.textContent = WallboardI18n.t(a.mute_reason);
      control.append(reason);
    }
    el.append(control);
    return el;
  }
  dialog.addEventListener("close", async () => {
    if (dialog.returnValue !== "confirm" || !currentMute) return;
    const entity = currentMute;
    currentMute = null;
    const out = document.getElementById("fire-feedback");
    out.textContent = WallboardI18n.t("Skickar tystningskommando…");
    try {
      const r = await fetch("/api/fire/mute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entity, confirmed: true }),
      });
      const body = await r.json();
      if (!r.ok)
        throw Error(
          body.error ||
            WallboardI18n.t(
              "Kunde inte skicka kommandot. Kontrollera detektorn på plats.",
            ),
        );
      out.textContent = WallboardI18n.t(body.message);
    } catch (e) {
      out.textContent =
        WallboardI18n.t(e.message) ||
        WallboardI18n.t("Anslutningen bröts. Kontrollera detektorn på plats.");
    }
  });
  function update(s) {
    latest = s;
    const fire = s.fire || { active: false, alarms: [], online: s.ha_online };
    if (fire.active && !fireActive) {
      WallboardPlannerOverview.close();
      WallboardKeyboard.hide();
      manualPhotos = false;
      document.body.classList.remove("sleep");
      fireView.hidden = false;
      document.getElementById("fire-feedback").textContent = "";
    }
    if (!fire.active && fireActive) {
      fireView.hidden = true;
      if (dialog.open) dialog.close("cancel");
      alarmKey = "";
    }
    fireActive = fire.active;
    document.body.classList.toggle("fire-active", fireActive);
    if (fireActive) {
      const key = JSON.stringify(fire.alarms);
      if (key !== alarmKey) {
        document
          .getElementById("fire-detectors")
          .replaceChildren(...fire.alarms.map(detectorRow));
        alarmKey = key;
      }
      document.getElementById("fire-connection").textContent = fire.online
        ? WallboardI18n.t("Live från Home Assistant")
        : WallboardI18n.t(
            "Anslutningen till Home Assistant saknas. Senast kända brandlarm ligger kvar.",
          );
      if (
        dialog.open &&
        !fire.alarms.some(
          (a) => a.entity_id === currentMute && a.mute_available,
        )
      )
        dialog.close("cancel");
    }
    window.WallboardLightControls?.update(s);
    window.WallboardTimer?.update(s);
    window.WallboardMusic?.update(s);
    window.WallboardForecast?.update(s);
    sendPlannerContext();
    window.WallboardSecurity?.update(s, { page, fireActive });
  }
  async function readyPlanner() {
    if (!frame.getAttribute("src")) frame.src = "/planner/";
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      if (frame.contentWindow?.wallboardPlannerReady?.()) return frame;
      await new Promise((resolve) => setTimeout(resolve, 150));
    }
    throw new Error("Planner unavailable");
  }
  return Object.freeze({
    readyPlanner,
    update,
    setPage,
    get page() {
      return page;
    },
  });
})();
