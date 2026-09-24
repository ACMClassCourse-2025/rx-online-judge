"use strict";

(() => {
  const crab = document.querySelector(".mascot-crab");
  if (!crab) return;

  const mascot = crab.closest(".mascot");
  const message = mascot.querySelector(".mascot-message");
  const body = crab.querySelector(".mascot-body");
  const arms = crab.querySelectorAll(".mascot-arm");
  const pincers = crab.querySelectorAll(".mascot-pincer");
  const spark = crab.querySelector(".mascot-clap-spark");
  const eyes = [...crab.querySelectorAll(".mascot-gaze")].map((element) => ({
    element,
    x: -13,
    y: -18,
  }));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const randomDelay = (min, max) => min + Math.random() * (max - min);
  const smoothstep = (n) => n * n * (3 - 2 * n);
  const mix = (from, to, amount) => from + (to - from) * amount;
  const clapDuration = 340;
  const clapAngles = [
    [0, -12],
    [0.12, -12],
    [0.38, 22],
    [0.53, 73],
    [0.61, 73],
    [0.76, 32],
    [0.94, -12],
    [1, -12],
  ];
  const clapDip = [
    [0, 0],
    [0.32, 0],
    [0.56, 7],
    [0.82, -2],
    [1, 0],
  ];
  const clapSpark = [
    [0, 0],
    [0.49, 0],
    [0.54, 1],
    [0.68, 1],
    [0.8, 0],
    [1, 0],
  ];
  let visible = false;
  let awake = false;
  let hovered = false;
  let tracking = false;
  let pointer = null;
  let motion = "idle";
  let lift = 0;
  let clapTime = 0;
  let idleTime = 0;
  let frame = 0;
  let lastTime = null;
  let gazeTimer;
  let blinkTimer;
  let blinkEndTimer;

  function sample(keyframes, phase) {
    const index = keyframes.findIndex(([time]) => time >= phase);
    if (index <= 0) return keyframes[0][1];
    const [start, from] = keyframes[index - 1];
    const [end, to] = keyframes[index];
    return mix(from, to, (phase - start) / (end - start));
  }

  function setMotion(next) {
    motion = next;
    crab.dataset.motion = next;
  }

  function setHovered(next) {
    hovered = next;
    if (!awake) return;
    if (hovered && (motion === "idle" || motion === "lowering")) {
      setMotion("raising");
    } else if (!hovered && motion === "raising") {
      setMotion("lowering");
    }
    // Leaving during a clap only changes intent; the cycle owns its completion.
  }

  function advanceMotion(elapsed) {
    if (motion === "raising") {
      lift = Math.min(1, lift + elapsed / 420);
      if (lift === 1) {
        clapTime = 0;
        setMotion("clapping");
      }
    } else if (motion === "clapping") {
      clapTime += elapsed;
      if (clapTime >= clapDuration) {
        clapTime %= clapDuration;
        if (!hovered) {
          clapTime = 0;
          setMotion("lowering");
        }
      }
    } else if (motion === "lowering") {
      lift = Math.max(0, lift - elapsed / 520);
      if (lift === 0) setMotion("idle");
    }
  }

  function renderPose() {
    const blend = smoothstep(lift);
    const phase = motion === "clapping" ? clapTime / clapDuration : 0;
    const sway = Math.sin((idleTime / 2800) * Math.PI * 2);
    const rock = Math.sin((idleTime / 4200) * Math.PI * 2);
    const shoulder = (-40 + sway * 6) * (1 - blend);
    const wrist = mix(-12 + sway * 3, sample(clapAngles, phase), blend);
    for (const arm of arms) arm.setAttribute("transform", `rotate(${shoulder})`);
    for (const pincer of pincers) {
      pincer.setAttribute(
        "transform",
        `rotate(${wrist}) scale(${mix(0.82, 1, blend)})`,
      );
    }
    const dip = sample(clapDip, phase) + rock * 4 * (1 - blend);
    body.setAttribute(
      "transform",
      `translate(0,${dip}) rotate(${rock * 1.6 * (1 - blend)},607,490)`,
    );
    spark.style.opacity = sample(clapSpark, phase);
    spark.setAttribute("transform", `scale(${mix(0.7, 1.1, phase)})`);
  }

  function renderGaze(elapsed) {
    const matrix = pointer && tracking ? body.getScreenCTM() : null;
    const point = matrix
      ? new DOMPoint(pointer.x, pointer.y).matrixTransform(matrix.inverse())
      : null;
    const follow = 1 - Math.exp(-elapsed / 90);
    for (const eye of eyes) {
      let x = -13;
      let y = -18;
      if (point) {
        const dx = (point.x - eye.element.cx.baseVal.value) / 180;
        const dy = (point.y - eye.element.cy.baseVal.value) / 180;
        const distance = Math.max(1, Math.hypot(dx, dy));
        x = (dx / distance) * 22;
        y = (dy / distance) * 25;
      }
      eye.x = mix(eye.x, x, follow);
      eye.y = mix(eye.y, y, follow);
      eye.element.setAttribute("transform", `translate(${eye.x},${eye.y})`);
    }
  }

  function animate(time) {
    if (!awake) return;
    const elapsed = lastTime === null ? 0 : Math.min(time - lastTime, 64);
    lastTime = time;
    idleTime += elapsed;
    advanceMotion(elapsed);
    renderPose();
    renderGaze(elapsed);
    frame = requestAnimationFrame(animate);
  }

  function alternateGaze() {
    tracking = !tracking;
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

  function resetPose() {
    lift = clapTime = idleTime = 0;
    setMotion("idle");
    renderPose();
    for (const eye of eyes) {
      eye.x = -13;
      eye.y = -18;
      eye.element.setAttribute("transform", "translate(-13,-18)");
    }
  }

  function finishGreeting() {
    mascot.classList.remove("is-greeting");
    mascot.classList.add("has-greeted");
  }

  function syncActivity() {
    const next = visible && !document.hidden && !reducedMotion.matches;
    if (reducedMotion.matches) {
      resetPose();
      finishGreeting();
    }
    if (next === awake) return;
    awake = next;
    mascot.classList.toggle("is-awake", awake);
    crab.classList.toggle("is-awake", awake);
    if (awake) {
      if (!mascot.classList.contains("has-greeted"))
        mascot.classList.add("is-greeting");
      setHovered(hovered);
      alternateGaze();
      scheduleBlink();
      lastTime = null;
      frame = requestAnimationFrame(animate);
    } else {
      clearTimeout(gazeTimer);
      clearTimeout(blinkTimer);
      clearTimeout(blinkEndTimer);
      cancelAnimationFrame(frame);
      tracking = false;
      crab.classList.remove("is-blinking");
    }
  }

  document.addEventListener(
    "pointermove",
    (event) => {
      if (event.pointerType === "touch") return;
      pointer = { x: event.clientX, y: event.clientY };
      setHovered(crab.contains(event.target));
    },
    { passive: true },
  );

  crab.addEventListener("pointerenter", (event) => {
    if (event.pointerType !== "touch") setHovered(true);
  });
  crab.addEventListener("pointerleave", () => setHovered(false));

  function forgetPointer() {
    pointer = null;
    setHovered(false);
  }
  document.documentElement.addEventListener("pointerleave", forgetPointer);
  window.addEventListener("blur", forgetPointer);
  document.addEventListener("visibilitychange", syncActivity);
  reducedMotion.addEventListener("change", syncActivity);
  message.addEventListener("animationend", (event) => {
    if (event.animationName === "mascot-message-pop") finishGreeting();
  });

  const observer = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    syncActivity();
  });
  observer.observe(crab);
  setMotion("idle");
})();
