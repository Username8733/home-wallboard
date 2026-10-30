"use strict";
window.WallboardScrollbars = (() => {
  const installed = new WeakMap();
  function install(doc) {
    if (installed.has(doc)) return;
    const win = doc.defaultView;
    if (!win) return;
    if (!doc.querySelector('link[href="/static/scrollbars.css"]')) {
      const css = doc.createElement("link");
      css.rel = "stylesheet";
      css.href = "/static/scrollbars.css";
      doc.head.append(css);
    }
    const handles = new Map();
    let queued = false,
      serial = 0;
    function visible(el) {
      return (
        el.isConnected &&
        el.getClientRects().length &&
        win.getComputedStyle(el).visibility !== "hidden"
      );
    }
    function update(handle) {
      const { el, track, thumb, axis } = handle,
        vertical = axis === "y";
      const rect =
          el === doc.scrollingElement
            ? {
                top: 0,
                left: 0,
                right: win.innerWidth,
                bottom: win.innerHeight,
              }
            : el.getBoundingClientRect(),
        extent = vertical ? el.clientHeight : el.clientWidth,
        total = vertical ? el.scrollHeight : el.scrollWidth,
        offset = vertical ? el.scrollTop : el.scrollLeft;
      const sleeping =
        doc === document &&
        document.body.classList.contains("night-screen-off");
      const fire =
        doc === document &&
        !document.getElementById("fire-view")?.hidden &&
        !el.closest("#fire-view");
      track.hidden =
        !visible(el) || total <= extent + 2 || extent < 40 || sleeping || fire;
      if (track.hidden) return;
      const host = el.closest("dialog[open]") || doc.body;
      if (track.parentNode !== host) host.append(track);
      const length = Math.max(36, (extent * extent) / total),
        travel = extent - length;
      handle.extent = extent;
      handle.total = total;
      handle.travel = travel;
      if (vertical) {
        Object.assign(track.style, {
          left: rect.right - 21 + "px",
          top: rect.top + "px",
          height: extent + "px",
        });
        Object.assign(thumb.style, {
          top: (offset / (total - extent)) * travel + "px",
          height: length + "px",
        });
      } else {
        Object.assign(track.style, {
          left: rect.left + "px",
          top: rect.bottom - 21 + "px",
          width: extent + "px",
        });
        Object.assign(thumb.style, {
          left: (offset / (total - extent)) * travel + "px",
          width: length + "px",
        });
      }
      track.setAttribute("aria-valuemax", String(total - extent));
      track.setAttribute("aria-valuenow", String(Math.round(offset)));
    }
    function make(el, axis) {
      const track = doc.createElement("div"),
        thumb = doc.createElement("div");
      track.className = "wb-scroll-track";
      thumb.className = "wb-scroll-thumb";
      track.append(thumb);
      track.dataset.axis = axis;
      track.tabIndex = 0;
      track.setAttribute("role", "scrollbar");
      track.setAttribute(
        "aria-orientation",
        axis === "y" ? "vertical" : "horizontal",
      );
      track.setAttribute("aria-valuemin", "0");
      track.setAttribute(
        "aria-label",
        axis === "y" ? "Scroll vertically" : "Scroll horizontally",
      );
      if (!el.id) el.id = "wb-scroll-area-" + ++serial;
      track.setAttribute("aria-controls", el.id);
      const handle = { el, axis, track, thumb };
      let dragging = null;
      const pos = (e) => (axis === "y" ? e.clientY : e.clientX);
      const get = () => (axis === "y" ? el.scrollTop : el.scrollLeft);
      const set = (value) => {
        if (axis === "y") el.scrollTop = value;
        else el.scrollLeft = value;
        update(handle);
      };
      track.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        update(handle);
        const r = thumb.getBoundingClientRect(),
          coordinate = pos(e);
        if (
          coordinate < (axis === "y" ? r.top : r.left) ||
          coordinate > (axis === "y" ? r.bottom : r.right)
        ) {
          const tr = track.getBoundingClientRect();
          set(
            ((coordinate -
              (axis === "y" ? tr.top : tr.left) -
              (handle.extent - handle.travel) / 2) /
              handle.travel) *
              (handle.total - handle.extent),
          );
        }
        dragging = {
          pointer: e.pointerId,
          position: coordinate,
          offset: get(),
        };
        track.dataset.dragging = "true";
        track.setPointerCapture(e.pointerId);
      });
      track.addEventListener("pointermove", (e) => {
        if (!dragging || e.pointerId !== dragging.pointer) return;
        e.preventDefault();
        e.stopPropagation();
        set(
          dragging.offset +
            ((pos(e) - dragging.position) / handle.travel) *
              (handle.total - handle.extent),
        );
      });
      function finish(e) {
        if (!dragging || e.pointerId !== dragging.pointer) return;
        dragging = null;
        delete track.dataset.dragging;
        e.stopPropagation();
      }
      for (const type of ["pointerup", "pointercancel", "lostpointercapture"])
        track.addEventListener(type, finish);
      track.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
      });
      track.addEventListener("keydown", (e) => {
        const delta = {
          ArrowDown: 40,
          ArrowRight: 40,
          ArrowUp: -40,
          ArrowLeft: -40,
          PageDown: handle.extent * 0.8,
          PageUp: -handle.extent * 0.8,
        };
        if (e.key in delta || ["Home", "End"].includes(e.key)) {
          e.preventDefault();
          set(
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? handle.total
                : get() + delta[e.key],
          );
        }
      });
      doc.body.append(track);
      return handle;
    }
    function scan() {
      queued = false;
      const found = new Set();
      for (const el of [
        doc.scrollingElement,
        ...doc.querySelectorAll("body *"),
      ]) {
        if (!el || el.closest(".wb-scroll-track") || !visible(el)) continue;
        const css = win.getComputedStyle(el);
        for (const axis of ["y", "x"]) {
          const extent = axis === "y" ? el.clientHeight : el.clientWidth,
            total = axis === "y" ? el.scrollHeight : el.scrollWidth;
          const overflow = axis === "y" ? css.overflowY : css.overflowX;
          if (
            extent < 40 ||
            total <= extent + 2 ||
            !(el === doc.scrollingElement || /^(auto|scroll)$/.test(overflow))
          )
            continue;
          let pair = handles.get(el);
          if (!pair) {
            pair = {};
            handles.set(el, pair);
          }
          if (!pair[axis]) pair[axis] = make(el, axis);
          if (!el.classList.contains("wb-scroll-managed"))
            el.classList.add("wb-scroll-managed");
          found.add(pair[axis]);
          update(pair[axis]);
        }
      }
      for (const [el, pair] of handles) {
        for (const axis of ["x", "y"])
          if (
            pair[axis] &&
            !found.has(pair[axis]) &&
            !pair[axis].track.dataset.dragging
          ) {
            pair[axis].track.remove();
            delete pair[axis];
          }
        if (!pair.x && !pair.y) {
          handles.delete(el);
          el.classList.remove("wb-scroll-managed");
        }
      }
    }
    function schedule() {
      if (!queued) {
        queued = true;
        win.requestAnimationFrame(scan);
      }
    }
    const observer = new win.MutationObserver((records) => {
      if (
        records.some(
          (r) =>
            !r.target.closest?.(".wb-scroll-track") &&
            !(
              r.type === "childList" &&
              [...r.addedNodes, ...r.removedNodes].every(
                (n) =>
                  n.nodeType === 1 && n.classList.contains("wb-scroll-track"),
              )
            ),
        )
      )
        schedule();
    });
    observer.observe(doc.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden", "open", "class"],
    });
    doc.addEventListener(
      "scroll",
      () => {
        for (const pair of handles.values())
          for (const h of Object.values(pair)) update(h);
      },
      true,
    );
    win.addEventListener("resize", schedule);
    const resize = new win.ResizeObserver(schedule);
    resize.observe(doc.body);
    const timer = win.setInterval(schedule, 1500);
    win.addEventListener(
      "pagehide",
      () => {
        observer.disconnect();
        resize.disconnect();
        win.clearInterval(timer);
      },
      { once: true },
    );
    installed.set(doc, { schedule });
    schedule();
  }
  install(document);
  document.getElementById("planner-frame")?.addEventListener("load", () => {
    try {
      install(document.getElementById("planner-frame").contentDocument);
    } catch {}
  });
  return { install, refresh: () => installed.get(document)?.schedule() };
})();
