"use strict";
window.WallboardHomeAgenda = (() => {
  const $ = (id) => document.getElementById(id);
  const t = (value) => WallboardI18n.t(value);
  const normalize = (value) =>
    String(value)
      .normalize("NFC")
      .trim()
      .replace(/\s+/g, " ")
      .toLocaleLowerCase("sv-SE");
  let snapshot = { people: [], events: [], preferences: {} },
    items = [],
    loadedDay = "",
    busy = false,
    timer;
  let stale = false,
    loading = true,
    refreshing = false,
    renderKey = "";

  function today(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Stockholm",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    const part = (type) => parts.find((p) => p.type === type).value;
    return `${part("year")}-${part("month")}-${part("day")}`;
  }
  function route(record, data) {
    const people = data.people || [],
      prefs = data.preferences || {};
    const fallback =
      people.find((p) => p.id === prefs.onlineFallback) ||
      people.find((p) => p.id === "family") ||
      people[0];
    const match = /^(.+?)\s+[-–—]\s+(.+)$/s.exec(record.summary);
    const find = (name) => {
      const exact = people.filter((p) => normalize(p.name) === normalize(name));
      if (exact.length === 1) return exact[0];
      const aliases = people.filter((p) =>
        p.aliases?.some((a) => normalize(a) === normalize(name)),
      );
      return aliases.length === 1 ? aliases[0] : null;
    };
    const columns = match?.[1].split(",").map(find);
    const matched = columns?.length && columns.every(Boolean);
    return {
      ...record,
      id: "icloud-" + record.id,
      title: matched ? match[2].trim() : record.summary,
      people: matched
        ? [...new Set(columns.map((p) => p.id))]
        : fallback
          ? [fallback.id]
          : [],
      online: true,
      onlineRecord: record,
      writable: !!record.writable && !record.stale,
    };
  }
  function daily(data, records, day, now = new Date()) {
    const mode = data.preferences?.calendarMode || "local";
    const source = [
      ...(["local", "mixed"].includes(mode) ? data.events || [] : []),
      ...(mode !== "local" ? records.map((r) => route(r, data)) : []),
    ];
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Stockholm",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(now);
    const rank = (e) => {
      const end = e.endDate || e.date;
      if (end === day && e.end && e.end <= parts) return 2;
      if (end === day && !e.end && e.time && e.date === day && e.time < parts)
        return 2;
      return !e.time || e.date < day || e.time <= parts ? 0 : 1;
    };
    return source
      .filter(
        (e) =>
          e &&
          typeof e.title === "string" &&
          e.date <= day &&
          (e.endDate || e.date) >= day,
      )
      .sort(
        (a, b) =>
          rank(a) - rank(b) ||
          (a.time || "").localeCompare(b.time || "") ||
          a.title.localeCompare(b.title),
      );
  }
  function color(person) {
    return person?.color && CSS.supports("color", person.color)
      ? person.color
      : "var(--accent)";
  }
  function colorPeople() {
    for (const el of $("people").children) {
      const person = snapshot.people.find(
        (p) => normalize(p.name) === normalize(el.textContent.slice(1)),
      );
      if (person)
        el.querySelector(".avatar")?.style.setProperty(
          "--agenda-person",
          color(person),
        );
    }
  }
  function timeLabel(e) {
    if (!e.time && !e.end) return t("Hela dagen");
    const start =
      e.date < today()
        ? t("Pågår")
        : WallboardI18n.formatTime(e.time || "00:00");
    return (
      start +
      (e.end && (e.endDate || e.date) === today()
        ? " – " + WallboardI18n.formatTime(e.end)
        : "")
    );
  }
  function render() {
    if (!$("agenda-events")) return;
    const day = today();
    if (loadedDay && loadedDay !== day) {
      items = [];
      loading = true;
    }
    const count = items.length;
    $("agenda-count").textContent = count
      ? `${count} ${t(count === 1 ? "händelse" : "händelser")}`
      : "";
    $("agenda-message").textContent = stale
      ? t("Kalendern kan inte uppdateras just nu.")
      : loading
        ? t("Hämtar dagens händelser…")
        : refreshing
          ? t("Uppdaterar kalendern…")
          : count
            ? ""
            : t("Inget planerat idag");
    $("agenda-message").hidden = !$("agenda-message").textContent;
    const key = JSON.stringify([
      day,
      WallboardI18n.language,
      WallboardI18n.timeFormat,
      items.slice(0, 3),
      snapshot.people,
    ]);
    if (key !== renderKey) {
      renderKey = key;
      $("agenda-events").replaceChildren(
        ...items.slice(0, 3).map((event) => {
          const people = (event.people || (event.person ? [event.person] : []))
            .map((id) => snapshot.people.find((p) => p.id === id))
            .filter(Boolean);
          const button = document.createElement("button");
          button.type = "button";
          button.className = "agenda-event";
          button.style.setProperty("--agenda-person", color(people[0]));
          const time = document.createElement("span");
          time.className = "agenda-time";
          time.textContent =
            !event.time && !event.end
              ? t("Heldag")
              : event.date < day
                ? t("Pågår")
                : WallboardI18n.formatTime(event.time || "00:00");
          const detail = document.createElement("span");
          detail.className = "agenda-detail";
          const title = document.createElement("strong");
          title.textContent =
            (people.length
              ? people.map((p) => p.name).join(", ") + " – "
              : "") + event.title;
          const range = document.createElement("small");
          range.textContent = timeLabel(event);
          detail.append(title, range);
          const chevron = document.createElement("span");
          chevron.className = "agenda-chevron";
          chevron.textContent = "›";
          chevron.setAttribute("aria-hidden", "true");
          button.append(time, detail, chevron);
          button.title = title.textContent + " · " + range.textContent;
          button.onclick = () => {
            window.WallboardPlannerOverview.showHome(event, snapshot, button);
            window.WallboardPages.readyPlanner().catch(() => {});
          };
          return button;
        }),
      );
    }
    colorPeople();
  }
  async function get(path) {
    const response = await fetch("/planner/api/" + path, {
      cache: "no-store",
      signal: AbortSignal.timeout(40000),
    });
    if (!response.ok) throw new Error("Planner unavailable");
    return response.json();
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    clearTimeout(timer);
    let delay = 30000;
    const day = today();
    try {
      const result = await get("state");
      const data = result.state || {
        people: [],
        events: [],
        preferences: { calendarMode: "local" },
      };
      if (!Array.isArray(data.people) || !Array.isArray(data.events))
        throw new Error("Invalid planner data");
      let online = { events: [] };
      if (
        data.preferences?.calendarMode &&
        data.preferences.calendarMode !== "local"
      ) {
        const [year, month] = day.split("-").map(Number);
        const end = `${month === 12 ? year + 1 : year}-${String(month === 12 ? 1 : month + 1).padStart(2, "0")}-01`;
        online = await get(
          "v2/events?" +
            new URLSearchParams({ start: day.slice(0, 7) + "-01", end }),
        );
        if (!Array.isArray(online.events))
          throw new Error("Invalid online events");
      }
      // Keep the last successful rows of a failed source, matching Family Planner's cache policy.
      const failed = new Set((online.errors || []).map((e) => e.sourceKey));
      const returned = new Set(online.events.map((e) => "icloud-" + e.id));
      const retained =
        loadedDay === day
          ? items
              .filter(
                (e) =>
                  e.online && failed.has(e.sourceKey) && !returned.has(e.id),
              )
              .map((e) => ({ ...e.onlineRecord, writable: false, stale: true }))
          : [];
      snapshot = data;
      stale = !!online.cache?.stale || failed.size > 0;
      refreshing = !!online.cache?.refreshing;
      const records = [...online.events, ...retained].map((e) =>
        stale ? { ...e, writable: false } : e,
      );
      items = daily(data, records, day);
      loadedDay = day;
      loading = false;
      if (refreshing) delay = 1500;
    } catch {
      stale = true;
      loading = false;
      if (loadedDay !== day) items = [];
      items = items.map((e) => ({ ...e, writable: false }));
    } finally {
      busy = false;
      render();
      timer = setTimeout(refresh, delay);
    }
  }
  async function edit(event) {
    if (state?.fire?.active) return;
    try {
      WallboardPages.setPage("planner");
      const frame = await WallboardPages.readyPlanner();
      if (state?.fire?.active) return;
      await frame.contentWindow.syncSharedState();
      if (
        !event.online &&
        !frame.contentWindow
          .plannerSnapshot()
          .events.some((e) => e.id === event.id)
      )
        throw new Error("Event removed");
      frame.contentWindow.editEvent(event, event.date, event.people?.[0]);
    } catch {
      $("planner-retry").hidden = false;
    }
  }
  if ($("agenda-all")) {
    let returnHome = null,
      navigation = 0;
    window.addEventListener("wallboard-page-change", () => {
      navigation += 1;
      returnHome?.abort();
      returnHome = null;
    });
    $("agenda-all").onclick = async () => {
      if (state?.fire?.active) return;
      try {
        WallboardPages.setPage("planner");
        const openedAt = navigation;
        const frame = await WallboardPages.readyPlanner();
        if (state?.fire?.active || navigation !== openedAt) return;
        await frame.contentWindow.wallboardOpenToday(today());
        if (state?.fire?.active || navigation !== openedAt) return;
        returnHome = new AbortController();
        frame.contentDocument.getElementById("day-detail").addEventListener(
          "close",
          () => {
            if (WallboardPages.page !== "planner" || state?.fire?.active)
              return;
            WallboardPages.setPage("home");
            $("agenda-all").focus({ preventScroll: true });
          },
          { once: true, signal: returnHome.signal },
        );
      } catch {
        $("planner-retry").hidden = false;
      }
    };
    window.addEventListener("wallboard-locale-change", render);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
    refresh();
  }
  return Object.freeze({ refresh, edit, colorPeople, today, daily, route });
})();
