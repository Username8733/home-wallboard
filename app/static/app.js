"use strict";
const $ = (id) => document.getElementById(id);
let state = null,
  manualPhotos = false,
  manualUntil = 0,
  lastWake = 0,
  photoIndex = -1,
  photoKey = "",
  front = 0,
  photoList = [];
const pending = new Set();
const weatherNames = {
  "clear-night": WallboardI18n.t("Stjärnklar natt"),
  cloudy: WallboardI18n.t("Molnigt"),
  exceptional: WallboardI18n.t("Ovanligt väder"),
  fog: WallboardI18n.t("Dimma"),
  hail: "Hagel",
  lightning: WallboardI18n.t("Åska"),
  "lightning-rainy": WallboardI18n.t("Åska och regn"),
  partlycloudy: WallboardI18n.t("Växlande molnighet"),
  pouring: WallboardI18n.t("Kraftigt regn"),
  rainy: WallboardI18n.t("Regn"),
  snowy: WallboardI18n.t("Snö"),
  "snowy-rainy": WallboardI18n.t("Snöblandat regn"),
  sunny: WallboardI18n.t("Soligt"),
  windy: WallboardI18n.t("Blåsigt"),
  "windy-variant": WallboardI18n.t("Blåsigt och molnigt"),
};
const weatherIcons = {
  sunny: "☀",
  "clear-night": "☾",
  partlycloudy: "☁",
  rainy: "☂",
  pouring: "☂",
  snowy: "❄",
  fog: "≋",
  cloudy: "☁",
};
function text(id, value) {
  $(id).textContent = value;
}
function clock() {
  const d = new Date();
  WallboardTheme.apply(d);
  WallboardI18n.renderClock("clock", d);
  WallboardI18n.renderClock("slide-clock", d);
  const date = d.toLocaleDateString(WallboardI18n.locale(), {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  text("date", date[0].toUpperCase() + date.slice(1));
  text("slide-date", date);
  text(
    "greeting",
    d.getHours() < 10
      ? WallboardI18n.t("God morgon")
      : d.getHours() < 17
        ? WallboardI18n.t("Välkommen hem")
        : WallboardI18n.t("God kväll"),
  );
}
clock();
setInterval(clock, 1000);
async function post(path, body = {}) {
  let r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw Error(r.status);
  return r.json();
}
async function wake() {
  manualPhotos = false;
  manualUntil = 0;
  document.body.classList.remove("sleep");
  if (Date.now() - lastWake < 2000) return;
  lastWake = Date.now();
  try {
    await post("/api/wake");
  } catch {}
}
let nightTapped = 0;
document.addEventListener(
  "pointerdown",
  (event) => {
    if (!["night", "screen_off"].includes(state?.mode)) return;
    nightTapped = Date.now();
    event.preventDefault();
    event.stopImmediatePropagation();
    wake();
  },
  { capture: true },
);
document.addEventListener(
  "click",
  (event) => {
    if (nightTapped && Date.now() - nightTapped < 700) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },
  { capture: true },
);
document.addEventListener("pointerdown", (e) => {
  if (e.target.closest("#photos-button")) return;
  wake();
});
$("photos-button").addEventListener("click", async () => {
  if (state?.fire?.active) return;
  manualPhotos = true;
  manualUntil = Date.now() + 120000;
  document.body.classList.add("sleep");
  if (photoIndex < 0) await nextPhoto();
});
$("return-home").addEventListener("click", wake);
function val(e) {
  return state?.states[e]?.state;
}
function temp(e) {
  const v = val(e);
  return v !== undefined &&
    v !== null &&
    !["unknown", "unavailable", ""].includes(v) &&
    Number.isFinite(Number(v))
    ? Number(v).toLocaleString(WallboardI18n.locale(), {
        maximumFractionDigits: 1,
      }) + "°"
    : "—°";
}
function render() {
  let s = state;
  document.body.classList.toggle(
    "night-screen-off",
    ["night", "screen_off"].includes(s.mode),
  );
  window.WallboardSettings?.update(s);
  const remote = s.remote_view;
  if (
    remote?.sequence &&
    String(remote.sequence) !==
      sessionStorage.getItem("wallboard-remote-sequence")
  ) {
    sessionStorage.setItem(
      "wallboard-remote-sequence",
      String(remote.sequence),
    );
    if (window.WallboardPages) WallboardPages.setPage(remote.page);
  }
  window.WallboardPages?.update(s);
  const active = s.mode === "active";
  if (manualPhotos && Date.now() > manualUntil) manualPhotos = false;
  document.body.classList.toggle(
    "sleep",
    !s.fire?.active && (manualPhotos || s.mode === "slideshow"),
  );
  text(
    "connection",
    s.ha_online ? WallboardI18n.t("Ansluten") : WallboardI18n.t("Frånkopplad"),
  );
  $("connection").classList.toggle("bad", !s.ha_online);
  const w = val(s.settings.weather_entity);
  const degree = (v) =>
    typeof v === "number" && Number.isFinite(v)
      ? v.toLocaleString(WallboardI18n.locale(), { maximumFractionDigits: 1 }) +
        "°"
      : "—°";
  text("outdoor", degree(s.temperatures?.outdoor));
  text(
    "slide-weather",
    degree(s.temperatures?.outdoor) +
      " · " +
      (WallboardI18n.t(weatherNames[s.forecast?.today?.condition || w]) || ""),
  );
  text("kitchen", degree(s.temperatures?.indoor));
  const alarm = val(s.home_entities?.alarm);
  text(
    "home-title",
    !s.ha_online
      ? WallboardI18n.t("Hemmet är frånkopplat")
      : alarm === "disarmed"
        ? WallboardI18n.t("Välkommen hem")
        : alarm === "triggered"
          ? WallboardI18n.t("Larmet har utlösts")
          : alarm?.startsWith("armed")
            ? WallboardI18n.t("Hemmet är larmat")
            : "Hemstatus",
  );
  text(
    "home-detail",
    !s.ha_online
      ? WallboardI18n.t(
          "Visar senast hämtade värden. Återansluter automatiskt.",
        )
      : alarm === "disarmed"
        ? WallboardI18n.t("Larmet är av · Här är läget hemma.")
        : alarm?.startsWith("armed")
          ? WallboardI18n.t(
              "Larmet är på · Överblick utan att ändra larmläget.",
            )
          : WallboardI18n.t("Kontrollera larmläget i Home Assistant."),
  );
  const doorNames = s.home_entities?.doors || {},
    doors = Object.keys(doorNames);
  const open = doors.filter((e) => val(e) === "on");
  text(
    "doors",
    !s.ha_online
      ? WallboardI18n.t("Dörrstatus kan inte uppdateras")
      : open.length
        ? open
            .map((e) => doorNames[e] + WallboardI18n.t(" är öppen"))
            .join(" · ")
        : doors.every((e) => val(e) === "off")
          ? WallboardI18n.t("✓ Entrédörrarna är stängda")
          : WallboardI18n.t("Dörrstatus saknas"),
  );
  $("people").replaceChildren(
    ...s.people.map((name) => {
      let v = val(s.people_entities?.[name]);
      let el = document.createElement("div");
      el.className =
        "person " + (v === "on" ? "here" : v === "off" ? "away" : "unknown");
      let a = document.createElement("div");
      a.className = "avatar";
      a.textContent = name[0].toUpperCase();
      el.append(
        a,
        document.createTextNode(name[0].toUpperCase() + name.slice(1)),
      );
      el.title =
        v === "on"
          ? WallboardI18n.t("Hemma")
          : v === "off"
            ? "Borta"
            : WallboardI18n.t("Status saknas");
      return el;
    }),
  );
  for (const [entity, name] of Object.entries(s.lights)) {
    let b = document.querySelector(`[data-entity="${entity}"]`);
    if (!b) {
      b = document.createElement("button");
      b.dataset.entity = entity;
      b.innerHTML =
        '<span class="bulb"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path></path></svg></span><span><span class="name"></span><small></small></span><span class="light-switch" aria-hidden="true"></span>';
      b.querySelector(".name").textContent = name;
      b.onclick = () => toggle(entity);
      $("lights").append(b);
    }
    window.WallboardLightControls?.bind(b, entity);
    let v = val(entity);
    b.className =
      "light " +
      (v === "on" ? "on " : "") +
      (pending.has(entity) ? "pending" : "");
    b.disabled =
      !s.ha_online || !["on", "off"].includes(v) || pending.has(entity);
    b.setAttribute("aria-pressed", String(v === "on"));
    b.querySelector(".name").textContent = name;
    const room = s.light_rooms?.[entity] || WallboardI18n.t("Rum saknas i HA");
    b.querySelector("small").textContent = room;
    const icon = s.light_icons?.[entity];
    if (icon) {
      b.querySelector("path").setAttribute("d", icon.path);
      b.querySelector("svg").dataset.icon = icon.icon;
    }
    b.title = name + " · " + room;
  }
  text(
    "photo-count",
    s.photos.length +
      WallboardI18n.t(" bilder · ") +
      (WallboardI18n.t(s.photo_library?.source_name) || "Immich"),
  );
  text(
    "health",
    s.ha_online
      ? WallboardI18n.t("Home Assistant · Uppdateras automatiskt")
      : WallboardI18n.t("Home Assistant · Anslutningen saknas"),
  );
  text(
    "camera-status",
    s.camera_ok
      ? WallboardI18n.t("● Lokal närvarodetektering")
      : WallboardI18n.t("● Kamera frånkopplad · Tryck fungerar"),
  );
  const currentPhoto = photoList[photoIndex]?.id;
  photoList = s.photos;
  const key = photoList.map((p) => p.id).join();
  if (key !== photoKey) {
    photoKey = key;
    const found = photoList.findIndex((p) => p.id === currentPhoto);
    if (found >= 0) photoIndex = found;
    else {
      photoIndex = -1;
      nextPhoto();
    }
  }
  text(
    "no-photos",
    WallboardI18n.t(s.photo_library?.error) ||
      WallboardI18n.t(
        "Det valda albumet har inga bilder ännu. Lägg till bilder eller välj ett annat album i inställningarna.",
      ),
  );
  if (!photoList.length) {
    for (const img of document.querySelectorAll(".slide")) {
      img.classList.remove("visible");
      img.removeAttribute("src");
    }
    $("photo-backdrop").style.backgroundImage = "none";
  }
  $("no-photos").style.display = photoList.length ? "none" : "block";
}
async function toggle(entity) {
  if (pending.has(entity)) return;
  pending.add(entity);
  render();
  try {
    await post("/api/light", {
      entity_id: entity,
      action: val(entity) === "on" ? "turn_off" : "turn_on",
    });
    text("feedback", "");
    await new Promise((r) => setTimeout(r, 650));
    await poll();
  } catch {
    text(
      "feedback",
      WallboardI18n.t("Det gick inte att ändra lampan. Försök igen."),
    );
  } finally {
    pending.delete(entity);
    render();
  }
}
async function nextPhoto() {
  if (!photoList.length) return;
  photoIndex = (photoIndex + 1) % photoList.length;
  let p = photoList[photoIndex];
  let src = "/photo/" + encodeURIComponent(p.file);
  let img = new Image();
  img.src = src;
  try {
    await img.decode();
  } catch {
    return;
  }
  front = 1 - front;
  let el = $(front ? "slide-a" : "slide-b");
  el.src = src;
  el.classList.add("visible");
  $(front ? "slide-b" : "slide-a").classList.remove("visible");
  $("photo-backdrop").style.backgroundImage = `url("${src}")`;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(p.date || "")
    ? new Date(p.date + "T12:00:00")
    : null;
  text(
    "caption",
    [
      p.city,
      date?.toLocaleDateString(WallboardI18n.locale(), {
        month: "long",
        year: "numeric",
      }),
    ]
      .filter(Boolean)
      .join(" · "),
  );
}
let slideChanged = Date.now();
setInterval(() => {
  const seconds = state?.settings?.slide_seconds || 20;
  if (
    document.body.classList.contains("sleep") &&
    Date.now() - slideChanged >= seconds * 1000
  ) {
    slideChanged = Date.now();
    nextPhoto();
  }
}, 1000);
async function poll() {
  try {
    const r = await fetch("/api/state");
    if (!r.ok) throw Error(r.status);
    state = await r.json();
    render();
  } catch {
    text("connection", WallboardI18n.t("Återansluter"));
    $("connection").classList.add("bad");
    document.querySelectorAll(".light").forEach((b) => (b.disabled = true));
    text(
      "camera-status",
      WallboardI18n.t("Anslutningen till wallboarden saknas"),
    );
  }
}
poll();
setInterval(poll, 2000);
