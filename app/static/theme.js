"use strict";
// Explicit Swedish time zone also follows daylight-saving changes automatically.
window.WallboardTheme = (() => {
  const hourFormat = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Stockholm",
    hour: "numeric",
    hourCycle: "h23",
  });
  const labels = {
    morning: WallboardI18n.t("Morgon"),
    day: WallboardI18n.t("Dag"),
    evening: WallboardI18n.t("Kväll"),
    night: WallboardI18n.t("Natt"),
  };
  let preference = "auto";
  try {
    preference = localStorage.getItem("wallboard-theme") || "auto";
  } catch {
    /* Optional startup cache. */
  }
  const choices = ["auto", "morning", "day", "evening", "night", "dark"];
  if (!choices.includes(preference)) preference = "auto";
  labels.dark = "Dark mode";
  function setPreference(value) {
    if (!choices.includes(value)) value = "auto";
    if (preference !== value) {
      preference = value;
      try {
        localStorage.setItem("wallboard-theme", value);
      } catch {
        /* Server preferences remain authoritative. */
      }
    }
    return apply();
  }
  function forHour(hour) {
    if (!Number.isInteger(hour) || hour < 0 || hour > 23)
      throw new RangeError("Hour must be 0–23");
    return hour < 6 || hour >= 22
      ? "night"
      : hour < 10
        ? "morning"
        : hour < 17
          ? "day"
          : "evening";
  }
  function apply(date = new Date()) {
    const theme =
      preference === "auto"
        ? forHour(Number(hourFormat.format(date)))
        : preference;
    if (document.documentElement.dataset.theme !== theme) {
      document.documentElement.dataset.theme = theme;
      document.documentElement.style.colorScheme = ["morning", "day"].includes(
        theme,
      )
        ? "light"
        : "dark";
    }
    const label = document.getElementById("theme-label");
    if (label)
      label.textContent =
        WallboardI18n.t(labels[theme]) +
        (preference === "auto"
          ? WallboardI18n.t(" · Automatiskt")
          : WallboardI18n.t(" · Fast tema"));
    return theme;
  }
  apply();
  return Object.freeze({ forHour, apply, setPreference });
})();
