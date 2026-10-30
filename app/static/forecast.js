"use strict";
window.WallboardForecast = (() => {
  const scene = document.getElementById("weather-scene");
  function update(s) {
    const f = s.forecast?.today;
    if (!f) {
      document.getElementById("forecast-summary").textContent = WallboardI18n.t(
        "Dagens prognos saknas",
      );
      document.getElementById("forecast-range").textContent = "";
      document.getElementById("forecast-rain").textContent = "";
      return;
    }
    const c = f.condition || "cloudy";
    scene.dataset.condition = c;
    document.getElementById("forecast-summary").textContent =
      (WallboardI18n.t(weatherNames[c]) || WallboardI18n.t("Dagens väder")) +
      (s.forecast.location ? " · " + s.forecast.location : "") +
      (s.forecast.stale ? WallboardI18n.t(" · Senast hämtat") : "");
    const degree = (v) => (typeof v === "number" ? Math.round(v) + "°" : "—");
    document.getElementById("forecast-range").textContent =
      "↑ " + degree(f.temperature) + "   ↓ " + degree(f.templow);
    document.getElementById("forecast-rain").textContent = [
      typeof f.precipitation === "number"
        ? f.precipitation.toLocaleString(WallboardI18n.locale()) + " mm"
        : "",
      typeof f.wind_speed === "number"
        ? Math.round(f.wind_speed) + " km/h"
        : "",
    ]
      .filter(Boolean)
      .join(" · ");
  }
  return Object.freeze({ update });
})();
