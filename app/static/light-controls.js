"use strict";
window.WallboardLightControls = (() => {
  const $ = (id) => document.getElementById(id);
  let entity = null,
    latest = null,
    pending = false,
    lastWrite = 0;
  const bound = new WeakSet();
  function close() {
    $("light-panel").hidden = true;
    entity = null;
  }
  function open(id) {
    if (state?.fire?.active) return;
    entity = id;
    lastWrite = 0;
    latest = state;
    wake();
    $("light-panel").hidden = false;
    $("light-panel-error").textContent = "";
    render();
    $("light-panel-close").focus({ preventScroll: true });
  }
  function bind(button, id) {
    if (bound.has(button)) return;
    bound.add(button);
    let timer = null,
      start = null,
      suppress = false;
    const cancel = () => {
      clearTimeout(timer);
      timer = null;
    };
    button.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || button.disabled) return;
      suppress = false;
      start = { x: e.clientX, y: e.clientY };
      cancel();
      timer = setTimeout(() => {
        timer = null;
        suppress = true;
        open(id);
      }, 550);
    });
    button.addEventListener("pointermove", (e) => {
      if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 12) {
        cancel();
        suppress = true;
      }
    });
    for (const event of ["pointerup", "pointercancel", "pointerleave"])
      button.addEventListener(event, cancel);
    button.addEventListener("contextmenu", (e) => {
      e.preventDefault();
    });
    button.onclick = (e) => {
      if (suppress) {
        suppress = false;
        e.preventDefault();
        return;
      }
      toggle(id);
    };
  }
  async function send(patch) {
    if (!entity || pending || latest?.fire?.active) return;
    pending = true;
    lastWrite = Date.now();
    $("light-panel-error").textContent = "";
    try {
      const r = await fetch("/api/light/control", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entity_id: entity, ...patch }),
        }),
        b = await r.json();
      if (!r.ok)
        throw Error(b.error || WallboardI18n.t("Lampan kunde inte ändras."));
      await poll();
    } catch (e) {
      $("light-panel-error").textContent = WallboardI18n.t(e.message);
    } finally {
      pending = false;
      render();
    }
  }
  function labels() {
    for (const [key, suffix] of [
      ["brightness", " %"],
      ["hue", "°"],
      ["saturation", " %"],
      ["kelvin", " K"],
    ])
      $("lamp-" + key + "-value").textContent = $("lamp-" + key).value + suffix;
    $("lamp-color-preview").style.backgroundColor =
      "hsl(" +
      $("lamp-hue").value +
      " " +
      $("lamp-saturation").value +
      "% 50%)";
  }
  function render() {
    if (!entity || !latest) return;
    const s = latest.states[entity],
      a = s?.attributes || {},
      cap = latest.light_controls?.[entity] || {};
    if (!s || !latest.settings.lights.includes(entity)) {
      close();
      return;
    }
    $("light-panel-name").textContent =
      latest.lights[entity] || a.friendly_name || entity;
    $("light-panel-room").textContent = latest.light_rooms?.[entity] || "";
    const online = latest.ha_online && ["on", "off"].includes(s.state);
    $("light-panel-toggle").disabled = !online;
    $("light-panel-toggle").textContent =
      s.state === "on" ? WallboardI18n.t("Släck") : WallboardI18n.t("Tänd");
    $("lamp-brightness-field").hidden = !cap.brightness;
    $("lamp-color-fields").hidden = !cap.color;
    $("lamp-temperature-field").hidden = !cap.temperature;
    $("light-panel-help").textContent = !online
      ? WallboardI18n.t("Lampan är inte tillgänglig.")
      : !cap.brightness && !cap.color && !cap.temperature
        ? WallboardI18n.t("Den här lampan kan bara tändas och släckas.")
        : WallboardI18n.t("Ändringar skickas när du släpper reglaget.");
    for (const input of document.querySelectorAll("#light-panel input"))
      input.disabled = !online || pending;
    if (
      !pending &&
      Date.now() - lastWrite > 1500 &&
      !$("light-panel").contains(document.activeElement?.closest("input"))
    ) {
      $("lamp-brightness").value =
        Math.round(((a.brightness ?? 128) / 255) * 100) || 1;
      $("lamp-hue").value = a.hs_color?.[0] ?? 0;
      $("lamp-saturation").value = a.hs_color?.[1] ?? 100;
      $("lamp-kelvin").min = cap.min_kelvin || 2000;
      $("lamp-kelvin").max = cap.max_kelvin || 6500;
      $("lamp-kelvin").value =
        a.color_temp_kelvin ||
        Math.round((cap.min_kelvin + cap.max_kelvin) / 2) ||
        3000;
    }
    labels();
  }
  $("light-panel-close").onclick = close;
  $("light-panel-toggle").onclick = () => {
    if (entity) toggle(entity);
  };
  for (const id of ["brightness", "hue", "saturation", "kelvin"])
    $("lamp-" + id).oninput = labels;
  $("lamp-brightness").onchange = () =>
    send({ brightness_pct: Number($("lamp-brightness").value) });
  for (const id of ["hue", "saturation"])
    $("lamp-" + id).onchange = () =>
      send({
        hs_color: [
          Number($("lamp-hue").value),
          Number($("lamp-saturation").value),
        ],
      });
  $("lamp-kelvin").onchange = () =>
    send({ color_temp_kelvin: Number($("lamp-kelvin").value) });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("light-panel").hidden) close();
  });
  function update(s) {
    latest = s;
    if (s.fire?.active || s.mode !== "active") close();
    else render();
  }
  document.addEventListener("DOMContentLoaded", () =>
    document
      .querySelectorAll(".light")
      .forEach((b) => bind(b, b.dataset.entity)),
  );
  return Object.freeze({ bind, open, close, update });
})();
