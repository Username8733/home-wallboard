"use strict";
window.WallboardKeyboard = (() => {
  let target = null,
    opened = false,
    lastShow = 0,
    automatic = true,
    blurTimer = null,
    requested = null;
  const attached = new WeakSet();
  function editable(el) {
    return (
      el?.nodeType === 1 &&
      (el.matches('textarea,[contenteditable="true"]') ||
        el.matches(
          'input:not([type]),input[type="text"],input[type="search"],input[type="email"],input[type="password"],input[type="url"],input[type="tel"],input[type="number"]',
        )) &&
      !el.disabled &&
      !el.readOnly
    );
  }
  function layout(on, height = 400) {
    opened = on;
    document.documentElement.style.setProperty(
      "--keyboard-space",
      Math.round(height / (window.devicePixelRatio || 1)) + "px",
    );
    document.body.classList.toggle("keyboard-open", on);
    if (on && target?.isConnected)
      setTimeout(() => {
        if (opened && target?.isConnected)
          target.scrollIntoView({ block: "center", behavior: "smooth" });
      }, 160);
  }
  async function request(on, manual = false) {
    if (on && state?.fire?.active) return;
    if (on && Date.now() - lastShow < 350) return;
    if (on) lastShow = Date.now();
    requested = on;
    try {
      const r = await fetch("/api/keyboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visible: on }),
      });
      const body = await r.json();
      if (!r.ok)
        throw Error(
          body.error || WallboardI18n.t("Tangentbordet kunde inte öppnas."),
        );
      layout(body.keyboard.visible, body.keyboard.height);
    } catch (e) {
      if (manual) window.WallboardSettings?.notice(e.message);
    } finally {
      requested = null;
    }
  }
  function focus(el) {
    if (!editable(el)) return;
    target = el;
    if (automatic) {
      request(true);
      wake();
    }
  }
  function attach(doc) {
    if (attached.has(doc)) return;
    attached.add(doc);
    doc.addEventListener("focusin", (e) => focus(e.target));
    doc.addEventListener(
      "pointerdown",
      (e) => {
        if (editable(e.target)) requestAnimationFrame(() => focus(e.target));
      },
      { passive: true },
    );
    doc.addEventListener("input", () => wake(), { passive: true });
    doc.addEventListener("focusout", () => {
      clearTimeout(blurTimer);
      blurTimer = setTimeout(() => {
        if (target?.ownerDocument.activeElement !== target) request(false);
      }, 200);
    });
  }
  function sync(kbd, prefs) {
    automatic = prefs?.keyboard_auto !== false;
    if (kbd && requested === null && opened !== kbd.visible)
      layout(kbd.visible, kbd.height);
  }
  function hide() {
    target?.blur();
    target = null;
    layout(false);
    return request(false);
  }
  function show() {
    if (target?.isConnected) target.focus({ preventScroll: true });
    return request(true, true);
  }
  attach(document);
  return Object.freeze({
    attach,
    sync,
    show,
    hide,
    get opened() {
      return opened;
    },
  });
})();
