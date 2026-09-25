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
  const themes = {
    semantic: [
      "THE COAST",
      "Taking the\nscenic route.",
      "Checking meaning, one little program at a time.",
      "Sea breeze, clear skies, sound semantics.",
    ],
    ir: [
      "THE WOODLANDS",
      "Into the\ngreen.",
      "Following your LLVM IR through the trees.",
      "Fresh air. A fresh intermediate representation.",
    ],
    codegen: [
      "THE HIGH PASS",
      "On to\nhigher ground.",
      "Putting your generated assembly through its paces.",
      "A steady climb from code to instructions.",
    ],
    optimization: [
      "THE NIGHT RUN",
      "Make every\ncycle count.",
      "Chasing fewer cycles under a sky full of stars.",
      "One last stretch. A little more speed.",
    ],
  };
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const narrow = matchMedia("(max-width: 800px)");
  let submission = null;
  let mounted = false;
  let active = false;
  let visible = true;
  let paused = false;
  let scrollFrame = 0;
  let resultLimit = 50;
  let reportKey = "";
  let previousStatus = "";

  function mountArt() {
    if (mounted) return;
    mounted = true;
    el("ride-art").innerHTML =
      `<svg viewBox="0 0 1200 520" xmlns="http://www.w3.org/2000/svg" focusable="false">
      <defs>
        <pattern id="ride-dashes" width="150" height="10" patternUnits="userSpaceOnUse"><path d="M15 5h62" stroke="var(--road-mark)" stroke-width="3" stroke-linecap="round"/></pattern>
        <g id="ride-tree"><path d="M0 0v88" stroke="#526b55" stroke-width="7"/><path d="M-43 34 0-48 43 34ZM-35 3 0-67 35 3Z" fill="var(--trees)"/></g>
        <g id="ride-palm"><path d="M0 0Q15-61 5-112" stroke="#9d7650" stroke-width="10" fill="none"/><path d="M5-110Q-51-157-76-98Q-34-126 5-110Q-6-171 36-175Q18-140 5-110Q53-161 91-116Q48-130 5-110Q48-116 64-70Q30-98 5-110Q-40-123-43-70Q-21-103 5-110" fill="#508e76"/></g>
        <g id="ride-cloud" fill="var(--cloud)"><path d="M0 20Q-5 0 17 0Q19-28 46-22Q70-21 72 0Q95-5 99 20Z"/></g>
      </defs>
      <g class="ride-stars" fill="#e8dbaf"><circle cx="134" cy="128" r="2"/><circle cx="300" cy="64" r="3"/><circle cx="460" cy="147" r="2"/><circle cx="640" cy="89" r="2"/><circle cx="846" cy="47" r="3"/><circle cx="1095" cy="168" r="2"/><path d="m1035 79 2 7 7 2-7 2-2 7-2-7-7-2 7-2Z"/><path d="m550 40 2 7 7 2-7 2-2 7-2-7-7-2 7-2Z"/></g>
      <circle class="ride-sun-halo" cx="962" cy="130" r="68" fill="var(--sun)" opacity=".15"/>
      <circle cx="962" cy="130" r="43" fill="var(--sun)"/>
      <g class="ride-clouds"><use href="#ride-cloud" x="685" y="123"/><use href="#ride-cloud" x="1095" y="199" transform="translate(328,59) scale(.7)"/><use href="#ride-cloud" x="300" y="182" transform="translate(50,0) scale(.65)"/></g>
      <g class="ride-distant"><path d="M-120 290Q40 205 165 270T430 235T710 254T970 230T1280 268V410H-120Z" fill="var(--hill-back)"/>
      <path d="M-80 345Q58 251 215 321T498 308T740 305T1016 302T1300 315V440H-80Z" fill="var(--hill-front)"/></g>
      <g class="ride-mountains"><path d="m350 360 220-221 128 134 160-202 252 289Z" fill="var(--hill-back)"/><path d="m500 210 70-71 57 60-44-12-23 30-18-26ZM802 143l56-72 83 94-65-22-21 14-21-24Z" fill="#e8ede5"/><path d="m30 375 232-194 198 194 221-137 286 137Z" fill="var(--hill-front)"/></g>
      <path class="ride-water" d="M0 330Q280 322 540 340T1200 324V413H0Z" fill="var(--water)"/>
      <g class="ride-waves" stroke="#fff" stroke-width="2" opacity=".5"><path d="M20 352h108m46 15h63m263-21h86m80 26h121m102-28h49m159 20h96M64 388h75m245-9h116m363 16h87"/></g>
      <g class="ride-scenery">
        <g class="ride-palms"><use href="#ride-palm" x="105" y="376"/><use href="#ride-palm" x="1137" y="360" transform="translate(258,79) scale(.8)"/></g>
        <g class="ride-trees"><use href="#ride-tree" x="94" y="318"/><use href="#ride-tree" x="190" y="332"/><use href="#ride-tree" x="773" y="314"/><use href="#ride-tree" x="1075" y="300"/></g>
        <g class="ride-rocks" fill="var(--hill-back)"><path d="m103 399 20-35 34-8 32 43Zm963 4 30-48 39 7 22 41Z"/></g>
      </g>
      <path d="M0 399Q280 384 600 402T1200 395V520H0Z" fill="var(--ground)"/>
      <path d="M0 424H1200V483H0Z" fill="var(--road)"/>
      <path d="M0 424H1200" stroke="var(--road-edge)" stroke-width="3"/>
      <g class="ride-road-motion"><rect x="-150" y="454" width="1500" height="10" fill="url(#ride-dashes)"/></g>
      <g class="ride-roadside" transform="translate(865,285)"><path d="M0 58v79m149-79v79" stroke="var(--sign-post)" stroke-width="6"/><rect width="163" height="73" x="-7" y="-7" rx="8" fill="var(--sign-post)"/><rect width="151" height="61" x="-1" y="-1" rx="5" fill="var(--sign)" stroke="var(--sign-ink)" stroke-opacity=".35"/>
        <text id="ride-sign-title" x="74" y="23" text-anchor="middle" fill="var(--sign-ink)" font-size="12" letter-spacing="2">NEXT UP</text><text id="ride-sign-value" x="74" y="46" text-anchor="middle" fill="var(--sign-ink)" font-size="16" font-weight="600">YOUR TURN →</text>
      </g>
      <g transform="translate(270,264)"><ellipse cx="135" cy="175" rx="136" ry="8" fill="#383d33" opacity=".12"/>
        <g class="ride-board"><path d="M37 151q13 15 30 15h146q22 0 31-15" stroke="#303439" stroke-width="8" stroke-linecap="round" fill="none"/><path d="M51 154h179" stroke="#e9b950" stroke-width="5" stroke-linecap="round"/><path d="M85 166v7m114-7v7" stroke="#545967" stroke-width="5"/><g class="ride-wheel"><circle cx="85" cy="177" r="10" fill="#efad51"/><circle cx="85" cy="177" r="4" fill="#404449"/></g><g class="ride-wheel"><circle cx="199" cy="177" r="10" fill="#efad51"/><circle cx="199" cy="177" r="4" fill="#404449"/></g></g>
        <g class="ride-crab-position"><g class="ride-crab-bob"><g fill="none" stroke="#c44f17" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="m67 112-24 19 7 16m13-26-12 17 9 9m-3-26-20 15 4 13m167-37 25 19-7 16m-12-26 12 17-9 9m3-26 20 15-4 13"/></g><g id="ride-crab" transform="translate(4,-16) scale(.22)"></g></g></g>
        <g class="ride-speed" stroke="var(--road-edge)" stroke-width="3" stroke-linecap="round"><path d="M-15 103h-35m23 15h-48m47 16h-25"/></g>
      </g>
      <g fill="var(--road-edge)" opacity=".35"><path d="m121 509 6-10 4 10m4 0 7-7 1 7m852 3 4-10 6 10m-824-6h16m876 2h24"/></g>
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
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      syncMotion();
    }).observe(el("ride-scene"));
  }

  function syncMotion() {
    el("ride-scene").classList.toggle(
      "is-moving",
      active && visible && !document.hidden && !paused && !motion.matches,
    );
    el("ride-motion").setAttribute(
      "aria-pressed",
      String(paused || motion.matches),
    );
    el("ride-motion").setAttribute(
      "aria-label",
      motion.matches
        ? "Animation disabled by reduced motion preference"
        : paused
          ? "Play animation"
          : "Pause animation",
    );
    el("ride-motion").innerHTML = motion.matches
      ? "— <span>Motion off</span>"
      : paused
        ? "▷ <span>Play</span>"
        : "Ⅱ <span>Pause</span>";
    el("ride-motion").disabled = motion.matches;
  }

  function scrollLayout() {
    scrollFrame = 0;
    if (!active) return;
    const top = el("ride-runway").getBoundingClientRect().top;
    const amount = narrow.matches
      ? 1
      : Math.min(1, Math.max(0, (16 - top) / 480));
    el("ride-sticky").style.setProperty("--reveal", amount.toFixed(4));
    el("ride-sticky").classList.toggle("is-detailed", amount > 0.85);
    el("ride-live").inert = amount < 0.85;
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
    submission = null;
    reportKey = "";
    resultLimit = 50;
    previousStatus = "";
    el("run-name").textContent = "Loading your run…";
    el("run-meta").textContent = "";
    el("run-status").textContent = "";
    el("run-error").hidden = true;
    el("run-content").hidden = true;
    el("cancel-submission").hidden = true;
    el("detail").replaceChildren();
    el("ride-log").replaceChildren();
    el("run-result-filter").value = "all";
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
    if (s.phase === "building") return "Building your compiler";
    if (s.phase === "testing" || s.results.length)
      return `Testing · ${names[stage]}`;
    return "Preparing your compiler";
  }
  function update(s) {
    mountArt();
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
    const theme = themes[stage];
    el("run-name").textContent = s.name;
    el("run-meta").textContent =
      `${languageName(s.language)} · ${s.id.slice(0, 8)}`;
    el("run-status").innerHTML = badge(s.status);
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
        ? "Ferris resting with one side of his feet on a skateboard, waiting for a worker."
        : done
          ? `Ferris has stepped off his skateboard, ${accepted ? "claws resting happily" : "waving his claws encouragingly"}. ${label(s.status)}.`
          : `Ferris riding a skateboard through ${theme[0].toLowerCase()}. ${s.completed} of ${s.total} tests completed.`,
    );
    el("ride-location").textContent =
      `${theme[0]} · ${names[stage].toUpperCase()}`;
    el("ride-scene-index").textContent =
      `0${stages.indexOf(stage) + 1} / 0${counts.length}`;
    let headline = theme[1];
    let caption = theme[2];
    if (queued) {
      headline = "Good things\ntake a moment.";
      caption =
        "Ferris is saving your spot. We’ll roll as soon as a worker is ready.";
    } else if (done) {
      headline = accepted
        ? "Well done.\nYou passed!"
        : s.status === "cancelled"
          ? "A pause in\nthe journey."
          : [
                "system_error",
                "source_error",
                "build_error",
                "time_limit",
              ].includes(s.status)
            ? "A bump in\nthe road."
            : "Next time,\nyou’ve got this.";
      const endings = {
        failed:
          "Let’s do better next time. Your results below show where to start.",
        cancelled:
          "The run was cancelled. Ferris will be here when you’re ready for another ride.",
        build_error:
          "Your compiler couldn’t finish building. Check the build diagnostics, then give it another go.",
        source_error:
          "We couldn’t fetch your source. Check the repository details in the diagnostics below.",
        system_error:
          "The judge couldn’t complete this run. Check the system details below before trying again.",
        time_limit:
          "This run reached its time limit. Review the results below before your next ride.",
      };
      caption = accepted
        ? "Every check passed. Time to step off the board and enjoy the view."
        : endings[s.status] ||
          "Check the diagnostics below before your next ride.";
    } else if (s.phase === "fetching" || s.phase === "building") {
      headline = "Getting ready\nto roll.";
      caption =
        s.phase === "fetching"
          ? "Picking up your code before we hit the road."
          : "Building your compiler. The first stretch is just ahead.";
    }
    el("ride-headline").textContent = headline;
    el("ride-caption").textContent = caption;
    el("ride-weather").textContent = queued
      ? "A little sea breeze. A little patience."
      : done
        ? "Every run is a step forward."
        : theme[3];
    el("ride-sign-title").textContent = queued
      ? "NEXT UP"
      : done
        ? "END OF THE RIDE"
        : "CHECKPOINT";
    el("ride-sign-value").textContent = queued
      ? "YOUR TURN →"
      : `${number(s.completed)} / ${number(s.total)}`;
    el("ride-progress-label").textContent = queued
      ? phase
      : `${done ? "Run finished" : phase} · ${number(s.completed)} / ${number(s.total)} checked`;
    el("ride-percent").textContent = `${progress}%`;
    el("ride-progress").setAttribute("aria-valuenow", progress);
    el("ride-progress").setAttribute(
      "aria-valuetext",
      `${s.completed} of ${s.total} tests completed, ${s.passed} passed`,
    );
    el("ride-progress-fill").style.width = `${progress}%`;
    const recent = s.results.at(-1);
    const brief =
      s.message ||
      (done
        ? accepted
          ? `Well done. All ${number(s.total)} tests passed.`
          : `${label(s.status)} · ${number(s.passed)} / ${number(s.total)} tests passed.`
        : s.cancel_requested
          ? "Cancellation requested. Waiting for the worker to stop."
          : s.current_case_id
            ? `Checking ${s.current_case_id}`
            : recent
              ? `${label(recent.verdict)} · ${recent.case_id}`
              : phase);
    if (el("ride-brief").textContent !== brief)
      el("ride-brief").textContent = brief;
    el("ride-passed").textContent = `${number(s.passed)} passed`;
    el("ride-live-status").textContent = done
      ? "Run complete"
      : "Updates automatically";
    el("ride-current-label").textContent = phase;
    el("ride-current-case").textContent =
      !done && s.current_case_id
        ? s.current_case_id
        : s.message ||
          (queued
            ? "Your compiler is in the queue."
            : s.phase === "fetching"
              ? s.repository_url
              : s.phase === "building"
                ? "Running the build from config.mk."
                : `${number(s.passed)} of ${number(s.total)} tests passed.`);
    el("ride-stages").innerHTML = counts
      .map((c, i) => {
        const complete = c.total !== null && c.completed === c.total;
        return `<li class="${c.id === stage ? "is-current" : ""} ${complete ? "is-complete" : ""} ${c.failed ? "has-failures" : ""}" ${c.id === stage ? 'aria-current="step"' : ""}><span class="ride-stage-number">${complete ? (c.failed ? "!" : "✓") : `0${i + 1}`}</span><span>${names[c.id]}</span></li>`;
      })
      .join("");
    el("ride-stage-summary").innerHTML = counts
      .map(
        (c) =>
          `<div><span>${names[c.id]}</span><strong class="${c.failed ? "has-failures" : ""}">${c.completed ? `${c.passed} / ${c.total ?? "?"} passed` : c.id === stage && !queued && !done ? (s.phase === "testing" ? "Running" : "Up next") : done ? "Not run" : "Waiting"}</strong></div>`,
      )
      .join("");
    const lines = [
      ["QUEUE", `Submitted ${date(s.created_at)}`],
      ...(s.started_at
        ? [["START", `Worker started ${date(s.started_at)}`]]
        : []),
      ...(s.commit_sha
        ? [["GIT", `Resolved ${s.git_ref} → ${s.commit_sha.slice(0, 12)}`]]
        : []),
      ...(s.build_log
        ? [["BUILD", s.build_log.trim().split("\n").slice(-2).join("\n")]]
        : []),
      ...s.results
        .slice(-5)
        .map((r) => [
          r.verdict === "accepted" ? "PASS" : "FAIL",
          `${r.case_id} · ${(r.duration_ms / 1000).toFixed(2)}s`,
        ]),
      ...(s.message ? [["JUDGE", s.message]] : []),
      ...(done
        ? [["DONE", `${label(s.status)} · ${s.passed} / ${s.total} passed`]]
        : [["NOW", phase]]),
    ];
    const log = el("ride-log");
    const atBottom = log.scrollHeight - log.clientHeight - log.scrollTop < 30;
    const logHTML = lines
      .map(
        ([kind, message]) =>
          `<div class="ride-log-line"><span class="log-${kind.toLowerCase()}">${kind}</span><p>${escapeHTML(message)}</p></div>`,
      )
      .join("");
    if (log.innerHTML !== logHTML) {
      log.innerHTML = logHTML;
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
    if (done && previousStatus === "running") {
      el("ride-scene").classList.remove("just-finished");
      void el("ride-scene").offsetWidth;
      el("ride-scene").classList.add("just-finished");
    } else if (!done) el("ride-scene").classList.remove("just-finished");
    previousStatus = s.status;
    renderReport();
    syncMotion();
    scheduleScroll();
  }

  function renderReport() {
    if (!submission) return;
    const s = submission;
    const filter = el("run-result-filter").value;
    // Avoid replacing expanded diagnostics on polls where only the current test changes.
    const key = JSON.stringify([
      s.results,
      s.build_log,
      s.message,
      s.optimization_score,
      s.status,
      s.commit_sha,
      filter,
      resultLimit,
    ]);
    if (key === reportKey) return;
    reportKey = key;
    const expanded = new Set(
      [...el("detail").querySelectorAll("details[open]")].map(
        (d) => d.dataset.key,
      ),
    );
    const scrollPositions = [...el("detail").querySelectorAll("pre")].map(
      (p) => p.scrollTop,
    );
    const counts = stageData(s);
    el("run-report-count").textContent =
      `${number(s.passed)} passed · ${number(s.completed - s.passed)} failed · ${number(Math.max(0, s.total - s.completed))} remaining`;
    el("run-stage-cards").innerHTML = counts
      .map(
        (c, i) =>
          `<article><span class="eyebrow">0${i + 1} / ${names[c.id]}</span><strong>${c.passed}<span> / ${c.total ?? "—"}</span></strong><p>${c.failed ? `${c.failed} failed · ` : ""}${c.total && c.completed === c.total ? "Stage complete" : terminal(s.status) ? (c.completed ? "Stage incomplete" : "Not run") : `${c.completed} checked`}</p></article>`,
      )
      .join("");
    const filtered = s.results.filter(
      (r) =>
        filter === "all" ||
        (filter === "failures" ? r.verdict !== "accepted" : r.stage === filter),
    );
    el("run-result-count").textContent =
      `${number(filtered.length)} results${filtered.length > resultLimit ? ` · showing ${resultLimit}` : ""}`;
    el("detail").innerHTML =
      `<p class="source-info">${escapeHTML(s.repository_url || "Legacy archive submission")}<br>Ref: <code>${escapeHTML(s.git_ref || "—")}</code> · Commit: <code>${escapeHTML(s.commit_sha || "Waiting for Git fetch")}</code></p>
      ${s.optimization_score ? `<div class="optimization-score"><strong>${scoreText(s.optimization_score.score)}</strong><span>Optimization score · lower is better</span><a href="#leaderboard">View leaderboard ↗</a></div>` : ""}
      ${
        filtered.length
          ? `<div class="table-scroll" tabindex="0" role="region" aria-label="Testcase results"><table><thead><tr><th>TESTCASE</th><th>STAGE</th><th>VERDICT</th><th>ELAPSED</th><th>CYCLES</th></tr></thead><tbody>${filtered
              .slice(0, resultLimit)
              .map(
                (r) =>
                  `<tr><td class="case-name">${escapeHTML(r.case_id)}${r.message ? `<span class="sub-meta">${escapeHTML(r.message)}</span>` : ""}${r.log ? `<details data-key="case-${escapeHTML(r.case_id)}"><summary>Diagnostics</summary><pre tabindex="0">${escapeHTML(r.log)}</pre></details>` : ""}</td><td>${names[r.stage] || escapeHTML(label(r.stage))}</td><td>${badge(r.verdict)}</td><td>${(r.duration_ms / 1000).toFixed(2)}s</td><td>${r.stage === "optimization" && r.verdict === "accepted" ? number(r.cycles) : "—"}</td></tr>`,
              )
              .join("")}</tbody></table></div>`
          : `<p class="run-no-results">${s.results.length ? "No tests match this filter." : terminal(s.status) ? "This run ended before any testcase results were produced." : "The first results will appear here as tests finish."}</p>`
      }
      ${filtered.length > resultLimit ? '<button id="run-more-results" class="button ghost small">Show 50 more results ↓</button>' : ""}
      ${s.message ? `<p class="notice">${escapeHTML(s.message)}</p>` : ""}
      <details data-key="build" ${s.status === "build_error" ? "open" : ""}><summary>Build diagnostics</summary><pre tabindex="0" role="region" aria-label="Build diagnostics output">${escapeHTML(s.build_log || "No build output yet.")}</pre></details>
      ${s.optimization_score ? `<details data-key="score"><summary>Optimization score · testcase ratios</summary>${scoreTable(s.optimization_score.cases)}</details>` : ""}
      <details data-key="json"><summary>Result JSON · all runs and diagnostics</summary><pre tabindex="0" role="region" aria-label="Result JSON output"></pre></details>`;
    for (const d of el("detail").querySelectorAll("details"))
      if (expanded.has(d.dataset.key)) d.open = true;
    const json = el("detail").querySelector('[data-key="json"]');
    const fillJSON = () => {
      if (json.open)
        json.querySelector("pre").textContent = JSON.stringify(
          submission,
          null,
          2,
        );
    };
    json.addEventListener("toggle", fillJSON);
    fillJSON();
    [...el("detail").querySelectorAll("pre")].forEach((p, i) => {
      p.scrollTop = scrollPositions[i] || 0;
    });
    if (el("run-more-results"))
      el("run-more-results").onclick = () => {
        resultLimit += 50;
        renderReport();
      };
  }
  el("run-result-filter").onchange = () => {
    resultLimit = 50;
    renderReport();
  };
  el("ride-motion").onclick = () => {
    paused = !paused;
    syncMotion();
  };
  el("ride-peek").onclick = () => {
    if (narrow.matches)
      el("ride-live").scrollIntoView({
        block: "start",
        behavior: motion.matches ? "instant" : "smooth",
      });
    else
      window.scrollTo({
        top:
          window.scrollY +
          el("ride-runway").getBoundingClientRect().top +
          480 -
          16,
        behavior: motion.matches ? "instant" : "smooth",
      });
  };
  el("ride-all-results").onclick = () =>
    el("run-report").scrollIntoView({
      block: "start",
      behavior: motion.matches ? "instant" : "smooth",
    });
  window.addEventListener("scroll", scheduleScroll, { passive: true });
  window.addEventListener("resize", scheduleScroll, { passive: true });
  document.addEventListener("visibilitychange", syncMotion);
  motion.addEventListener("change", syncMotion);
  narrow.addEventListener("change", scheduleScroll);
  return { activate, reset, update, error };
})();
