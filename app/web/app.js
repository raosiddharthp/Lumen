(function () {
  "use strict";

  const SAMPLES = [
    {
      title: "Breast cancer, stage I, in remission",
      notes: "Applicant: 44-year-old accountant requesting EUR 500,000 life cover. Medical history: breast cancer, stage I, treated with lumpectomy and radiotherapy; treatment completed in March 2020. Annual surveillance mammograms since then have all been clear and there has been no recurrence. Blood pressure 126/80, no medication. No other conditions."
    }
  ];
  const MIN_CHARS = 20;

  const $ = (id) => document.getElementById(id);
  const notes = $("notes");
  const count = $("count");
  const runBtn = $("run");
  const loadBtn = $("load");
  const sampleSel = $("sample");
  const progress = $("progress");
  const result = $("result");
  const warmChip = $("warm");
  let busy = false;
  let timer = null;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  SAMPLES.forEach((s, i) => {
    const option = el("option", "", s.title);
    option.value = String(i);
    sampleSel.appendChild(option);
  });

  function refresh() {
    count.textContent = notes.value.length + " / 4000";
    runBtn.disabled = busy || notes.value.trim().length < MIN_CHARS;
  }

  function setChip(text, tone) {
    warmChip.textContent = text;
    warmChip.className = "chip" + (tone ? " " + tone : "");
  }

  function warmUp() {
    fetch("/api/warm", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        const agents = data.agents || {};
        const names = Object.keys(agents);
        const ready = names.length > 0 && names.every((n) => agents[n] === 200);
        if (ready) setChip("agents: ready", "teal");
        else setChip("agents: waking up", "amber");
      })
      .catch(() => setChip("agents: unreachable", "coral"));
  }

  function showProgress(seconds) {
    progress.hidden = false;
    progress.textContent = "";
    const box = el("div", "callout amber");
    box.appendChild(el("div", "callout-label", "Running"));
    box.appendChild(el("div", "callout-body",
      seconds + " s elapsed. Research, the applicability check, the rating engine, drafting and the grounding check run in order. A first run after a quiet period wakes three services and can take about a minute."));
    progress.appendChild(box);
  }

  function showError(message) {
    result.hidden = false;
    result.textContent = "";
    const box = el("div", "callout coral");
    box.appendChild(el("div", "callout-label", "The case did not complete"));
    box.appendChild(el("div", "callout-body", message));
    result.appendChild(box);
  }

  function describeError(status, data) {
    if (status === 422) return "The notes must be between " + MIN_CHARS + " and 4000 characters.";
    if (status === 502) return "The run failed on the server and nothing was recorded as decided. Reference: " + (data.case_id || "none") + ".";
    return "Unexpected response (" + status + "). Please try again.";
  }

  function heading(num, title) {
    const h = el("h2", "section-heading");
    h.appendChild(el("span", "section-num", num));
    h.appendChild(document.createTextNode(" " + title));
    return h;
  }

  function stat(value, label, tone) {
    const cell = el("div", "stat-cell");
    cell.appendChild(el("div", "stat-value " + tone, value));
    cell.appendChild(el("div", "stat-label", label));
    return cell;
  }

  function renderCase(doc) {
    const ref = doc.referral || {};
    const evidence = doc.evidence || {};
    result.textContent = "";
    result.hidden = false;
    result.appendChild(heading("02", "Result"));

    const grid = el("div", "stat-grid");
    grid.appendChild(stat("Tier " + ref.tier, "Referral: " + (ref.signers || []).join(" + "), ref.tier === 1 ? "teal" : "coral"));
    grid.appendChild(stat(String((doc.draft || []).length), "Draft sentences, each cited", "amber"));
    grid.appendChild(stat(String((evidence.verified || []).length), "Evidence passages verified", "purple"));
    grid.appendChild(stat(String(doc.grounding), "Grounding check", doc.grounding === "passed" ? "teal" : "coral"));
    result.appendChild(grid);

    const box = el("div", "callout teal");
    box.appendChild(el("div", "callout-label", "Case record"));
    const body = el("div", "callout-body");
    body.appendChild(document.createTextNode("Case "));
    body.appendChild(el("code", "", doc.case_id));
    body.appendChild(document.createTextNode(" is " + doc.status.replace("_", " ") + ". Nothing is decided until a named human signs."));
    box.appendChild(body);
    result.appendChild(box);
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function runCase() {
    if (busy) return;
    busy = true;
    refresh();
    result.hidden = true;
    const started = Date.now();
    showProgress(0);
    timer = setInterval(() => showProgress(Math.round((Date.now() - started) / 1000)), 1000);

    fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: notes.value.trim() })
    })
      .then((res) => res.json().then((data) => ({ res, data })))
      .then(({ res, data }) => {
        if (!res.ok) throw new Error(describeError(res.status, data));
        renderCase(data);
      })
      .catch((err) => showError(err.message || "The request failed. Please try again."))
      .finally(() => {
        clearInterval(timer);
        progress.hidden = true;
        busy = false;
        refresh();
      });
  }

  loadBtn.addEventListener("click", () => {
    notes.value = SAMPLES[Number(sampleSel.value)].notes;
    refresh();
  });
  notes.addEventListener("input", refresh);
  runBtn.addEventListener("click", runCase);

  refresh();
  warmUp();
})();
