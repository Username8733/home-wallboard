"use strict";
window.WallboardPhotoSettings = (() => {
  const $ = (id) => document.getElementById(id),
    form = $("settings-form");
  let options = null,
    remember = {};
  function render(preferred) {
    if (!options) return;
    const source = form.elements.photo_source.value,
      albums = options.albums[source] || [],
      select = form.elements.photo_album;
    select.replaceChildren(
      ...albums.map((a) => {
        const o = document.createElement("option");
        o.value = a.id;
        o.textContent = a.name
          .replace(
            / · privat urval$/,
            WallboardI18n.language === "en"
              ? " · private selection"
              : " · privat urval",
          )
          .replace(
            / · privat$/,
            WallboardI18n.language === "en" ? " · private" : " · privat",
          );
        return o;
      }),
    );
    if (!albums.length) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = WallboardI18n.t("Lägg till ett album nedan");
      select.append(o);
    }
    if (albums.some((a) => a.id === preferred)) select.value = preferred;
    $("photo-shared-fields").hidden = !["icloud", "google"].includes(source);
    $("photo-local-fields").hidden = source !== "local";
    $("photo-album-create").hidden = source === "immich";
    $("photo-album-link").hidden = source === "local";
    $("photo-album-link").disabled = !["icloud", "google"].includes(source);
    $("photo-source-help").textContent =
      source === "immich"
        ? WallboardI18n.t("Album som är delade med wallboardens Immich-konto.")
        : source === "local"
          ? WallboardI18n.t(
              "Välj en mapp eller skapa en ny. Lägg till bilder med knappen nedan.",
            )
          : WallboardI18n.t(
              "Anslut ditt privata konto nedan och välj sedan ett album. Du kan även använda en befintlig delningslänk.",
            );
    $("photo-open-icloud-account").hidden = source !== "icloud";
    if (source === "icloud")
      $("photo-source-help").textContent = WallboardI18n.t(
        "Privat iCloud hanteras under Konton. Här väljer du album för bildspelet.",
      );
    if (window.WallboardSettingsNavigation?.selected === "photos")
      window.WallboardPrivatePhotos?.show(
        source === "icloud" ? null : source,
        options.connections,
      );
  }
  function fill(p, catalog) {
    options = catalog || options;
    if (!options) return;
    remember = { [p.photo_source]: p.photo_album };
    form.elements.photo_source.value = p.photo_source;
    render(p.photo_album);
    $("photo-settings-status").textContent = "";
    $("photo-new-name").value = "";
    $("photo-album-link").value = "";
  }
  form.elements.photo_source.onchange = () => {
    render(remember[form.elements.photo_source.value]);
  };
  form.elements.photo_album.onchange = () => {
    remember[form.elements.photo_source.value] =
      form.elements.photo_album.value;
  };
  $("photo-add-album").onclick = async () => {
    const button = $("photo-add-album"),
      source = form.elements.photo_source.value;
    button.disabled = true;
    $("photo-settings-status").textContent = WallboardI18n.t("Läser albumet…");
    try {
      const r = await fetch("/api/photos/albums", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source,
            name: $("photo-new-name").value,
            url: $("photo-album-link").value,
          }),
        }),
        body = await r.json();
      if (!r.ok)
        throw Error(
          body.error || WallboardI18n.t("Albumet kunde inte läggas till."),
        );
      options = body.options;
      remember[source] = body.album.id;
      render(body.album.id);
      $("photo-album-link").value = "";
      $("photo-new-name").value = "";
      $("photo-settings-status").textContent = WallboardI18n.t(
        "Albumet är tillagt. Tryck Spara för att använda det i bildspelet.",
      );
    } catch (e) {
      $("photo-settings-status").textContent = WallboardI18n.t(e.message);
    } finally {
      button.disabled = false;
    }
  };
  $("photo-upload").onclick = () => $("photo-files").click();
  $("photo-files").onchange = async () => {
    const files = $("photo-files").files;
    if (!files.length) return;
    const data = new FormData();
    data.set("album", form.elements.photo_album.value);
    for (const file of files) data.append("photos", file);
    $("photo-upload").disabled = true;
    $("photo-settings-status").textContent = WallboardI18n.t(
      "Lägger till bilder…",
    );
    try {
      const r = await fetch("/api/photos/upload", {
          method: "POST",
          body: data,
        }),
        body = await r.json();
      if (!r.ok)
        throw Error(
          body.error || WallboardI18n.t("Bilderna kunde inte läggas till."),
        );
      $("photo-settings-status").textContent =
        body.count +
        WallboardI18n.t(" bilder tillagda. Tryck Spara om du har bytt album.");
    } catch (e) {
      $("photo-settings-status").textContent = WallboardI18n.t(e.message);
    } finally {
      $("photo-upload").disabled = false;
      $("photo-files").value = "";
    }
  };
  async function reload() {
    const source = form.elements.photo_source.value,
      album = form.elements.photo_album.value;
    const response = await fetch("/api/photos/sources");
    if (!response.ok) return;
    options = await response.json();
    render(album);
  }
  $("photo-open-icloud-account").onclick = () =>
    WallboardSettingsNavigation.open("accounts");
  const activate = () => render(form.elements.photo_album.value);
  return Object.freeze({ fill, reload, activate });
})();
