"use strict";
window.WallboardWeatherSettings = (() => {
  const form = document.getElementById("settings-form");
  const get = (id) => document.getElementById(id);
  let location = null;
  let cities = [];
  function options(field, values, selected) {
    const list = { ...values };
    if (selected && !list[selected])
      list[selected] = selected + WallboardI18n.t(" · saknas just nu");
    field.replaceChildren(
      ...Object.entries(list).map(([id, name]) => {
        const option = document.createElement("option");
        option.value = id;
        option.textContent = name.replace(
          "Rum saknas i HA",
          WallboardI18n.t("Rum saknas i HA"),
        );
        return option;
      }),
    );
    field.value = selected;
  }
  function visibility() {
    get("weather-city-fields").hidden =
      form.elements.weather_source.value !== "open_meteo";
    get("weather-entity-field").hidden =
      form.elements.weather_source.value !== "ha";
    get("outdoor-sensor-field").hidden =
      form.elements.outdoor_temperature_source.value !== "sensor";
  }
  function fill(settings, sensors, weatherEntities) {
    for (const key of ["weather_source", "outdoor_temperature_source"])
      form.elements[key].value = settings[key];
    for (const key of [
      "indoor_temperature_entity",
      "outdoor_temperature_entity",
    ])
      options(form.elements[key], sensors, settings[key]);
    options(
      form.elements.weather_entity,
      weatherEntities,
      settings.weather_entity,
    );
    location = settings.weather_city
      ? {
          name: settings.weather_city,
          latitude: settings.weather_latitude,
          longitude: settings.weather_longitude,
        }
      : null;
    get("weather-city-query").value = settings.weather_city;
    get("weather-city-status").textContent = location
      ? WallboardI18n.t("Vald plats: ") + location.name
      : WallboardI18n.t("Sök och välj stad för Open-Meteo.");
    get("weather-city-results").replaceChildren();
    visibility();
  }
  get("weather-city-search").onclick = async () => {
    const button = get("weather-city-search");
    button.disabled = true;
    try {
      const response = await fetch(
        "/api/weather/cities?q=" +
          encodeURIComponent(get("weather-city-query").value),
      );
      const data = await response.json();
      if (!response.ok) throw Error(data.error);
      cities = data.cities;
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = WallboardI18n.t("Välj stad…");
      get("weather-city-results").replaceChildren(
        empty,
        ...cities.map((city, i) => {
          const option = document.createElement("option");
          option.value = i;
          option.textContent = city.name;
          return option;
        }),
      );
      get("weather-city-status").textContent = cities.length
        ? WallboardI18n.t("Välj rätt stad i listan.")
        : WallboardI18n.t("Inga städer hittades.");
    } catch (error) {
      get("weather-city-status").textContent = WallboardI18n.t(error.message);
    } finally {
      button.disabled = false;
    }
  };
  get("weather-city-results").onchange = () => {
    const value = get("weather-city-results").value;
    if (value === "") return;
    location = cities[Number(value)];
    get("weather-city-status").textContent =
      WallboardI18n.t("Vald plats: ") +
      location.name +
      WallboardI18n.t(" · tryck Spara");
  };
  form.elements.weather_source.onchange = visibility;
  form.elements.outdoor_temperature_source.onchange = visibility;
  function collect() {
    const data = {};
    for (const key of [
      "weather_source",
      "weather_entity",
      "outdoor_temperature_source",
      "outdoor_temperature_entity",
      "indoor_temperature_entity",
    ])
      data[key] = form.elements[key].value;
    data.weather_city = location?.name || "";
    data.weather_latitude = location?.latitude ?? null;
    data.weather_longitude = location?.longitude ?? null;
    return data;
  }
  return Object.freeze({ fill, collect });
})();
