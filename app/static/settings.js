"use strict";
window.WallboardSettings = (() => {
  const $ = (id) => document.getElementById(id),
    panel = $("settings-panel"),
    form = $("settings-form");
  let current = null,
    openedSettings = null,
    lights = {},
    rooms = {},
    booted = false,
    maxLights = 9,
    photoSources = null,
    temperatureSensors = {},
    weatherEntities = {},
    appearanceDraft = null,
    themeBusy = false,
    themeSave = Promise.resolve();
  const bools = [
    "show_help_text",
    "night_mode_enabled",
    "presence_enabled",
    "keyboard_auto",
    "show_weather",
    "show_home",
    "show_people",
    "show_lights",
    "show_temperatures",
    "show_photos",
  ];
  const ints = [
    "idle_seconds",
    "slide_seconds",
    "active_brightness",
    "idle_brightness",
    "timer_volume",
  ];
  function notice(message) {
    const el = $("ui-notice");
    el.textContent = message;
    el.hidden = false;
    setTimeout(() => {
      el.hidden = true;
    }, 6000);
  }
  function fill(p) {
    for (const k of bools) form.elements[k].checked = p[k];
    for (const k of ints) form.elements[k].value = p[k];
    for (const k of [
      "screen_mode",
      "start_dashboard",
      "timer_sound",
      "theme",
      "language",
      "time_format",
      "night_start",
      "night_end",
    ])
      form.elements[k].value = p[k];
    const grouped = new Map();
    for (const [id, name] of Object.entries(lights)) {
      const room = rooms[id] || "Rum saknas i HA";
      if (!grouped.has(room)) grouped.set(room, []);
      grouped.get(room).push([id, name]);
    }
    $("settings-lights").replaceChildren(
      ...[...grouped.entries()]
        .sort(([a], [b]) => a.localeCompare(b, WallboardI18n.locale()))
        .map(([room, items]) => {
          const group = document.createElement("section");
          group.className = "settings-light-room";
          const heading = document.createElement("h3");
          heading.textContent =
            room === "Rum saknas i HA" ? WallboardI18n.t(room) : room;
          if (room === "Rum saknas i HA") heading.dataset.i18n = room;
          const choices = document.createElement("div");
          choices.className = "settings-room-lights";
          for (const [id, name] of items.sort((a, b) =>
            a[1].localeCompare(b[1], WallboardI18n.locale()),
          )) {
            const label = document.createElement("label"),
              input = document.createElement("input");
            input.type = "checkbox";
            input.name = "lights";
            input.value = id;
            input.checked = p.lights.includes(id);
            label.append(input, document.createTextNode(name));
            choices.append(label);
          }
          group.append(heading, choices);
          return group;
        }),
    );
    for (const input of form.querySelectorAll("input[name=timer_outputs]"))
      input.checked = p.timer_outputs.includes(input.value);
    window.WallboardPhotoSettings?.fill(p, photoSources);
    window.WallboardWeatherSettings?.fill(
      p,
      temperatureSensors,
      weatherEntities,
    );
    appearanceDraft = {
      theme: p.theme,
      language: p.language,
      time_format: p.time_format,
      show_help_text: p.show_help_text,
    };
    apply(current || p);
    WallboardTimeFields.render();
    limitLights();
    ranges();
    $("settings-error").textContent = "";
  }
  function ranges() {
    for (const k of ["active_brightness", "idle_brightness", "timer_volume"])
      $(k + "-value").textContent = form.elements[k].value + " %";
  }
  async function open() {
    if (state?.fire?.active) return;
    wake();
    panel.hidden = false;
    WallboardSettingsNavigation.home();
    $("settings-error").textContent = "";
    try {
      const r = await fetch("/api/settings");
      if (!r.ok) throw Error();
      const body = await r.json();
      current = body.settings;
      openedSettings = structuredClone(current);
      photoSources = body.photo_sources;
      temperatureSensors = body.temperature_sensors || {};
      weatherEntities = body.weather_entities || {};
      lights = body.lights;
      rooms = body.light_rooms || {};
      maxLights = body.max_lights || 9;
      fill(current);
      $("settings-close").focus({ preventScroll: true });
    } catch {
      $("settings-error").textContent = WallboardI18n.t(
        "Inställningarna kunde inte hämtas. Stäng och försök igen.",
      );
    }
  }
  function close() {
    if (themeBusy) {
      themeSave.finally(close);
      return;
    }
    panel.hidden = true;
    appearanceDraft = null;
    if (current) apply(current);
    if (state) window.WallboardPages?.update(state);
    WallboardKeyboard.hide();
    $("open-settings").focus({ preventScroll: true });
  }
  $("open-settings").onclick = open;
  $("settings-close").onclick = close;
  $("settings-cancel").onclick = close;
  $("settings-keyboard").addEventListener("pointerdown", (e) =>
    e.preventDefault(),
  );
  $("settings-keyboard").onclick = () => WallboardKeyboard.show();
  $("settings-test-timer-sound").onclick = async () => {
    const button = $("settings-test-timer-sound"),
      out = $("timer-sound-preview-status");
    button.disabled = true;
    out.textContent = "";
    try {
      const volume = Number(form.elements.timer_volume.value),
        r = await fetch("/api/timer/sound-test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            volume,
            sound: form.elements.timer_sound.value,
            outputs: [
              ...form.querySelectorAll("input[name=timer_outputs]:checked"),
            ].map((i) => i.value),
          }),
        }),
        body = await r.json();
      if (!r.ok)
        throw Error(body.error || WallboardI18n.t("Ljudet kunde inte spelas."));
      out.textContent = volume
        ? WallboardI18n.t("Spelar provljud med ") +
          volume +
          WallboardI18n.t(" % volym.")
        : WallboardI18n.t("Timerljudet är avstängt (0 %).");
    } catch (e) {
      out.textContent = WallboardI18n.t(e.message);
    } finally {
      setTimeout(() => {
        button.disabled = false;
      }, 3300);
    }
  };
  function limitLights() {
    const inputs = [...form.querySelectorAll('input[name="lights"]')],
      count = inputs.filter((i) => i.checked).length;
    for (const i of inputs) i.disabled = !i.checked && count >= maxLights;
    $("settings-light-count").textContent = WallboardI18n.t(
      "{count} av {max} valda",
    )
      .replace("{count}", count)
      .replace("{max}", maxLights);
  }
  form.addEventListener("change", limitLights);
  for (const key of ["language", "time_format", "show_help_text"])
    form.elements[key].addEventListener("change", () => {
      if (!appearanceDraft) return;
      appearanceDraft[key] =
        key === "show_help_text"
          ? form.elements[key].checked
          : form.elements[key].value;
      apply(current);
      WallboardTimeFields.render();
      if (typeof clock === "function") clock();
      if (state) WallboardPages.update(state);
    });
  form.elements.theme.addEventListener("change", () => {
    if (!appearanceDraft || themeBusy) return;
    const selected = form.elements.theme.value,
      previous = current.theme;
    appearanceDraft.theme = selected;
    apply(current);
    if (state) WallboardPages.update(state);
    themeBusy = true;
    form.elements.theme.disabled = true;
    themeSave = (async () => {
      try {
        const response = await fetch("/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ theme: selected }),
        });
        const body = await response.json();
        if (!response.ok)
          throw Error(
            body.error ||
              WallboardI18n.t("Kunde inte spara temat. Försök igen."),
          );
        current = body.settings;
        if (openedSettings) openedSettings.theme = selected;
        if (state) state.settings = current;
      } catch (error) {
        if (appearanceDraft) appearanceDraft.theme = previous;
        form.elements.theme.value = previous;
        apply(current);
        $("settings-error").textContent = WallboardI18n.t(error.message);
      } finally {
        themeBusy = false;
        form.elements.theme.disabled = false;
      }
    })();
  });
  form.addEventListener("input", ranges);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (themeBusy) await themeSave;
    const draft = {};
    for (const k of bools) draft[k] = form.elements[k].checked;
    for (const k of ints) draft[k] = Number(form.elements[k].value);
    for (const k of [
      "screen_mode",
      "start_dashboard",
      "timer_sound",
      "theme",
      "language",
      "time_format",
      "night_start",
      "night_end",
    ])
      draft[k] = form.elements[k].value;
    Object.assign(draft, WallboardWeatherSettings.collect());
    draft.photo_source = form.elements.photo_source.value;
    draft.photo_album = form.elements.photo_album.value;
    draft.timer_outputs = [
      ...form.querySelectorAll("input[name=timer_outputs]:checked"),
    ].map((i) => i.value);
    draft.lights = [
      ...form.querySelectorAll('input[name="lights"]:checked'),
    ].map((i) => i.value);
    // Send only edited fields, so an open form cannot overwrite newer HA changes.
    const equal = (a, b) =>
      JSON.stringify(Array.isArray(a) ? [...a].sort() : a) ===
      JSON.stringify(Array.isArray(b) ? [...b].sort() : b);
    for (const key of Object.keys(draft))
      if (openedSettings && equal(draft[key], openedSettings[key]))
        delete draft[key];
    $("settings-save").disabled = true;
    $("settings-error").textContent = "";
    try {
      const r = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const body = await r.json();
      if (!r.ok)
        throw Error(
          body.error || WallboardI18n.t("Kunde inte spara inställningarna."),
        );
      current = body.settings;
      appearanceDraft = null;
      if (state) state.settings = current;
      apply(current);
      close();
      notice(WallboardI18n.t("Inställningarna är sparade."));
      await poll();
    } catch (e) {
      $("settings-error").textContent = WallboardI18n.t(e.message);
    } finally {
      $("settings-save").disabled = false;
    }
  });
  function apply(p) {
    if (!p) return;
    current = p;
    const appearance = appearanceDraft || p;
    WallboardI18n.configure(appearance);
    WallboardTheme.setPreference(appearance.theme || "auto");
    document.body.classList.toggle("hide-help", !appearance.show_help_text);
    if (typeof clock === "function") clock();
    document.querySelector("#dashboard .weather").hidden = !p.show_weather;
    document.querySelector("#dashboard .home").hidden = !p.show_home;
    document.querySelector("#dashboard .controls").hidden = !p.show_lights;
    $("people").hidden = !p.show_people;
    for (const el of document.querySelectorAll(
      ".temperature:not(.photo-entry):not(.timer-entry)",
    ))
      el.hidden = !p.show_temperatures;
    document.querySelector(".photo-entry").hidden = !p.show_photos;
    const count = (p.show_temperatures ? 2 : 0) + 1 + (p.show_photos ? 1 : 0),
      temps = document.querySelector(".temperatures");
    temps.hidden = !count;
    temps.dataset.count = count;
    $("dashboard").dataset.layout =
      p.show_home && p.show_lights
        ? "both"
        : p.show_home
          ? "home"
          : p.show_lights
            ? "lights"
            : "none";
    for (const b of document.querySelectorAll(".light"))
      b.hidden = !p.lights.includes(b.dataset.entity);
    $("lights").dataset.count = p.lights.length;
    if (!booted && window.WallboardPages) {
      booted = true;
      WallboardPages.setPage(p.start_dashboard);
    }
  }
  function update(s) {
    apply(s.settings);
    WallboardKeyboard.sync(s.keyboard, s.settings);
    if (s.mode !== "active" && WallboardKeyboard.opened)
      WallboardKeyboard.hide();
    if (s.fire?.active && !panel.hidden) {
      appearanceDraft = null;
      panel.hidden = true;
      WallboardI18n.configure(s.settings);
      WallboardTheme.setPreference(s.settings.theme);
      WallboardKeyboard.hide();
    }
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !panel.hidden) close();
  });
  return Object.freeze({
    apply,
    update,
    notice,
    open,
    close,
    get isOpen() {
      return !panel.hidden;
    },
  });
})();
