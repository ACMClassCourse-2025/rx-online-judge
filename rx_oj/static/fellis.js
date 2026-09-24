"use strict";

(() => {
  const crab = document.querySelector(".mascot-crab");
  if (!crab) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const randomDelay = (min, max) => min + Math.random() * (max - min);
  let visible = false;
  let awake = false;
  let hovered = false;
  let tracking = false;
  let pointer = null;
  let gazeTimer;
  let blinkTimer;
  let blinkEndTimer;
  let gazeFrame = 0;

  function restEyes() {
    crab.style.setProperty("--gaze-x", "0px");
    crab.style.setProperty("--gaze-y", "0px");
  }

  function updateGaze() {
    gazeFrame = 0;
    if (!awake || !tracking || !pointer || crab.classList.contains("is-clapping")) {
      restEyes();
      return;
    }

    // Use SVG coordinates so the gaze stays correct at every size and tilt.
    const matrix = crab.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(pointer.x, pointer.y).matrixTransform(
      matrix.inverse(),
    );
    const dx = (point.x - 615) / 240;
    const dy = (point.y - 445) / 240;
    const distance = Math.max(1, Math.hypot(dx, dy));
    crab.style.setProperty("--gaze-x", `${(dx / distance) * 16}px`);
    crab.style.setProperty("--gaze-y", `${(dy / distance) * 11}px`);
  }

  function requestGaze() {
    if (!gazeFrame) gazeFrame = requestAnimationFrame(updateGaze);
  }

  function alternateGaze() {
    tracking = !tracking;
    updateGaze();
    gazeTimer = setTimeout(
      alternateGaze,
      tracking ? randomDelay(1800, 3200) : randomDelay(2500, 4500),
    );
  }

  function scheduleBlink() {
    blinkTimer = setTimeout(() => {
      crab.classList.add("is-blinking");
      blinkEndTimer = setTimeout(() => {
        crab.classList.remove("is-blinking");
        scheduleBlink();
      }, 220);
    }, randomDelay(3200, 6800));
  }

  function syncActivity() {
    const next = visible && !document.hidden && !reducedMotion.matches;
    if (next === awake) return;
    awake = next;
    crab.classList.toggle("is-awake", awake);
    if (awake) {
      crab.classList.toggle("is-clapping", hovered);
      alternateGaze();
      scheduleBlink();
    } else {
      clearTimeout(gazeTimer);
      clearTimeout(blinkTimer);
      clearTimeout(blinkEndTimer);
      cancelAnimationFrame(gazeFrame);
      gazeFrame = 0;
      tracking = false;
      crab.classList.remove("is-blinking", "is-clapping");
      restEyes();
    }
  }

  document.addEventListener(
    "pointermove",
    (event) => {
      if (event.pointerType === "touch") return;
      pointer = { x: event.clientX, y: event.clientY };
      hovered = crab.contains(event.target);
      crab.classList.toggle("is-clapping", awake && hovered);
      if (awake && tracking) requestGaze();
    },
    { passive: true },
  );

  crab.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "touch") return;
    hovered = true;
    crab.classList.toggle("is-clapping", awake);
    restEyes();
  });
  crab.addEventListener("pointerleave", () => {
    hovered = false;
    crab.classList.remove("is-clapping");
    if (awake) requestGaze();
  });

  function forgetPointer() {
    pointer = null;
    hovered = false;
    crab.classList.remove("is-clapping");
    restEyes();
  }
  document.documentElement.addEventListener("pointerleave", forgetPointer);
  window.addEventListener("blur", forgetPointer);
  window.addEventListener(
    "scroll",
    () => {
      if (awake && tracking) requestGaze();
    },
    { passive: true },
  );
  window.addEventListener("resize", () => {
    if (awake && tracking) requestGaze();
  });
  document.addEventListener("visibilitychange", syncActivity);
  reducedMotion.addEventListener("change", syncActivity);

  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    syncActivity();
  });
  observer.observe(crab);
})();
