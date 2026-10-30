"use strict";
window.WallboardPrivatePhotos = (() => {
  const get = (id) => document.getElementById(id);
  const form = get("settings-form");
  let timer = null;
  let source = null;
  let lastState = "";
  const labels = {
    disconnected: WallboardI18n.t("Inte ansluten"),
    connected: WallboardI18n.t("Ansluten"),
    busy: WallboardI18n.t("Arbetar…"),
    two_factor: WallboardI18n.t("Bekräfta tvåfaktorskod"),
    picking: WallboardI18n.t("Välj privata bilder"),
    error: WallboardI18n.t("Anslutningen behöver kontrolleras"),
  };
  const statusOutput = () =>
    get(
      source === "icloud"
        ? "icloud-account-photo-status"
        : "private-photo-status",
    );
  function render(status) {
    if (!source) return;
    const state = status[source] || {};
    statusOutput().textContent = WallboardI18n.t(
      state.message || labels[state.state] || "",
    );
    get("icloud-two-factor").hidden =
      source !== "icloud" || state.state !== "two_factor";
    for (const button of get(
      source === "icloud" ? "icloud-private-fields" : "private-photo-fields",
    ).querySelectorAll("button"))
      button.disabled = state.state === "busy";
    get("google-configured").textContent = status.google_configured
      ? WallboardI18n.t("OAuth-klientfil är sparad.")
      : WallboardI18n.t(
          "Lägg till en OAuth-klientfil för typen Desktop app. Aktivera Google Photos Picker API i Google Cloud och lägg till kontot som testanvändare om appen är i testläge.",
        );
    if (state.state === "connected" && lastState && lastState !== "connected") {
      window.WallboardPhotoSettings.reload();
      if (source === "icloud") window.WallboardAccounts?.load();
    }
    lastState = state.state;
  }
  async function poll() {
    if (get("settings-panel").hidden || !source) {
      stop();
      return;
    }
    try {
      const response = await fetch("/api/photos/private/status");
      if (response.ok) render(await response.json());
    } catch {
      /* Retry while the settings panel is open. */
    }
  }
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  function show(value, status) {
    source = ["icloud", "google"].includes(value) ? value : null;
    lastState = "";
    get("private-photo-fields").hidden = source !== "google";
    get("icloud-private-fields").hidden = source !== "icloud";
    get("google-private-fields").hidden = source !== "google";
    stop();
    if (source) {
      if (status) render(status);
      poll();
      timer = setInterval(poll, 3000);
    }
  }
  async function action(provider, verb, body = {}) {
    const response = await fetch(
      "/api/photos/private/" + provider + "/" + verb,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const data = await response.json();
    if (!response.ok)
      throw Error(
        data.error || WallboardI18n.t("Anslutningen kunde inte slutföras."),
      );
    if (data.connections) render(data.connections);
    return data;
  }
  function button(id, provider, verb, body = () => ({}), opensWindow = false) {
    get(id).onclick = async () => {
      // Open synchronously so browsers do not block the OAuth/Picker window.
      const popup = opensWindow ? window.open("about:blank", "_blank") : null;
      try {
        const data = await action(provider, verb, body());
        if (data.url) {
          if (popup) {
            popup.opener = null;
            popup.location.replace(data.url);
          } else
            throw Error(
              WallboardI18n.t(
                "Tillåt att wallboarden öppnar en inloggningsflik och försök igen.",
              ),
            );
        }
        if (verb === "disconnect" || verb === "refresh") {
          await WallboardPhotoSettings.reload();
          if (provider === "icloud") await WallboardAccounts.load();
        }
      } catch (error) {
        if (popup) popup.close();
        statusOutput().textContent = WallboardI18n.t(error.message);
      } finally {
        if (provider === "icloud") {
          get("icloud-password").value = "";
          get("icloud-code").value = "";
        }
      }
    };
  }
  button("icloud-login", "icloud", "login", () => ({
    username: get("icloud-username").value,
    password: get("icloud-password").value,
  }));
  button("icloud-verify", "icloud", "verify", () => ({
    code: get("icloud-code").value,
  }));
  button("icloud-refresh", "icloud", "refresh");
  button("icloud-disconnect", "icloud", "disconnect");
  button("google-login", "google", "login", () => ({}), true);
  button(
    "google-pick",
    "google",
    "pick",
    () => ({ name: get("google-selection-name").value }),
    true,
  );
  button("google-import", "google", "import");
  button("google-cancel", "google", "cancel");
  button("google-disconnect", "google", "disconnect");
  get("google-client-file").onchange = async () => {
    const file = get("google-client-file").files[0];
    if (!file) return;
    try {
      if (file.size > 32768)
        throw Error(WallboardI18n.t("Klientfilen är för stor."));
      await action("google", "configure", JSON.parse(await file.text()));
    } catch (error) {
      statusOutput().textContent = WallboardI18n.t(error.message);
    } finally {
      get("google-client-file").value = "";
    }
  };
  return Object.freeze({ show, stop });
})();
