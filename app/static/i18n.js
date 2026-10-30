"use strict";
window.WallboardI18n = (() => {
  const messages = window.WallboardMessages;
  const reverse = new Map(
    Object.entries(messages)
      .filter(([a, b]) => a !== b)
      .map(([a, b]) => [b, a]),
  );
  let language = "sv",
    timeFormat = "24h";
  try {
    const saved = JSON.parse(localStorage.getItem("wallboard-locale") || "{}");
    if (["sv", "en"].includes(saved.language)) language = saved.language;
    if (["12h", "24h"].includes(saved.timeFormat))
      timeFormat = saved.timeFormat;
  } catch {
    /* Optional startup preferences. */
  }
  const locale = () => (language === "en" ? "en-GB" : "sv-SE");
  function t(value) {
    if (typeof value !== "string") return value;
    if (language === "sv") return reverse.get(value) || value;
    if (messages[value]) return messages[value];
    return value
      .replace(/Rum saknas i HA/g, "No room assigned in HA")
      .replace(/^(\d+) av (\d+) valda$/, "$1 of $2 selected")
      .replace(/^Hämtar privata bilder: (\d+)$/, "Importing private photos: $1")
      .replace(
        /^(\d+) privata bilder hämtade\. Välj albumet och tryck Spara\.$/,
        "$1 private photos imported. Select the album and press Save.",
      )
      .replace(/ · privat urval$/, " · private selection")
      .replace(/ · privat$/, " · private");
  }
  function staticText(root = document) {
    if (root.documentElement) root.documentElement.lang = language;
    for (const node of root.querySelectorAll("[data-i18n]"))
      node.textContent = t(node.dataset.i18n);
    for (const attr of ["aria-label", "placeholder", "title"])
      for (const node of root.querySelectorAll("[data-i18n-" + attr + "]"))
        node.setAttribute(attr, t(node.getAttribute("data-i18n-" + attr)));
  }
  function configure(prefs) {
    const nextLanguage = ["sv", "en"].includes(prefs.language)
      ? prefs.language
      : "sv";
    const nextFormat = prefs.time_format === "12h" ? "12h" : "24h";
    const changed = language !== nextLanguage || timeFormat !== nextFormat;
    language = nextLanguage;
    timeFormat = nextFormat;
    document.documentElement.lang = language;
    if (changed) {
      try {
        localStorage.setItem(
          "wallboard-locale",
          JSON.stringify({ language, timeFormat }),
        );
      } catch {
        /* Server remains authoritative. */
      }
      staticText();
      window.dispatchEvent(new Event("wallboard-locale-change"));
    }
  }
  function formatTime(value) {
    const [h, m] = String(value || "")
      .split(":")
      .map(Number);
    if (
      !Number.isInteger(h) ||
      h < 0 ||
      h > 23 ||
      !Number.isInteger(m) ||
      m < 0 ||
      m > 59
    )
      return "";
    return timeFormat === "12h"
      ? (h % 12 || 12) +
          ":" +
          String(m).padStart(2, "0") +
          " " +
          (h < 12 ? "AM" : "PM")
      : String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
  }
  function clockParts(date) {
    return new Intl.DateTimeFormat(timeFormat === "12h" ? "en-US" : locale(), {
      timeZone: "Europe/Stockholm",
      hour: timeFormat === "12h" ? "numeric" : "2-digit",
      minute: "2-digit",
      hourCycle: timeFormat === "12h" ? "h12" : "h23",
    }).formatToParts(date);
  }
  function renderClock(id, date) {
    const element = document.getElementById(id);
    if (!element) return;
    const parts = clockParts(date);
    element.replaceChildren(
      ...parts.map((part) => {
        if (part.type === "dayPeriod") {
          const span = document.createElement("span");
          span.className = "clock-period";
          span.textContent = part.value.toUpperCase();
          return span;
        }
        return document.createTextNode(part.value);
      }),
    );
    element.setAttribute("aria-label", parts.map((p) => p.value).join(""));
  }
  document.addEventListener("DOMContentLoaded", () => staticText());
  return Object.freeze({
    t,
    configure,
    staticText,
    locale,
    formatTime,
    renderClock,
    get language() {
      return language;
    },
    get timeFormat() {
      return timeFormat;
    },
  });
})();
