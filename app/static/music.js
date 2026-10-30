"use strict";
window.WallboardMusic = (() => {
  const $ = (id) => document.getElementById(id);
  let latest = null,
    loaded = false,
    history = [],
    location = { category: "playlists" },
    generation = 0,
    view = "library",
    queueBusy = false,
    queueUpdated = 0,
    queueFirst = true,
    context = null,
    commandBusy = false,
    outputBusy = false,
    outputKey = "",
    selectedPlayer = null;
  const kinds = {
    artist: "Artist",
    album: "Album",
    track: WallboardI18n.t("Låt"),
    playlist: "Spellista",
    music: WallboardI18n.t("Musik"),
    podcast: "Podcast",
    audiobook: "Ljudbok",
    directory: WallboardI18n.t("Bibliotek"),
    episode: "Avsnitt",
  };
  async function browse(next, back = false) {
    if (!back) history.push(location);
    location = next;
    const ticket = ++generation;
    $("music-library").setAttribute("aria-busy", "true");
    $("music-message").textContent = WallboardI18n.t("Hämtar musik…");
    try {
      const r = await fetch("/api/music/browse?" + new URLSearchParams(next));
      const b = await r.json();
      if (!r.ok) throw Error(b.error);
      if (ticket !== generation) return;
      $("music-library-title").textContent =
        next.category || (!next.id && !next.query)
          ? WallboardI18n.t(b.title)
          : b.title;
      context = b.context?.play ? b.context : null;
      $("music-collection-actions").hidden = view !== "library" || !context;
      for (const button of document.querySelectorAll("[data-music-category]"))
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.musicCategory === next.category),
        );
      $("music-clear-search").hidden = view !== "library" || !next.q;
      $("music-library").replaceChildren(
        ...b.items.map((item) => {
          const row = document.createElement("div");
          row.className = "music-item";
          const info = document.createElement("button");
          info.className = "music-item-info";
          const title = document.createElement("strong");
          title.textContent = item.title;
          const sub = document.createElement("small");
          sub.textContent =
            WallboardI18n.t(kinds[item.kind]) || WallboardI18n.t("Musik");
          info.append(title, sub);
          info.disabled = !item.expand && !item.play;
          info.onclick = () =>
            item.play && ["track", "music", "episode"].includes(item.kind)
              ? command({ action: "item", id: item.id })
              : item.expand
                ? browse({ id: item.id })
                : command({ action: "item", id: item.id });
          row.append(info);
          if (item.play) {
            const play = document.createElement("button");
            play.className = "music-item-play";
            play.textContent = "▶ " + WallboardI18n.t("Spela");
            play.setAttribute(
              "aria-label",
              WallboardI18n.t("Spela ") +
                item.title +
                " · " +
                (latest?.music?.player?.name || WallboardI18n.t("Högtalare")),
            );
            play.onclick = () => command({ action: "item", id: item.id });
            const add = document.createElement("button");
            add.className = "music-item-play";
            add.textContent = "+ " + WallboardI18n.t("Köa");
            add.setAttribute(
              "aria-label",
              WallboardI18n.t("Lägg ") + item.title + WallboardI18n.t(" i kön"),
            );
            add.onclick = () =>
              command({ action: "item", id: item.id, enqueue: "add" });
            row.append(play, add);
          }
          return row;
        }),
      );
      $("music-message").textContent = b.items.length
        ? ""
        : WallboardI18n.t(
            "Inga träffar. Prova en annan sökning eller kategori.",
          );
    } catch (e) {
      if (ticket === generation)
        $("music-message").textContent =
          WallboardI18n.t(e.message) ||
          WallboardI18n.t("Musiken kunde inte hämtas.");
    } finally {
      if (ticket === generation) {
        $("music-library").setAttribute("aria-busy", "false");
        $("music-back").disabled = !history.length;
      }
    }
  }
  function setView(next) {
    view = next;
    const library = next === "library";
    $("music-view-library").setAttribute("aria-pressed", String(library));
    $("music-view-queue").setAttribute("aria-pressed", String(!library));
    for (const el of [
      $("music-search-form"),
      document.querySelector(".music-categories"),
      document.querySelector(".music-library-heading"),
      $("music-message"),
      $("music-library"),
      $("music-collection-actions"),
    ])
      el.hidden = !library;
    $("music-collection-actions").hidden = !library || !context;
    $("music-clear-search").hidden = !library || !location.q;
    $("music-queue").hidden = library;
    if (!library) loadQueue(true);
  }
  async function loadQueue(force = false) {
    if (queueBusy || (!force && Date.now() - queueUpdated < 5000)) return;
    queueBusy = true;
    const requestedPlayer = latest?.music?.player?.entity_id;
    try {
      const r = await fetch("/api/music/queue"),
        b = await r.json();
      if (!r.ok)
        throw Error(b.error || WallboardI18n.t("Musikkön kunde inte hämtas."));
      if (
        latest?.music?.player?.entity_id !== requestedPlayer ||
        (b.player && b.player !== requestedPlayer)
      )
        return;
      $("music-queue-count").textContent = b.total + WallboardI18n.t(" låtar");
      $("music-view-queue").textContent =
        WallboardI18n.t("Musikkö (") + b.total + ")";
      $("music-queue-message").textContent = !b.total
        ? WallboardI18n.t("Kön är tom.")
        : !b.active
          ? WallboardI18n.t("Ingen aktiv Music Assistant-kö på högtalaren.")
          : b.limited
            ? WallboardI18n.t("Visar de första 500 låtarna.")
            : "";
      const list = $("music-queue-items"),
        scroll = list.scrollTop;
      list.replaceChildren(
        ...b.items.map((item) => {
          const row = document.createElement("li");
          row.className = item.current ? "current" : "";
          const number = document.createElement("span");
          number.className = "queue-number";
          number.textContent = item.current ? "▶" : String(item.index + 1);
          const info = document.createElement("div"),
            title = document.createElement("strong"),
            artist = document.createElement("small");
          title.textContent = item.title;
          artist.textContent = item.artist;
          info.append(title, artist);
          const duration = document.createElement("span");
          duration.className = "queue-duration";
          duration.textContent = item.duration
            ? Math.floor(item.duration / 60) +
              ":" +
              String(item.duration % 60).padStart(2, "0")
            : "";
          const button = document.createElement("button");
          button.type = "button";
          button.className = "queue-play";
          button.setAttribute(
            "aria-label",
            WallboardI18n.t("Spela ") + item.title,
          );
          button.append(number, info, duration);
          button.onclick = () => command({ action: "queue_item", id: item.id });
          row.append(button);
          return row;
        }),
      );
      list.scrollTop = scroll;
      if (queueFirst) {
        list.querySelector(".current")?.scrollIntoView({ block: "center" });
        queueFirst = false;
      }
    } catch (e) {
      $("music-queue-message").textContent =
        WallboardI18n.t(e.message) || WallboardI18n.t("Kön kunde inte hämtas.");
    } finally {
      queueBusy = false;
      queueUpdated =
        latest?.music?.player?.entity_id === requestedPlayer ? Date.now() : 0;
    }
  }
  $("music-clear-search").onclick = () => {
    $("music-search").value = "";
    history = [];
    browse({ category: "playlists" }, true);
  };
  $("music-play-collection").onclick = () =>
    context && command({ action: "item", id: context.id });
  $("music-add-collection").onclick = () =>
    context && command({ action: "item", id: context.id, enqueue: "add" });
  $("music-queue-current").onclick = () =>
    $("music-queue-items")
      .querySelector(".current")
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  $("music-view-library").onclick = () => setView("library");
  $("music-view-queue").onclick = () => setView("queue");
  $("music-queue-refresh").onclick = () => loadQueue(true);
  async function command(body) {
    if (latest?.fire?.active || commandBusy || outputBusy) return;
    commandBusy = true;
    $("music-page").classList.add("music-command-busy");
    $("music-control-status").textContent = WallboardI18n.t("Arbetar…");
    try {
      const r = await fetch("/api/music/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, player: selectedPlayer }),
      });
      const b = await r.json();
      if (!r.ok)
        throw Error(
          b.error || WallboardI18n.t("Kunde inte ändra uppspelningen."),
        );
      $("music-control-status").textContent =
        body.action === "item"
          ? body.enqueue === "add"
            ? WallboardI18n.t("Tillagd i kön på ") +
              (latest?.music?.player?.name || "")
            : WallboardI18n.t("Spelar på ") +
              (latest?.music?.player?.name || "")
          : "";
      await poll();
      if (["queue_item", "item"].includes(body.action)) {
        queueUpdated = 0;
        if (view === "queue") loadQueue(true);
      }
    } catch (e) {
      $("music-control-status").textContent =
        WallboardI18n.t(e.message) || WallboardI18n.t("Anslutningen bröts.");
    } finally {
      commandBusy = false;
      $("music-page").classList.remove("music-command-busy");
    }
  }
  function artwork(img, url) {
    if (url) {
      if (img.getAttribute("src") !== url) {
        img.hidden = false;
        img.src = url;
      }
    } else {
      img.hidden = true;
      img.removeAttribute("src");
    }
  }
  for (const id of ["music-art", "slide-music-art"])
    $(id).addEventListener("error", () => {
      $(id).hidden = true;
    });
  $("music-search-form").onsubmit = (e) => {
    e.preventDefault();
    const q = $("music-search").value.trim();
    if (q.length < 2) {
      $("music-message").textContent = WallboardI18n.t(
        "Skriv minst två tecken.",
      );
      return;
    }
    WallboardKeyboard.hide();
    $("music-search").blur();
    browse({ q });
  };
  for (const b of document.querySelectorAll("[data-music-category]"))
    b.onclick = () => {
      WallboardKeyboard.hide();
      browse({ category: b.dataset.musicCategory });
    };
  $("music-back").onclick = () => {
    const previous = history.pop();
    if (previous) browse(previous, true);
  };
  $("music-retry").onclick = () => browse(location, true);
  for (const action of ["previous", "next"])
    $("music-" + action).onclick = () => command({ action });
  $("music-play").onclick = () =>
    command({
      action: latest?.music?.player.state === "playing" ? "pause" : "play",
    });
  $("music-volume").oninput = () => {
    $("music-volume-label").textContent = $("music-volume").value + " %";
  };
  $("music-volume").onchange = () =>
    command({ action: "volume", value: Number($("music-volume").value) / 100 });
  $("music-shuffle").onclick = () =>
    command({ action: "shuffle", value: !latest?.music?.player.shuffle });
  $("music-repeat").onclick = () =>
    command({
      action: "repeat",
      value: latest?.music?.player.repeat === "off" ? "all" : "off",
    });
  $("music-output-name").onchange = async () => {
    if (outputBusy || commandBusy || latest?.fire?.active) return;
    outputBusy = true;
    $("music-output-name").disabled = true;
    $("music-control-status").textContent = WallboardI18n.t("Arbetar…");
    try {
      const response = await fetch("/api/music/output", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player: $("music-output-name").value }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          result.error || WallboardI18n.t("Kunde inte välja högtalare."),
        );
      await poll();
      $("music-control-status").textContent =
        WallboardI18n.t("Vald högtalare") +
        ": " +
        (latest?.music?.player?.name || "");
    } catch (error) {
      $("music-control-status").textContent = WallboardI18n.t(error.message);
    } finally {
      outputBusy = false;
      if (latest) update(latest);
    }
  };
  function update(s) {
    latest = s;
    if (
      view === "queue" &&
      !s.fire?.active &&
      window.WallboardPages?.page === "music"
    )
      loadQueue();
    const p = s.music?.player;
    if (!p) return;
    const playing = s.music?.playing;
    const output = $("music-output-name"),
      outputs = s.music.outputs || [
        { id: p.entity_id, name: p.name || "Relax", online: p.online },
      ];
    const key = JSON.stringify([outputs, WallboardI18n.language]);
    if (key !== outputKey) {
      outputKey = key;
      output.replaceChildren(
        ...outputs.map((speaker) => {
          const option = document.createElement("option");
          option.value = speaker.id;
          option.textContent =
            speaker.name +
            (speaker.group ? " · " + WallboardI18n.t("Grupp") : "") +
            (!speaker.online ? " · " + WallboardI18n.t("Frånkopplad") : "");
          option.disabled = !speaker.online;
          return option;
        }),
      );
    }
    if (!outputBusy) output.value = p.entity_id;
    output.disabled = outputBusy || commandBusy || s.fire?.active;
    if (selectedPlayer !== p.entity_id) {
      selectedPlayer = p.entity_id;
      queueUpdated = 0;
      queueFirst = true;
      $("music-queue-items").replaceChildren();
      $("music-queue-count").textContent = "";
      $("music-view-queue").textContent = WallboardI18n.t("Musikkö");
      $("music-queue-message").textContent = WallboardI18n.t("Hämtar musik…");
    }
    $("music-title").textContent =
      p.title || WallboardI18n.t("Välj något att lyssna på");
    $("music-artist").textContent =
      p.artist || WallboardI18n.t("Ditt bibliotek i Music Assistant");
    $("music-album").textContent = p.album || "";
    artwork($("music-art"), p.art);
    $("music-player-status").textContent = !p.online
      ? WallboardI18n.t("Spelaren är frånkopplad")
      : p.state === "playing"
        ? WallboardI18n.t("Spelar på ") + p.name
        : p.state === "paused"
          ? WallboardI18n.t("Pausat") + " · " + p.name
          : p.name;
    $("music-play").textContent = p.state === "playing" ? "Ⅱ" : "▶";
    $("music-play").setAttribute(
      "aria-label",
      p.state === "playing"
        ? WallboardI18n.t("Pausa")
        : WallboardI18n.t("Spela"),
    );
    for (const id of [
      "music-play",
      "music-next",
      "music-previous",
      "music-volume",
      "music-shuffle",
      "music-repeat",
    ])
      $(id).disabled = !p.online || s.fire?.active;
    if (document.activeElement !== $("music-volume")) {
      $("music-volume").value = Math.round((p.volume || 0) * 100);
      $("music-volume-label").textContent =
        Math.round((p.volume || 0) * 100) + " %";
    }
    $("music-shuffle").setAttribute("aria-pressed", String(p.shuffle));
    $("music-repeat").setAttribute("aria-pressed", String(p.repeat !== "off"));
    const visible = !!playing && !s.fire?.active;
    $("slide-music").hidden = !visible;
    $("slideshow").classList.toggle("has-music", visible);
    if (visible) {
      $("slide-music-title").textContent = playing.title;
      $("slide-music-artist").textContent = playing.artist;
      $("slide-music-player").textContent = playing.name;
      $("slide-music-album").textContent = playing.album || "";
      artwork($("slide-music-art"), playing.art);
    }
  }
  function show() {
    if (!loaded) {
      loaded = true;
      history = [];
      browse({ category: "playlists" }, true);
      if (latest?.music?.player.state === "playing") setView("queue");
    } else if (view === "queue") loadQueue(true);
  }
  return Object.freeze({ update, show, browse });
})();
