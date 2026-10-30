"use strict";
window.WallboardSettingsNavigation = (() => {
  const get = (id) => document.getElementById(id);
  const sections = [...document.querySelectorAll("[data-settings-category]")];
  const scroll = document.querySelector(".settings-scroll");
  const categories = {
    home: {
      title: WallboardI18n.t("Huvuddashboard"),
      detail: WallboardI18n.t("Innehåll och startvy"),
      icon: "⌂",
      color: "blue",
    },
    lights: {
      title: WallboardI18n.t("Belysning"),
      detail: WallboardI18n.t("Välj lampor och lampgrupper"),
      icon: "☀",
      color: "orange",
    },
    weather: {
      title: WallboardI18n.t("Temperatur och väder"),
      detail: WallboardI18n.t("Givare, vädertjänst och stad"),
      icon: "☁",
      color: "blue",
    },
    photos: {
      title: WallboardI18n.t("Bilder och album"),
      detail: WallboardI18n.t("Bildkälla och privata konton"),
      icon: "▧",
      color: "purple",
    },
    accounts: {
      title: WallboardI18n.t("Konton"),
      detail: WallboardI18n.t("iCloud för kalender och bilder"),
      icon: "◉",
      color: "gray",
    },
    regional: {
      title: WallboardI18n.t("Språk och tid"),
      detail: WallboardI18n.t("Tidsformat och språk"),
      icon: "◷",
      color: "blue",
    },
    appearance: {
      title: WallboardI18n.t("Utseende"),
      detail: WallboardI18n.t("Automatiskt eller fast tema"),
      icon: "◐",
      color: "purple",
    },
    night: {
      title: WallboardI18n.t("Nattläge"),
      detail: WallboardI18n.t("Schemalagd släckning av skärmen"),
      icon: "☾",
      color: "indigo",
    },
    screen: {
      title: WallboardI18n.t("Skärm och bildspel"),
      detail: WallboardI18n.t("Ljusstyrka, närvaro och viloläge"),
      icon: "▣",
      color: "green",
    },
    sound: {
      title: WallboardI18n.t("Timerljud"),
      detail: WallboardI18n.t("Ljudsignal, volym och högtalare"),
      icon: "♫",
      color: "red",
    },
    keyboard: {
      title: WallboardI18n.t("Tangentbord"),
      detail: WallboardI18n.t("Automatiskt skärmtangentbord"),
      icon: "⌨",
      color: "gray",
    },
  };
  let selected = null;
  function open(id, focus = true) {
    if (!categories[id]) return;
    selected = id;
    if (id === "accounts") WallboardAccounts.open();
    else if (id === "photos") WallboardPhotoSettings.activate();
    else window.WallboardPrivatePhotos?.stop();
    get("settings-light-count").hidden = id !== "lights";
    get("settings-category-menu").hidden = true;
    for (const section of sections)
      section.hidden = section.dataset.settingsCategory !== id;
    get("settings-title").textContent = WallboardI18n.t(categories[id].title);
    get("settings-back").hidden = false;
    scroll.scrollTop = 0;
    if (focus) get("settings-back").focus({ preventScroll: true });
  }
  function home(focus = false) {
    const previous = selected;
    selected = null;
    window.WallboardPrivatePhotos?.stop();
    get("settings-light-count").hidden = true;
    for (const section of sections) section.hidden = true;
    get("settings-category-menu").hidden = false;
    get("settings-title").textContent = WallboardI18n.t("Inställningar");
    get("settings-back").hidden = true;
    scroll.scrollTop = 0;
    if (focus)
      document
        .querySelector(`[data-open-category="${previous}"]`)
        ?.focus({ preventScroll: true });
  }
  get("settings-category-list").replaceChildren(
    ...Object.entries(categories).map(([id, category]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "settings-category-row";
      button.dataset.openCategory = id;
      const icon = document.createElement("span");
      icon.className = "settings-category-icon " + category.color;
      icon.textContent = category.icon;
      icon.setAttribute("aria-hidden", "true");
      const text = document.createElement("span");
      text.className = "settings-category-text";
      const title = document.createElement("strong");
      title.textContent = WallboardI18n.t(category.title);
      const detail = document.createElement("small");
      detail.textContent = WallboardI18n.t(category.detail);
      text.append(title, detail);
      const chevron = document.createElement("span");
      chevron.className = "settings-category-chevron";
      chevron.textContent = "›";
      chevron.setAttribute("aria-hidden", "true");
      button.append(icon, text, chevron);
      button.onclick = () => open(id);
      return button;
    }),
  );
  get("settings-back").onclick = () => {
    WallboardKeyboard.hide();
    home(true);
  };
  get("settings-form").addEventListener(
    "invalid",
    (event) => {
      const section = event.target.closest("[data-settings-category]");
      if (section) open(section.dataset.settingsCategory, false);
    },
    true,
  );
  window.addEventListener("wallboard-locale-change", () => {
    for (const [id, category] of Object.entries(categories)) {
      const button = document.querySelector(`[data-open-category="${id}"]`);
      button.querySelector("strong").textContent = WallboardI18n.t(
        category.title,
      );
      button.querySelector("small").textContent = WallboardI18n.t(
        category.detail,
      );
    }
    get("settings-title").textContent = WallboardI18n.t(
      selected ? categories[selected].title : WallboardI18n.t("Inställningar"),
    );
  });
  home();
  return Object.freeze({
    open,
    home,
    get selected() {
      return selected;
    },
  });
})();
