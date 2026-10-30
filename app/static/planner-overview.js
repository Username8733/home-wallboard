"use strict";
window.WallboardPlannerOverview = (() => {
  const $ = (id) => document.getElementById(id);
  let selected = null,
    lastFocus = null;
  function close() {
    if ($("event-overview").hidden) return;
    $("event-overview").hidden = true;
    selected = null;
    if (lastFocus?.isConnected) lastFocus.focus({ preventScroll: true });
  }
  function dateLabel(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || ""))
      return WallboardI18n.t("Datum saknas");
    return new Date(value + "T12:00:00").toLocaleDateString(
      WallboardI18n.locale(),
      {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      },
    );
  }
  function show(frame, original, event, date, person, context = {}) {
    if (state?.fire?.active) return;
    WallboardKeyboard.hide();
    lastFocus =
      context.focus ||
      frame?.contentDocument.activeElement ||
      document.activeElement;
    selected = { frame, original, event, date, person };
    const w = frame?.contentWindow,
      record = event.onlineRecord || {},
      snapshot = context.snapshot || w.plannerSnapshot(),
      ids = context.ids || w.participants(event),
      endDate = record.editEndDate || event.endDate || event.date,
      endTime = record.editEndTime ?? event.end ?? "";
    $("event-title").textContent =
      event.title || record.summary || WallboardI18n.t("Händelse");
    $("event-date").textContent =
      dateLabel(event.date) +
      (endDate && endDate !== event.date ? " – " + dateLabel(endDate) : "");
    $("event-times").textContent = event.time
      ? WallboardI18n.formatTime(event.time) +
        (endTime ? " – " + WallboardI18n.formatTime(endTime) : "")
      : endTime
        ? WallboardI18n.t("Till ") + WallboardI18n.formatTime(endTime)
        : WallboardI18n.t("Hela dagen");
    $("event-participants").replaceChildren(
      ...ids.map((id) => {
        const p = snapshot.people.find((p) => p.id === id),
          el = document.createElement("span");
        el.textContent = p?.name || id;
        return el;
      }),
    );
    $("event-location").textContent =
      event.location ||
      record.location ||
      WallboardI18n.t("Ingen plats angiven");
    $("event-notes").textContent =
      event.description ||
      record.description ||
      WallboardI18n.t("Inga anteckningar.");
    $("event-source-label").textContent = event.online
      ? record.calendarName || record.sourceName || "Onlinekalender"
      : WallboardI18n.t("Familjens kalender");
    const writable = !event.online || event.writable;
    $("event-edit").disabled = !writable;
    $("event-edit-help").textContent = writable
      ? WallboardI18n.t("Ändra uppgifterna via knappen Ändra.")
      : WallboardI18n.t(
          "Händelsen är skrivskyddad eller kalendern kan inte nås just nu.",
        );
    $("event-overview").hidden = false;
    $("event-title").focus({ preventScroll: true });
    wake();
  }
  function install(frame) {
    const w = frame?.contentWindow,
      d = frame.contentDocument;
    if (w.__wallboardEventOverviewInstalled) return true;
    if (
      typeof w.openEvent !== "function" ||
      typeof w.plannerSnapshot !== "function"
    )
      return false;
    const original = w.editEvent || w.openEvent;
    w.openEvent = (event, date, person) =>
      show(frame, original, event, date, person);
    if (typeof w.renderDay === "function") {
      const render = w.renderDay;
      w.renderDay = function () {
        render.call(w);
        const s = d.getElementById("day-summary");
        if (s)
          s.textContent = s.textContent.replace(
            w.msg(" · Select an event to edit"),
            WallboardI18n.t(" · Tryck på en aktivitet för detaljer"),
          );
        for (const b of d.querySelectorAll(".day-event"))
          b.setAttribute(
            "aria-label",
            (b.title || "Aktivitet") + WallboardI18n.t(". Visa detaljer."),
          );
      };
    }
    const head = d.querySelector("#editor .dialog-head");
    if (head) {
      const b = d.createElement("button");
      b.type = "button";
      b.className = "wb-keyboard-trigger";
      b.textContent = WallboardI18n.t("Tangentbord");
      b.addEventListener("pointerdown", (e) => e.preventDefault());
      b.onclick = () => WallboardKeyboard.show();
      head.insertBefore(b, d.getElementById("close"));
    }
    WallboardKeyboard.attach(d);
    w.__wallboardEventOverviewInstalled = true;
    return true;
  }
  $("event-close").onclick = close;
  $("event-back").onclick = close;
  $("event-edit").onclick = () => {
    const item = selected;
    if (!item || state?.fire?.active) return;
    close();
    if (!item.frame) {
      item.original(item.event);
      return;
    }
    item.original.call(
      item.frame.contentWindow,
      item.event,
      item.date,
      item.person,
    );
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("event-overview").hidden) {
      e.preventDefault();
      close();
    }
  });
  return Object.freeze({
    install,
    showHome(event, snapshot, focus) {
      const ids = (event.people || []).filter((id) =>
        snapshot.people.some((p) => p.id === id),
      );
      show(
        null,
        (item) => window.WallboardHomeAgenda.edit(item),
        event,
        event.date,
        ids[0],
        { snapshot, ids, focus },
      );
    },
    close,
    get isOpen() {
      return !$("event-overview").hidden;
    },
  });
})();
