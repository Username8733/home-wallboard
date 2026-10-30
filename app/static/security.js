"use strict";
window.WallboardSecurity = (() => {
  const $ = (id) => document.getElementById(id),
    grid = $("camera-grid"),
    viewer = $("camera-viewer"),
    stream = $("camera-stream"),
    poster = $("camera-poster"),
    video = $("camera-video");
  let latest = null,
    visible = false,
    timer = null,
    selected = null,
    fallback = null,
    lastFocus = null,
    hls = null,
    videoTimeout = null;
  const cards = new Map();
  function tag(el, text, kind = "") {
    el.textContent = text;
    el.className = kind;
  }
  async function loadPreview(card, entity) {
    card.controller = new AbortController();
    card.image.dataset.loading = "1";
    try {
      const r = await fetch(
        "/api/camera/" + encodeURIComponent(entity) + "/image?v=" + Date.now(),
        { signal: card.controller.signal },
      );
      if (!r.ok || !r.headers.get("Content-Type")?.startsWith("image/"))
        throw Error("Camera image unavailable");
      const blob = await r.blob();
      if (card.controller.signal.aborted) return;
      card.pendingUrl = URL.createObjectURL(blob);
      card.image.src = card.pendingUrl;
    } catch (e) {
      card.image.dataset.loading = "0";
      if (e.name === "AbortError") return;
      card.image.hidden = true;
      card.unavailable.hidden = false;
      card.unavailable.textContent = WallboardI18n.t(
        "Kamerabilden kunde inte hämtas",
      );
    }
  }
  function refreshImages() {
    if (!visible || selected || !latest?.security?.online) return;
    for (const c of latest.security.cameras) {
      const card = cards.get(c.entity_id);
      if (!card || card.image.dataset.loading === "1") continue;
      if (["unavailable", "unknown"].includes(c.state)) continue;
      loadPreview(card, c.entity_id);
    }
  }
  function setVisible(on) {
    if (visible === on) return;
    visible = on;
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    if (on) {
      refreshImages();
      timer = setInterval(refreshImages, 15000);
    } else {
      for (const card of cards.values()) {
        card.controller?.abort();
        card.image.dataset.loading = "0";
      }
      closeCamera();
    }
  }
  function closeCamera() {
    if (fallback) {
      clearTimeout(fallback);
      fallback = null;
    }
    const wasOpen = selected;
    selected = null;
    if (videoTimeout) {
      clearTimeout(videoTimeout);
      videoTimeout = null;
    }
    if (hls) {
      hls.destroy();
      hls = null;
    }
    video.onplaying = null;
    video.onerror = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    video.hidden = true;
    poster.hidden = true;
    poster.removeAttribute("src");
    stream.onload = null;
    stream.onerror = null;
    stream.removeAttribute("src");
    viewer.hidden = true;
    if (wasOpen && lastFocus?.isConnected)
      lastFocus.focus({ preventScroll: true });
  }
  function openCamera(camera) {
    if (!visible || latest?.fire?.active) return;
    closeCamera();
    selected = camera.entity_id;
    lastFocus = cards.get(selected)?.button;
    $("camera-viewer-title").textContent = camera.name;
    stream.alt = WallboardI18n.t("Kamerabild från ") + camera.name;
    viewer.hidden = false;
    $("camera-stream-error").hidden = true;
    stream.hidden = false;
    const preview = cards.get(selected);
    poster.hidden = false;
    poster.src =
      preview?.url || "/api/camera/" + encodeURIComponent(selected) + "/image";
    $("camera-stream-status").textContent = WallboardI18n.t(
      "Direktbild · ansluter video…",
    );
    const id = selected;
    function snapshot() {
      if (selected !== id) return;
      stream.onload = () => {
        if (selected !== id) return;
        stream.hidden = false;
        $("camera-stream-error").hidden = true;
        $("camera-stream-status").textContent = WallboardI18n.t(
          "Bildläge · uppdateras varannan sekund",
        );
        fallback = setTimeout(snapshot, 2000);
      };
      stream.onerror = () => {
        if (selected !== id) return;
        stream.hidden = true;
        $("camera-stream-error").hidden = false;
        $("camera-stream-status").textContent = WallboardI18n.t(
          "Kameran är frånkopplad · försöker igen",
        );
        fallback = setTimeout(snapshot, 5000);
      };
      stream.src =
        "/api/camera/" +
        encodeURIComponent(id) +
        "/image?full=1&v=" +
        Date.now();
    }
    let usingFallback = false;
    function tryMjpeg() {
      if (selected !== id || usingFallback) return;
      usingFallback = true;
      if (videoTimeout) {
        clearTimeout(videoTimeout);
        videoTimeout = null;
      }
      video.onerror = null;
      video.onplaying = null;
      if (hls) {
        hls.destroy();
        hls = null;
      }
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.hidden = true;
      poster.hidden = false;
      stream.hidden = false;
      stream.onload = () => {
        if (selected !== id) return;
        $("camera-stream-status").textContent = WallboardI18n.t(
          "Direktvy · uppdateras varje sekund",
        );
        $("camera-stream-error").hidden = true;
      };
      if (!stream.getAttribute("src")?.endsWith("/stream")) {
        stream.onerror = snapshot;
        stream.src = "/api/camera/" + encodeURIComponent(id) + "/stream";
      }
    }
    stream.hidden = false;
    video.hidden = true;
    video.muted = true;
    video.onerror = tryMjpeg;
    stream.onload = () => {
      if (selected === id) {
        stream.hidden = false;
        $("camera-stream-error").hidden = true;
        $("camera-stream-status").textContent = WallboardI18n.t(
          "Direktvy · ansluter video i bakgrunden…",
        );
      }
    };
    stream.onerror = snapshot;
    stream.src = "/api/camera/" + encodeURIComponent(id) + "/stream";
    video.onplaying = () => {
      if (selected !== id) return;
      if (videoTimeout) {
        clearTimeout(videoTimeout);
        videoTimeout = null;
      }
      video.hidden = false;
      poster.hidden = true;
      stream.hidden = true;
      stream.onload = null;
      stream.onerror = null;
      stream.removeAttribute("src");
      $("camera-stream-status").textContent = WallboardI18n.t("Direktsändning");
      $("camera-stream-error").hidden = true;
    };
    videoTimeout = setTimeout(tryMjpeg, 25000);
    const source =
      "/api/camera/" + encodeURIComponent(id) + "/hls/master_playlist.m3u8";
    if (window.Hls?.isSupported()) {
      hls = new Hls({
        enableWorker: false,
        lowLatencyMode: true,
        maxBufferLength: 3,
        backBufferLength: 0,
        liveSyncDurationCount: 1,
        startFragPrefetch: true,
      });
      hls.on(Hls.Events.MEDIA_ATTACHED, () => hls?.loadSource(source));
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(tryMjpeg);
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) tryMjpeg();
      });
      hls.attachMedia(video);
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = source;
      video.play().catch(tryMjpeg);
    } else tryMjpeg();
    $("camera-close").focus({ preventScroll: true });
    wake();
  }
  function returnToGrid() {
    closeCamera();
    refreshImages();
  }
  $("camera-close").onclick = returnToGrid;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && selected) returnToGrid();
  });
  function makeCamera(c) {
    const b = document.createElement("button");
    b.className = "camera-card";
    b.setAttribute("aria-label", WallboardI18n.t("Öppna kameran ") + c.name);
    const picture = document.createElement("div");
    picture.className = "camera-thumbnail";
    const image = document.createElement("img");
    image.alt = c.name;
    image.hidden = true;
    const unavailable = document.createElement("span");
    unavailable.className = "camera-image-status";
    unavailable.textContent = WallboardI18n.t("Hämtar kamerabild…");
    picture.append(image, unavailable);
    const line = document.createElement("div");
    line.className = "camera-label";
    const name = document.createElement("strong");
    name.textContent = c.name;
    const status = document.createElement("span");
    line.append(name, status);
    b.append(picture, line);
    grid.append(b);
    image.onload = () => {
      image.dataset.loading = "0";
      image.hidden = false;
      unavailable.hidden = true;
      const card = cards.get(c.entity_id);
      if (card?.pendingUrl) {
        if (card.url) URL.revokeObjectURL(card.url);
        card.url = card.pendingUrl;
        card.pendingUrl = null;
      }
    };
    image.onerror = () => {
      image.dataset.loading = "0";
      image.hidden = true;
      unavailable.hidden = false;
      unavailable.textContent = WallboardI18n.t(
        "Kamerabilden kunde inte hämtas",
      );
    };
    b.onclick = () => openCamera(c);
    cards.set(c.entity_id, { button: b, image, status, unavailable });
  }
  function update(s, context) {
    latest = s;
    const sec = s.security;
    if (!sec) return;
    $("security-connection").textContent = sec.online
      ? WallboardI18n.t("Ansluten till HA")
      : WallboardI18n.t("HA frånkopplad");
    $("security-connection").classList.toggle("bad", !sec.online);
    const alarmNames = {
      disarmed: WallboardI18n.t("Avlarmat"),
      armed_away: WallboardI18n.t("Bortalarmat"),
      armed_home: WallboardI18n.t("Hemmalarmat"),
      armed_night: WallboardI18n.t("Nattlarmat"),
      triggered: WallboardI18n.t("Larm utlöst"),
      arming: WallboardI18n.t("Larmar på"),
      pending: WallboardI18n.t("Fördröjt larm"),
    };
    $("security-alarm").textContent =
      alarmNames[sec.alarm] || WallboardI18n.t("Status saknas");
    const open = sec.doors.filter((d) => d.state === "on").length,
      unknown = sec.doors.filter(
        (d) => !["on", "off"].includes(d.state),
      ).length;
    $("security-doors").textContent = open
      ? open +
        WallboardI18n.t(" öppna") +
        (unknown ? " · " + unknown + WallboardI18n.t(" okända") : "")
      : unknown
        ? unknown + WallboardI18n.t(" okända")
        : WallboardI18n.t("Alla stängda");
    const smokeIds = s.smoke_entities || [];
    const clear =
      sec.online &&
      smokeIds.length > 0 &&
      smokeIds.every((id) => s.states[id]?.state === "off");
    $("security-smoke").textContent = s.fire?.active
      ? WallboardI18n.t("Larm utlöst")
      : clear
        ? WallboardI18n.t("Ingen aktiv signal")
        : WallboardI18n.t("Status saknas");
    const items = sec.doors.map((d) => ({
      name: d.name,
      value:
        d.state === "on"
          ? WallboardI18n.t("Öppen")
          : d.state === "off"
            ? WallboardI18n.t("Stängd")
            : WallboardI18n.t("Status saknas"),
      kind: d.state === "on" ? "warn" : d.state === "off" ? "ok" : "unknown",
    }));
    items.push({
      name: WallboardI18n.t("Lås · huvudentré"),
      value:
        sec.lock === "locked"
          ? WallboardI18n.t("Låst")
          : sec.lock === "unlocked"
            ? WallboardI18n.t("Olåst")
            : WallboardI18n.t("Status saknas"),
      kind:
        sec.lock === "locked"
          ? "ok"
          : sec.lock === "unlocked"
            ? "warn"
            : "unknown",
    });
    $("security-contacts").replaceChildren(
      ...items.map((i) => {
        const el = document.createElement("div");
        el.className = "contact-status " + i.kind;
        const name = document.createElement("span");
        name.textContent = i.name;
        const value = document.createElement("strong");
        value.textContent = i.value;
        el.append(name, value);
        return el;
      }),
    );
    for (const c of sec.cameras) {
      if (!cards.has(c.entity_id)) makeCamera(c);
      const card = cards.get(c.entity_id);
      const offline =
        !sec.online || ["unknown", "unavailable"].includes(c.state);
      tag(
        card.status,
        offline
          ? WallboardI18n.t("Frånkopplad")
          : c.motion === "on"
            ? WallboardI18n.t("Rörelse")
            : WallboardI18n.t("Öppna"),
        offline ? "unknown" : c.motion === "on" ? "motion" : "",
      );
      if (offline) {
        card.image.hidden = true;
        card.unavailable.hidden = false;
        card.unavailable.textContent = WallboardI18n.t(
          "Kameran är frånkopplad",
        );
      }
    }
    setVisible(
      context.page === "security" && !context.fireActive && s.mode === "active",
    );
  }
  return Object.freeze({
    update,
    setVisible,
    closeCamera,
    get selected() {
      return selected;
    },
  });
})();
