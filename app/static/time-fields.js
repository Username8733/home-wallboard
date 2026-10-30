"use strict";
window.WallboardTimeFields = (() => {
  const form = document.getElementById("settings-form");
  function option(value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    return node;
  }
  function render() {
    const twelve = form.elements.time_format.value === "12h";
    for (const container of document.querySelectorAll("[data-time-field]")) {
      const hidden = form.elements[container.dataset.timeField];
      const [hour, minute] = hidden.value.split(":").map(Number);
      const hours = document.createElement("select"),
        minutes = document.createElement("select"),
        period = document.createElement("select");
      hours.className = "time-hour";
      minutes.className = "time-minute";
      period.className = "time-period";
      hours.setAttribute("aria-label", WallboardI18n.t("Timme"));
      minutes.setAttribute("aria-label", WallboardI18n.t("Minut"));
      period.setAttribute("aria-label", "AM/PM");
      for (let h = twelve ? 1 : 0; h < (twelve ? 13 : 24); h++)
        hours.append(
          option(h, twelve ? String(h) : String(h).padStart(2, "0")),
        );
      for (let m = 0; m < 60; m++)
        minutes.append(option(m, String(m).padStart(2, "0")));
      period.append(option("AM", "AM"), option("PM", "PM"));
      hours.value = twelve ? hour % 12 || 12 : hour;
      minutes.value = minute;
      period.value = hour < 12 ? "AM" : "PM";
      function change() {
        const h = twelve
          ? (Number(hours.value) % 12) + (period.value === "PM" ? 12 : 0)
          : Number(hours.value);
        hidden.value =
          String(h).padStart(2, "0") +
          ":" +
          String(minutes.value).padStart(2, "0");
        hidden.dispatchEvent(new Event("change", { bubbles: true }));
      }
      for (const select of [hours, minutes, period]) select.onchange = change;
      const colon = document.createElement("span");
      colon.textContent = ":";
      container.replaceChildren(
        hours,
        colon,
        minutes,
        ...(twelve ? [period] : []),
      );
      container.dataset.format = twelve ? "12h" : "24h";
    }
  }
  return Object.freeze({ render });
})();
