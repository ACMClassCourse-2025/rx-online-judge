"use strict";

// The scene is mounted once. Polling only changes text and state, never animation nodes.
const RunPage = (() => {
  const el = (id) => document.getElementById(id);
  const stages = ["semantic", "ir", "codegen", "optimization"];
  const names = {
    semantic: "Semantic",
    ir: "LLVM IR",
    codegen: "Code generation",
    optimization: "Optimization",
  };
  const landscapes = {
    semantic: "the coast",
    ir: "the woodlands",
    codegen: "the mountains",
    optimization: "the night sky",
  };
  const captions = {
    semantic: "Taking the scenic route. Everything has to make sense first.",
    ir: "Into the green. A fresh perspective on your program.",
    codegen: "On to higher ground. One instruction at a time.",
    optimization: "Chasing fewer cycles under a sky full of stars.",
  };
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = matchMedia("(max-width: 800px)");
  let submission = null;
  let mounted = false;
  let active = false;
  let visible = true;
  let scrollFrame = 0;
  let previousStatus = "";
  const revealDistance = 520;

  function mountArt() {
    if (mounted) return;
    mounted = true;
    el("ride-art").innerHTML =
      `<svg viewBox="0 -100 1200 620" preserveAspectRatio="xMidYMax meet" xmlns="http://www.w3.org/2000/svg" focusable="false">
      <defs>
        <pattern id="ride-dashes" width="150" height="10" patternUnits="userSpaceOnUse"><path d="M15 5h62" stroke="var(--road-mark)" stroke-width="3" stroke-linecap="round"/></pattern>
        <pattern id="ride-grip" width="5" height="5" patternUnits="userSpaceOnUse"><rect width="5" height="5" fill="#343e42"/><circle cx="1" cy="1" r=".55" fill="#7a8887" opacity=".6"/></pattern>
        <g id="ride-tree"><path d="M0 0v88" stroke="#526b55" stroke-width="7"/><path d="M-43 34 0-48 43 34ZM-35 3 0-67 35 3Z" fill="var(--trees)"/></g>
        <g id="ride-palm"><path d="M0 0Q15-61 5-112" stroke="#9d7650" stroke-width="10" fill="none"/><path d="M5-110Q-51-157-76-98Q-34-126 5-110Q-6-171 36-175Q18-140 5-110Q53-161 91-116Q48-130 5-110Q48-116 64-70Q30-98 5-110Q-40-123-43-70Q-21-103 5-110" fill="#508e76"/></g>
        <g id="ride-cloud" fill="var(--cloud)"><path d="M0 20Q-5 0 17 0Q19-28 46-22Q70-21 72 0Q95-5 99 20Z"/></g>
        <g id="ride-cloud-tile"><use href="#ride-cloud" x="180" y="90" transform="scale(.7)"/><use href="#ride-cloud" x="680" y="66"/><use href="#ride-cloud" x="1060" y="177"/></g>
        <g id="ride-star-tile" fill="#e8dbaf"><circle cx="134" cy="128" r="2"/><circle cx="300" cy="24" r="3"/><circle cx="460" cy="147" r="2"/><circle cx="640" cy="89" r="2"/><circle cx="846" cy="47" r="3"/><circle cx="1095" cy="168" r="2"/><path d="m1035 79 2 7 7 2-7 2-2 7-2-7-7-2 7-2Z"/><path d="m550 0 2 7 7 2-7 2-2 7-2-7-7-2 7-2Z"/></g>
        <path id="ride-hill-back-tile" d="M0 290C100 290 110 226 240 226S390 290 490 290S630 236 730 236S900 286 980 286S1110 290 1200 290V430H0Z" fill="var(--hill-back)"/>
        <path id="ride-hill-front-tile" d="M0 348C90 348 110 291 230 291S360 350 480 350S640 300 760 300S920 340 1000 340S1110 348 1200 348V435H0Z" fill="var(--hill-front)"/>
        <g id="ride-mountain-back-tile"><path d="M0 390 160 312 350 360 570 139 698 273 858 71 1110 360 1200 390V425H0Z" fill="var(--hill-back)"/><path d="m500 210 70-71 57 60-44-12-23 30-18-26ZM802 143l56-72 83 94-65-22-21 14-21-24Z" fill="#e8ede5"/></g>
        <path id="ride-mountain-front-tile" d="M0 390 262 181 460 375 681 238 967 375 1100 340 1200 390V430H0Z" fill="var(--hill-front)"/>
        <g id="ride-palm-tile"><use href="#ride-palm" x="105" y="390"/><use href="#ride-palm" transform="translate(1090,385) scale(.8)"/></g>
        <g id="ride-tree-tile"><use href="#ride-tree" x="94" y="318"/><use href="#ride-tree" x="190" y="332"/><use href="#ride-tree" x="773" y="314"/><use href="#ride-tree" x="1075" y="300"/></g>
        <g id="ride-rock-tile" fill="var(--hill-back)"><path d="m103 404 20-40 34-8 32 48Zm963 0 30-49 39 7 22 42Z"/></g>
        <g id="ride-wave-tile" stroke="#fff" stroke-width="2" opacity=".5"><path d="M20 352h108m46 15h63m263-21h86m80 26h121m102-28h49m159 20h96M64 388h75m245-9h116m363 16h87"/></g>
        <g id="ride-verge-tile" fill="var(--road-edge)" opacity=".5"><path d="m121 502 6-10 4 10m4 0 7-7 1 7m852 3 4-10 6 10m-824-6h16m876 2h24"/></g>
      </defs>
      <g class="ride-stars ride-parallax"><use href="#ride-star-tile"/><use href="#ride-star-tile" x="1200"/></g>
      <g class="ride-sun"><circle cx="962" cy="100" r="68" fill="var(--sun)" opacity=".15"/>
      <circle cx="962" cy="100" r="43" fill="var(--sun)"/></g>
      <g class="ride-clouds ride-parallax"><use href="#ride-cloud-tile"/><use href="#ride-cloud-tile" x="1200"/></g>
      <g class="ride-distant">
        <g class="ride-far ride-parallax"><use href="#ride-hill-back-tile"/><use href="#ride-hill-back-tile" x="1200"/></g>
        <g class="ride-near ride-parallax"><use href="#ride-hill-front-tile"/><use href="#ride-hill-front-tile" x="1200"/></g>
      </g>
      <g class="ride-mountains">
        <g class="ride-far ride-parallax"><use href="#ride-mountain-back-tile"/><use href="#ride-mountain-back-tile" x="1200"/></g>
        <g class="ride-near ride-parallax"><use href="#ride-mountain-front-tile"/><use href="#ride-mountain-front-tile" x="1200"/></g>
      </g>
      <path class="ride-water" d="M0 338H1200V413H0Z" fill="var(--water)"/>
      <g class="ride-waves ride-parallax"><use href="#ride-wave-tile"/><use href="#ride-wave-tile" x="1200"/></g>
      <g class="ride-scenery ride-parallax">
        <g class="ride-palms"><use href="#ride-palm-tile"/><use href="#ride-palm-tile" x="1200"/></g>
        <g class="ride-trees"><use href="#ride-tree-tile"/><use href="#ride-tree-tile" x="1200"/></g>
        <g class="ride-rocks"><use href="#ride-rock-tile"/><use href="#ride-rock-tile" x="1200"/></g>
      </g>
      <path d="M0 404H1200V620H0Z" fill="var(--ground)"/>
      <path d="M0 424H1200V483H0Z" fill="var(--road)"/>
      <path d="M0 424H1200" stroke="var(--road-edge)" stroke-width="3"/>
      <g class="ride-road-motion"><rect x="0" y="454" width="1350" height="10" fill="url(#ride-dashes)"/></g>
      <g class="ride-roadside" transform="translate(865,285)"><path d="M0 58v79m149-79v79" stroke="var(--sign-post)" stroke-width="6"/><rect width="163" height="73" x="-7" y="-7" rx="8" fill="var(--sign-post)"/><rect width="151" height="61" x="-1" y="-1" rx="5" fill="var(--sign)" stroke="var(--sign-ink)" stroke-opacity=".35"/>
        <text id="ride-sign-title" x="74" y="23" text-anchor="middle" fill="var(--sign-ink)" font-size="11" letter-spacing="1.5">NEXT UP</text><text id="ride-sign-value" x="74" y="46" text-anchor="middle" fill="var(--sign-ink)" font-size="16" font-weight="600">YOUR TURN →</text>
      </g>
      <g transform="translate(270,264)">
        <ellipse cx="140" cy="191" rx="127" ry="6" fill="#383d33" opacity=".14"/>
        <g class="ride-rider">
          <g class="ride-crab-position"><g id="ride-crab" transform="translate(4,0) scale(.22)"></g></g>
          <g class="ride-board">
            <g fill="#54686b" stroke="#35484e" stroke-width="1.5">
              <path d="M74 162h23l-4 5H78Zm109 0h23l-4 5h-15Z"/>
              <path d="m85 165 3 12m106-12 3 12" stroke-width="4"/>
              <path d="M74 176h24m86 0h24" stroke="#aab6ae" stroke-width="4" stroke-linecap="round"/>
            </g>
            <g transform="translate(86,178)"><g class="ride-wheel"><circle r="12" fill="#bd813d" stroke="#78552e" stroke-width="1"/><circle cx="1" cy="-1" r="10" fill="#efc477"/><circle cx="1" cy="-1" r="5" fill="#d59e52"/><path d="M-5-7-3-5M7 4 5 2" stroke="#f9df9f" stroke-width="2" stroke-linecap="round"/><circle cx="1" cy="-1" r="3" fill="#546367"/><circle cx="1" cy="-1" r="1.3" fill="#c2cfc8"/></g></g>
            <g transform="translate(195,178)"><g class="ride-wheel"><circle r="12" fill="#bd813d" stroke="#78552e" stroke-width="1"/><circle cx="1" cy="-1" r="10" fill="#efc477"/><circle cx="1" cy="-1" r="5" fill="#d59e52"/><path d="M-5-7-3-5M7 4 5 2" stroke="#f9df9f" stroke-width="2" stroke-linecap="round"/><circle cx="1" cy="-1" r="3" fill="#546367"/><circle cx="1" cy="-1" r="1.3" fill="#c2cfc8"/></g></g>
            <path d="M27 147Q42 151 57 155H220Q238 155 253 144L252 151Q238 166 220 167H60Q40 166 27 154Z" fill="#b67e43" stroke="#3c4b4d" stroke-width="2" stroke-linejoin="round"/>
            <path d="M30 154Q44 162 62 163H219Q238 162 250 151" fill="none" stroke="#f1d29b" stroke-width="2"/>
            <path d="M27 146Q37 139 51 145L66 149H218Q235 148 246 140Q255 138 255 145Q240 159 220 160H61Q42 158 27 151Z" fill="#ebbd72" stroke="#3c4b4d" stroke-width="2"/>
            <path d="M37 146Q43 145 53 150L67 153H216Q235 153 245 145L249 145Q237 156 220 157H62Q47 155 37 149Z" fill="url(#ride-grip)"/>
            <path d="m58 151 8 6m150-5-5 6" stroke="#c77548" stroke-width="3"/>
            <g fill="#c7c9b7"><circle cx="80" cy="154" r="1.2"/><circle cx="91" cy="154" r="1.2"/><circle cx="190" cy="154" r="1.2"/><circle cx="201" cy="154" r="1.2"/></g>
          </g>
        </g>
      </g>
      <g class="ride-verge ride-parallax"><use href="#ride-verge-tile"/><use href="#ride-verge-tile" x="1200"/></g>
    </svg>`;
    const crab = document.querySelector(".mascot-body").cloneNode(true);
    for (const node of [crab, ...crab.querySelectorAll("*")]) {
      if (node.hasAttribute("class"))
        node.setAttribute(
          "class",
          node.getAttribute("class").replaceAll("mascot-", "ride-ferris-"),
        );
      if (node.id) node.id = `ride-${node.id}`;
      if (node.hasAttribute("clip-path"))
        node.setAttribute(
          "clip-path",
          node.getAttribute("clip-path").replace("#fellis", "#ride-fellis"),
        );
    }
    crab.querySelector(".ride-ferris-clap-spark").remove();
    el("ride-crab").append(crab);
    el("ride-crab").parentElement.addEventListener("animationend", (event) => {
      if (event.animationName === "ride-board-on")
        el("ride-scene").classList.remove("is-boarding");
    });
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      syncMotion();
    }).observe(el("ride-scene"));
  }

  function syncMotion() {
    if (motion.matches) el("ride-scene").classList.remove("is-boarding");
    el("ride-scene").classList.toggle(
      "is-moving",
      active && visible && !document.hidden && !motion.matches,
    );
  }

  function scrollLayout() {
    scrollFrame = 0;
    if (!active) return;
    const top = el("ride-runway").getBoundingClientRect().top;
    const distance = narrow.matches
      ? Math.max(1, el("ride-scene").parentElement.offsetHeight - 136)
      : revealDistance;
    const amount = Math.min(1, Math.max(0, -top / distance));
    el("ride-sticky").style.setProperty("--reveal", amount.toFixed(4));
    el("ride-sticky").classList.toggle("is-detailed", amount > 0.85);
    el("ride-stages").setAttribute("aria-hidden", String(amount < 0.5));
    el("ride-copy").setAttribute("aria-hidden", String(amount >= 0.5));
    el("ride-live").inert = !narrow.matches && amount < 0.85;
    el("ride-peek").setAttribute(
      "aria-label",
      amount > 0.85 ? "Back to full scene" : "Show results and system log",
    );
    el("ride-peek").title =
      amount > 0.85 ? "Back to full scene" : "Show results and system log";
    el("ride-peek").textContent = amount > 0.85 ? "↑" : "↓";
  }
  function scheduleScroll() {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(scrollLayout);
  }
  function activate(value) {
    active = value;
    document.body.classList.toggle("viewing-run", value);
    syncMotion();
    scheduleScroll();
  }
  function reset() {
    mountArt();
    submission = null;
    previousStatus = "";
    el("run-name").textContent = "Loading your run…";
    el("run-meta").textContent = "";
    el("run-status").textContent = "";
    el("run-error").hidden = true;
    el("run-content").hidden = false;
    el("cancel-submission").hidden = true;
    el("void-submission").hidden = true;
    el("run-void-info").hidden = true;
    el("run-facts").replaceChildren();
    el("ride-log").replaceChildren();
    el("ride-live-body").scrollTop = 0;
    el("run-score").hidden = true;
    el("run-score-details").open = false;
    el("run-score-cases").replaceChildren();
    el("ride-scene").dataset.status = "queued";
    el("ride-scene").dataset.theme = "semantic";
    el("ride-scene").classList.remove("is-boarding");
    el("ride-headline").textContent = "Ready to roll.";
    el("ride-caption").textContent =
      "A little patience. The open road is just ahead.";
    el("ride-stages").replaceChildren();
    el("ride-current-label").textContent = "Loading your run…";
    el("ride-current-case").textContent = "";
    el("ride-brief").textContent = "Loading your run…";
    el("ride-percent").textContent = "0%";
    el("ride-progress-fill").style.width = "0%";
    el("ride-progress").setAttribute("aria-valuenow", "0");
    el("ride-progress").setAttribute("aria-valuetext", "Loading your run");
    el("ride-sign-title").textContent = "NEXT UP";
    el("ride-sign-value").textContent = "YOUR TURN →";
    el("ride-live-title").textContent = "Current run";
  }
  function error(message) {
    el("run-error").textContent = message;
    el("run-error").hidden = false;
    if (!submission) el("run-name").textContent = "Run unavailable";
  }
  function stageData(s) {
    const included = stages.slice(
      0,
      Math.max(0, stages.indexOf(s.suite || s.stage)) + 1,
    );
    return included.map((id) => {
      const results = s.results.filter((r) => r.stage === id);
      const total =
        s.stage_counts?.[id] ??
        (s.catalog_version === state.catalog?.version
          ? state.catalog.stages[id]
          : null);
      const passed = results.filter((r) => r.verdict === "accepted").length;
      return {
        id,
        total,
        completed: results.length,
        passed,
        failed: results.length - passed,
      };
    });
  }
  function currentStage(s, counts) {
    if (s.current_stage && stages.includes(s.current_stage))
      return s.current_stage;
    return (
      counts.find((c) => c.total && c.completed < c.total)?.id ||
      s.results.at(-1)?.stage ||
      "semantic"
    );
  }
  function phaseText(s, stage) {
    if (s.cancel_requested && !terminal(s.status)) return "Stopping the run…";
    if (s.status === "queued") return "Waiting for a worker";
    if (terminal(s.status)) return label(s.status);
    if (s.phase === "fetching") return "Fetching your repository";
    if (s.phase === "dependencies") return "Preparing dependencies";
    if (s.phase === "building") return "Building your compiler";
    if (s.phase === "testing" || s.results.length)
      return `Testing · ${names[stage]}`;
    return "Preparing your compiler";
  }
  function renderScore(s) {
    const panel = el("run-score");
    panel.hidden = (s.suite || s.stage) !== "optimization";
    if (panel.hidden) return;
    const score = s.optimization_score;
    panel.dataset.ready = String(Boolean(score));
    el("run-score-details").hidden = !score;
    el("run-score-description").hidden = Boolean(score);
    if (score) {
      el("run-score-value").textContent = scoreText(score.score);
      el("run-score-description").textContent = "";
      el("run-score-baseline").textContent =
        `Rust baseline ${score.baseline_id.slice(0, 12)}`;
      const table = scoreTable(score.cases);
      if (el("run-score-cases").innerHTML !== table)
        el("run-score-cases").innerHTML = table;
      return;
    }
    el("run-score-details").open = false;
    el("run-score-cases").replaceChildren();
    let value = "Not scored";
    let description =
      "All four suites must pass to earn an optimization score.";
    if (s.status === "voided") {
      value = "Voided";
      description =
        "This run was voided by an administrator and does not count toward optimization scores.";
    } else if (!terminal(s.status)) {
      value = "Pending";
      description = "Your score appears after all four suites pass.";
    } else if (s.status === "accepted") {
      if (
        s.catalog_version &&
        state.catalog?.version &&
        s.catalog_version !== state.catalog.version
      ) {
        description =
          "This run uses an older test catalog. Submit it again to earn a score.";
      } else if (s.optimization_baseline_status === "missing") {
        value = "Awaiting baseline";
        description =
          "The official Rust baseline is not available yet. This run will be scored automatically when it is ready.";
      } else if (s.optimization_baseline_status === "stale") {
        value = "Awaiting baseline";
        description =
          "The Rust baseline no longer matches the test catalog. Your administrator needs to regenerate it.";
      } else {
        description =
          "A score requires a matching Rust baseline and complete, valid optimization results.";
      }
    }
    el("run-score-value").textContent = value;
    el("run-score-description").textContent = description;
  }
  function update(s) {
    mountArt();
    const revealScore =
      Boolean(s.optimization_score) && !submission?.optimization_score;
    const body = el("ride-live-body");
    const scrollTop = body.scrollTop;
    const atBottom = body.scrollHeight - body.clientHeight - scrollTop < 30;
    submission = s;
    el("run-content").hidden = false;
    el("run-error").hidden = true;
    const counts = stageData(s);
    const stage = currentStage(s, counts);
    const done = terminal(s.status);
    const accepted = s.status === "accepted";
    const queued = s.status === "queued";
    const phase = phaseText(s, stage);
    const progress = s.total
      ? Math.min(100, Math.floor((s.completed / s.total) * 100))
      : 0;
    el("run-name").textContent = s.name;
    el("ride-live-title").textContent = s.name;
    el("run-meta").textContent =
      `${languageName(s.language)} · ${s.id.slice(0, 8)}`;
    el("run-status").innerHTML = badge(s.status);
    el("void-submission").hidden =
      !state.user?.is_admin || s.status === "voided";
    el("void-submission").onclick = () => ManagePage.confirmVoid(s);
    el("run-void-info").hidden = s.status !== "voided";
    el("run-void-info").textContent =
      s.status === "voided"
        ? `Voided by ${s.voided_by_name || "an administrator"}${s.voided_at ? ` · ${date(s.voided_at)}` : ""}. Previous status: ${label(s.status_before_void || "unknown")}. Excluded from optimization scoring.`
        : "";
    const facts = [
      ["Account", s.owner || "Legacy submission"],
      ["Run ID", s.id],
      ["Suite", label(s.suite || s.stage)],
      ["Repository", s.repository_url],
      ["Ref", s.git_ref],
      ["Commit", s.commit_sha || "Not resolved"],
      ["Submitted", date(s.created_at)],
    ];
    el("run-facts").innerHTML = facts
      .map(([name, value]) => `<dt>${name}</dt><dd>${escapeHTML(value)}</dd>`)
      .join("");
    el("cancel-submission").hidden = done;
    el("cancel-submission").disabled = Boolean(s.cancel_requested);
    el("cancel-submission").textContent = s.cancel_requested
      ? "Cancelling…"
      : "Cancel run";
    document.title = `${s.name} · ${label(s.status)} · Rx Compiler Judge`;
    el("ride-scene").dataset.theme = stage;
    el("ride-scene").dataset.status = queued
      ? "queued"
      : done
        ? accepted
          ? "accepted"
          : "failed"
        : "running";
    el("ride-scene").setAttribute(
      "aria-label",
      queued
        ? "Ferris waiting behind his skateboard for a worker."
        : done
          ? `Ferris staying on his skateboard, ${accepted ? "claws resting happily" : "waving his claws encouragingly"}. ${label(s.status)}.`
          : `Ferris riding a skateboard through ${landscapes[stage]}. ${s.completed} of ${s.total} tests completed.`,
    );
    let headline = names[stage];
    let caption = captions[stage];
    if (queued) {
      headline = "In the queue.";
      caption = "A little patience. The open road is just ahead.";
    } else if (s.status === "voided") {
      headline = "Voided.";
      caption = "This run has been excluded from optimization scoring.";
    } else if (done) {
      caption = accepted
        ? "Every check passed. Take a moment to enjoy the view."
        : s.status === "cancelled"
          ? "Taking a breather. There’s always another ride."
          : "A bump in the road. The System log has the details.";
      if (
        ["build_error", "source_error", "system_error", "time_limit"].includes(
          s.status,
        )
      )
        headline = label(s.status);
    } else if (s.phase === "fetching") {
      headline = "Fetching source.";
      caption = "Picking up your code before we hit the road.";
    } else if (s.phase === "dependencies") {
      headline = "Preparing dependencies.";
      caption = "Getting your compiler’s dependencies ready for the ride.";
    } else if (s.phase === "building") {
      headline = "Building your compiler.";
      caption = "Warming up the wheels. The first stretch is just ahead.";
    }
    el("ride-headline").textContent = headline;
    el("ride-caption").textContent = caption;
    el("ride-sign-title").textContent = queued
      ? "NEXT UP"
      : done
        ? accepted
          ? "ALL PASSED"
          : label(s.status).toUpperCase()
        : "CHECKPOINT";
    el("ride-sign-value").textContent = queued
      ? "YOUR TURN →"
      : `${number(s.completed)} / ${number(s.total)}`;
    el("ride-percent").textContent = `${progress}%`;
    el("ride-progress").setAttribute("aria-valuenow", progress);
    el("ride-progress").setAttribute(
      "aria-valuetext",
      `${s.completed} of ${s.total} tests completed, ${s.passed} passed`,
    );
    el("ride-progress-fill").style.width = `${progress}%`;
    const brief = s.optimization_score
      ? `Optimization score ${scoreText(s.optimization_score.score)}`
      : queued || ["fetching", "dependencies", "building"].includes(s.phase)
        ? phase
        : `${done ? (accepted ? "All tests passed" : label(s.status)) : names[stage]} · ${number(s.completed)} / ${number(s.total)} checked`;
    if (el("ride-brief").textContent !== brief)
      el("ride-brief").textContent = brief;
    el("ride-current-label").textContent = phase;
    el("ride-current-case").textContent =
      !done && s.current_case_id
        ? s.current_case_id
        : queued
          ? "Your compiler is in the queue."
          : s.phase === "fetching"
            ? s.repository_url
            : s.phase === "dependencies"
              ? "Checking the dependency cache and downloading missing packages."
              : s.phase === "building"
                ? "Running the build from config.mk."
                : `${number(s.passed)} of ${number(s.total)} tests passed.`;
    el("ride-stages").innerHTML = counts
      .map((c, i) => {
        const complete = c.total !== null && c.completed === c.total;
        return `<li class="${c.id === stage ? "is-current" : ""} ${complete ? "is-complete" : ""} ${c.failed ? "has-failures" : ""}" ${c.id === stage ? 'aria-current="step"' : ""}><span class="ride-stage-number">${complete ? (c.failed ? "!" : "✓") : `0${i + 1}`}</span><span>${names[c.id]}</span></li>`;
      })
      .join("");
    renderScore(s);
    const lines = [
      ["QUEUE", `Submitted ${date(s.created_at)}`],
      ...(s.started_at
        ? [["START", `Worker started ${date(s.started_at)}`]]
        : []),
      ...(s.commit_sha
        ? [["GIT", `Resolved ${s.git_ref} → ${s.commit_sha.slice(0, 12)}`]]
        : []),
      ...(s.build_log ? [["BUILD", s.build_log]] : []),
      ...s.results.map((r) => [
        r.verdict === "accepted" ? "PASS" : "FAIL",
        `${r.case_id} · ${label(r.verdict)} · ${(r.duration_ms / 1000).toFixed(2)}s${r.stage === "optimization" && r.verdict === "accepted" ? ` · ${number(r.cycles)} cycles` : ""}`,
        [r.message, r.log].filter(Boolean).join("\n"),
        r.case_id,
      ]),
      ...(s.message ? [["JUDGE", s.message]] : []),
      ...(done
        ? [["DONE", `${label(s.status)} · ${s.passed} / ${s.total} passed`]]
        : [["NOW", phase]]),
    ];
    const log = el("ride-log");
    const expanded = new Set(
      [...log.querySelectorAll("details[open]")].map((d) => d.dataset.case),
    );
    const logHTML = lines
      .map(
        ([kind, message, detail, caseId]) =>
          `<div class="ride-log-line"><span class="log-${kind.toLowerCase()}">${kind}</span><div><p>${escapeHTML(message)}</p>${detail ? `<details data-case="${escapeHTML(caseId)}" ${expanded.has(caseId) ? "open" : ""}><summary>Output</summary><pre>${escapeHTML(detail)}</pre></details>` : ""}</div></div>`,
      )
      .join("");
    if (log.innerHTML !== logHTML) {
      log.innerHTML = logHTML;
      body.scrollTop = atBottom ? body.scrollHeight : scrollTop;
      if (s.status === "build_error" && previousStatus !== "build_error") {
        const build = log
          .querySelector(".log-build")
          ?.closest(".ride-log-line");
        if (build)
          body.scrollTop +=
            build.getBoundingClientRect().top -
            body.getBoundingClientRect().top;
      }
    }
    if (
      revealScore ||
      (done && !previousStatus && s.status !== "build_error") ||
      (accepted &&
        (s.suite || s.stage) === "optimization" &&
        previousStatus !== "accepted")
    )
      body.scrollTop = 0;
    // Board once when the worker picks up the run; polling and completion never replay it.
    if (
      s.status === "running" &&
      ["", "queued"].includes(previousStatus) &&
      !motion.matches
    )
      el("ride-scene").classList.add("is-boarding");
    previousStatus = s.status;
    syncMotion();
    scheduleScroll();
  }

  el("ride-peek").onclick = () => {
    if (narrow.matches && !el("ride-sticky").classList.contains("is-detailed"))
      el("ride-live").scrollIntoView({
        block: "start",
        behavior: motion.matches ? "instant" : "smooth",
      });
    else
      window.scrollTo({
        top:
          window.scrollY +
          el("ride-runway").getBoundingClientRect().top +
          (el("ride-sticky").classList.contains("is-detailed")
            ? 0
            : revealDistance),
        behavior: motion.matches ? "instant" : "smooth",
      });
  };
  window.addEventListener("scroll", scheduleScroll, { passive: true });
  window.addEventListener("resize", scheduleScroll, { passive: true });
  document.addEventListener("visibilitychange", syncMotion);
  motion.addEventListener("change", syncMotion);
  narrow.addEventListener("change", scheduleScroll);
  return { activate, reset, update, error };
})();
