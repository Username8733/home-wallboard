"use strict";
window.WallboardAccounts = (() => {
  const get = (id) => document.getElementById(id);
  let snapshot = null,
    busy = false;
  function render(body) {
    snapshot = body;
    const calendar = body.calendar;
    if (!get("icloud-username").value && body.apple_id)
      get("icloud-username").value = body.apple_id;
    get("icloud-account-identity").textContent =
      body.apple_id || WallboardI18n.t("Inget Apple-konto anslutet");
    get("icloud-account-warning").hidden = !body.account_mismatch;
    get("icloud-account-warning").textContent = WallboardI18n.t(
      "Kalender och bilder använder olika Apple-konton. Ange samma Apple-konto när du ansluter respektive tjänst.",
    );
    get("icloud-calendar-status").textContent = !calendar.available
      ? WallboardI18n.t(calendar.error)
      : calendar.configured
        ? WallboardI18n.t("Ansluten") + " · " + calendar.apple_id
        : WallboardI18n.t("Inte ansluten");
    get("icloud-account-calendar").replaceChildren(
      ...calendar.calendars.map((c) => {
        const option = document.createElement("option");
        option.value = c.id;
        option.textContent = c.name;
        return option;
      }),
    );
    if (calendar.selected.length)
      get("icloud-account-calendar").value = calendar.selected[0];
    get("icloud-calendar-connect").disabled =
      busy || !calendar.available || !calendar.ready;
    for (const key of ["refresh", "disconnect"])
      get("icloud-calendar-" + key).disabled =
        busy || !calendar.available || !calendar.configured;
    get("icloud-calendar-select").disabled = busy || !calendar.calendars.length;
  }
  async function load() {
    try {
      const response = await fetch("/api/accounts/icloud");
      if (!response.ok)
        throw Error(WallboardI18n.t("Kontoanslutningen kunde inte hämtas."));
      render(await response.json());
    } catch (error) {
      get("icloud-calendar-result").textContent = WallboardI18n.t(
        error.message,
      );
    }
  }
  async function open() {
    get("icloud-calendar-result").textContent = "";
    WallboardPrivatePhotos.show("icloud");
    await load();
  }
  async function action(verb) {
    if (busy) return;
    if (
      verb === "disconnect" &&
      !confirm(
        WallboardI18n.t(
          "Koppla bort iCloud-kalendern även för Family Planner i HA? Kalendern hos Apple raderas inte.",
        ),
      )
    )
      return;
    const body = { action: verb };
    if (verb === "connect") {
      body.username = get("icloud-username").value;
      body.password = get("icloud-calendar-password").value;
    }
    if (verb === "select") body.calendar = get("icloud-account-calendar").value;
    busy = true;
    if (snapshot) render(snapshot);
    get("icloud-calendar-result").textContent = WallboardI18n.t("Arbetar…");
    try {
      const response = await fetch("/api/accounts/icloud/calendar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok)
        throw Error(
          data.error || WallboardI18n.t("Kalenderanslutningen kunde inte nås."),
        );
      render(data);
      get("icloud-calendar-result").textContent = WallboardI18n.t(
        "Kalenderinställningen är uppdaterad.",
      );
      const frame = get("planner-frame");
      if (frame.contentWindow?.refreshOnline)
        frame.contentWindow.refreshOnline(true);
    } catch (error) {
      get("icloud-calendar-result").textContent = WallboardI18n.t(
        error.message,
      );
    } finally {
      busy = false;
      get("icloud-calendar-password").value = "";
      if (snapshot) render(snapshot);
    }
  }
  for (const verb of ["connect", "refresh", "select", "disconnect"])
    get("icloud-calendar-" + verb).onclick = () => action(verb);
  window.addEventListener("wallboard-locale-change", () => {
    if (snapshot) render(snapshot);
  });
  return Object.freeze({ open, load });
})();
