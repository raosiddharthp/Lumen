(function () {
  "use strict";

  const SAMPLES = [
    {
      title: "Breast cancer, stage I, in remission",
      notes: "Applicant: 44-year-old accountant requesting EUR 500,000 life cover. Medical history: breast cancer, stage I, treated with lumpectomy and radiotherapy; treatment completed in March 2020. Annual surveillance mammograms since then have all been clear and there has been no recurrence. Blood pressure 126/80, no medication. No other conditions."
    }
  ];
  const MIN_CHARS = 20;
  const ROLES = {
    senior_underwriter: "Senior underwriter",
    cosigner_cmo_or_cuo: "Co-signer (CMO or CUO)"
  };
  const STATUS_TEXT = {
    awaiting_signoff: "awaiting sign-off",
    signed_off: "signed off",
    declined: "declined"
  };
  const STATUS_NOTE = {
    awaiting_signoff: "Nothing is decided until a named human signs.",
    signed_off: "All required signers approved.",
    declined: "A signer declined, so the case is closed without approval."
  };

  const $ = (id) => document.getElementById(id);
  const notes = $("notes");
  const count = $("count");
  const runBtn = $("run");
  const loadBtn = $("load");
  const sampleSel = $("sample");
  const progress = $("progress");
  const result = $("result");
  const warmChip = $("warm");
  const leftChip = $("left");
  const recordedBtn = $("recorded");
  let busy = false;
  let timer = null;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function roleName(role) {
    return ROLES[role] || String(role).replace(/_/g, " ");
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

  function loadLimits() {
    fetch("/api/limits")
      .then((r) => r.json())
      .then((data) => {
        leftChip.title = data.message || "";
        if (data.left === null || data.left === undefined) {
          leftChip.textContent = "live runs: no limit set";
          leftChip.className = "chip";
        } else if (!data.live) {
          leftChip.textContent = "live runs: none left";
          leftChip.className = "chip coral";
        } else {
          leftChip.textContent = "live runs left: " + data.left;
          leftChip.className = "chip " + (data.left > 1 ? "teal" : "amber");
        }
      })
      .catch(() => {
        leftChip.textContent = "live runs: unknown";
        leftChip.className = "chip amber";
      });
  }

  function recordedBanner(info, why) {
    const text = (why ? why + " " : "") +
      "This is a recorded run from " + info.at + ", produced by the same pipeline as a live run. Sign-off is switched off on it.";
    return callout("amber", "Recorded run", text);
  }

  function showRecorded(why) {
    return fetch("/api/recorded")
      .then((res) => {
        if (!res.ok) throw new Error("no recording");
        return res.json();
      })
      .then((data) => renderCase(data, true, why))
      .catch(() => showError((why ? why + " " : "") + "The recorded run could not be loaded."));
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

  function callout(tone, label, text) {
    const box = el("div", "callout " + tone);
    box.appendChild(el("div", "callout-label", label));
    box.appendChild(el("div", "callout-body", text));
    return box;
  }

  function renderSummary(doc) {
    const ref = doc.referral || {};
    const evidence = doc.evidence || {};
    const block = el("div", "block");
    block.appendChild(heading("02", "Result"));

    const grid = el("div", "stat-grid");
    grid.appendChild(stat("Tier " + ref.tier, "Referral: " + (ref.signers || []).map(roleName).join(" + "), ref.tier === 1 ? "teal" : "coral"));
    grid.appendChild(stat(String((doc.draft || []).length), "Draft sentences, each cited", "amber"));
    grid.appendChild(stat(String((evidence.verified || []).length), "Evidence passages verified", "purple"));
    grid.appendChild(stat(String(doc.grounding), "Grounding check", doc.grounding === "passed" ? "teal" : "coral"));
    block.appendChild(grid);

    const tone = doc.status === "signed_off" ? "teal" : doc.status === "declined" ? "coral" : "amber";
    const box = el("div", "callout " + tone);
    box.appendChild(el("div", "callout-label", "Case record"));
    const body = el("div", "callout-body");
    body.appendChild(document.createTextNode("Case "));
    body.appendChild(el("code", "", doc.case_id));
    body.appendChild(document.createTextNode(" is " + (STATUS_TEXT[doc.status] || doc.status) + ". " + (STATUS_NOTE[doc.status] || "")));
    box.appendChild(body);
    block.appendChild(box);
    return block;
  }

  function renderRating(doc) {
    const block = el("div", "block");
    block.appendChild(heading("03", "Rating and referral"));
    const rating = doc.rating;
    if (!rating) {
      block.appendChild(callout("coral", "No rating", "The rating engine produced no rating for this case, so it was sent to the highest referral tier."));
    } else {
      const table = el("table", "comp-table");
      const tbody = el("tbody");
      const rows = [
        ["Status", rating.status],
        ["Loading", rating.loading_pct === null || rating.loading_pct === undefined ? "none" : rating.loading_pct + "%"],
        ["Rules applied", (rating.rule_ids || []).join(", ") || "none"],
        ["Guidance", (rating.guidance_refs || []).join(", ") || "none"],
        ["Engine version", rating.methodology_version]
      ];
      rows.forEach((row) => {
        const tr = el("tr");
        tr.appendChild(el("td", "", row[0]));
        tr.appendChild(el("td", "", String(row[1])));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      block.appendChild(table);
      (rating.notes || []).forEach((n) => block.appendChild(el("p", "body-text", String(n))));
    }
    const ref = doc.referral || {};
    const reasons = (ref.reasons || []).map((r) => (typeof r === "string" ? r : JSON.stringify(r)));
    if (reasons.length) {
      block.appendChild(callout("amber", "Mandatory referral rules triggered", reasons.join(", ") + ". Required signers: " + (ref.signers || []).map(roleName).join(" and ") + "."));
    } else {
      block.appendChild(callout("teal", "Referral", "No mandatory referral rule was triggered. Required signer: " + (ref.signers || []).map(roleName).join(" and ") + "."));
    }
    return block;
  }

  function showPassage(panel, cid, passage) {
    panel.textContent = "";
    const label = (passage ? passage.title : "Passage unavailable") + " · " + cid;
    panel.appendChild(el("div", "callout-label", label));
    panel.appendChild(el("div", "passage-text", passage ? passage.text : "The text of this passage is not available."));
    panel.hidden = false;
  }

  function renderDraft(doc, passages) {
    const block = el("div", "block");
    block.appendChild(heading("04", "Draft summary"));
    const sentences = doc.draft || [];
    if (!sentences.length) {
      block.appendChild(callout("amber", "No narrative", "No draft passed the grounding check, so none is shown. The case went to the highest referral tier with the rating and evidence only."));
      return block;
    }
    block.appendChild(el("p", "section-kicker", "Every sentence was checked against the passages it cites. Select a citation to read the passage."));
    sentences.forEach((s) => {
      const row = el("div", "sentence");
      row.appendChild(el("p", "sentence-text", s.text));
      const cites = el("div", "cites");
      const panel = el("div", "passage");
      panel.hidden = true;
      (s.cites || []).forEach((cid) => {
        const btn = el("button", "chip cite", cid);
        btn.type = "button";
        btn.addEventListener("click", () => {
          const wasOpen = btn.classList.contains("active");
          cites.querySelectorAll(".cite").forEach((b) => b.classList.remove("active"));
          if (wasOpen) {
            panel.hidden = true;
            return;
          }
          btn.classList.add("active");
          showPassage(panel, cid, passages[cid]);
        });
        cites.appendChild(btn);
      });
      cites.appendChild(el("span", "chip " + (s.verdict === "supported" ? "teal" : "coral"), s.verdict || "unchecked"));
      row.appendChild(cites);
      row.appendChild(panel);
      block.appendChild(row);
    });
    return block;
  }

  function evidenceGroup(ids, passages, label, dropped) {
    const group = el("div");
    group.appendChild(el("div", "figure-label", label));
    if (!ids.length) {
      group.appendChild(el("p", "body-text", "None."));
      return group;
    }
    ids.forEach((id) => {
      const passage = passages[id];
      const details = el("details", "evidence" + (dropped ? " dropped" : ""));
      const summary = el("summary");
      summary.appendChild(el("span", "chip " + (dropped ? "" : "teal"), id));
      summary.appendChild(document.createTextNode(passage ? passage.title : ""));
      details.appendChild(summary);
      details.appendChild(el("p", "passage-text", passage ? passage.text : "The text of this passage is not available."));
      group.appendChild(details);
    });
    return group;
  }

  function renderEvidence(doc, passages) {
    const evidence = doc.evidence || {};
    const block = el("div", "block");
    block.appendChild(heading("05", "Evidence"));
    block.appendChild(evidenceGroup(evidence.verified || [], passages, "Verified for this case", false));
    block.appendChild(evidenceGroup(evidence.dropped || [], passages, "Retrieved, then removed by the applicability check", true));
    return block;
  }

  function signoffLog(signoffs) {
    const table = el("table", "comp-table");
    const thead = el("thead");
    const head = el("tr");
    ["Role", "Name", "Decision", "When", "Reason"].forEach((h) => head.appendChild(el("th", "", h)));
    thead.appendChild(head);
    table.appendChild(thead);
    const tbody = el("tbody");
    signoffs.forEach((s) => {
      const tr = el("tr");
      [roleName(s.role), s.name, s.decision, new Date(s.at).toLocaleString(), s.reason || "—"].forEach((v) => tr.appendChild(el("td", "", v)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function field(label, control) {
    const wrap = el("div", "field");
    const lab = el("label", "", label);
    control.id = "f-" + label.toLowerCase().replace(/[^a-z]+/g, "-");
    lab.htmlFor = control.id;
    wrap.appendChild(lab);
    wrap.appendChild(control);
    return wrap;
  }

  function signoffError(status, data) {
    if (status === 404) return "Case not found.";
    if (status === 409) return data.error === "closed" ? "This case is already closed." : "That role has already signed.";
    if (status === 422 && data.message) return data.message.charAt(0).toUpperCase() + data.message.slice(1) + ".";
    if (status === 422) return "Please check the fields and try again.";
    return "The sign-off could not be recorded. Nothing was changed.";
  }

  function signoffForm(doc, remaining) {
    const form = el("form", "signoff-form");
    const roleSel = el("select");
    remaining.forEach((r) => {
      const option = el("option", "", roleName(r));
      option.value = r;
      roleSel.appendChild(option);
    });
    const nameInput = el("input");
    nameInput.type = "text";
    nameInput.maxLength = 80;
    nameInput.required = true;
    nameInput.autocomplete = "off";
    nameInput.placeholder = "Your name (not verified)";
    const decisionSel = el("select");
    [["approve", "Approve"], ["decline", "Decline"]].forEach((pair) => {
      const option = el("option", "", pair[1]);
      option.value = pair[0];
      decisionSel.appendChild(option);
    });
    const reason = el("textarea");
    reason.rows = 2;
    reason.maxLength = 500;
    reason.placeholder = "Required if you decline";

    const row = el("div", "field-row");
    row.appendChild(field("Signing as", roleSel));
    row.appendChild(field("Name", nameInput));
    row.appendChild(field("Decision", decisionSel));
    form.appendChild(row);
    form.appendChild(field("Reason", reason));

    const error = el("div", "form-error");
    const actions = el("div", "form-actions");
    const submit = el("button", "btn primary", "Record sign-off");
    submit.type = "submit";
    actions.appendChild(submit);
    actions.appendChild(el("span", "form-note", "Demo only: there is no sign-in, so the name is recorded as typed."));
    form.appendChild(actions);
    form.appendChild(error);

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      error.textContent = "";
      submit.disabled = true;
      fetch("/api/cases/" + encodeURIComponent(doc.case_id) + "/signoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role: roleSel.value,
          name: nameInput.value,
          decision: decisionSel.value,
          reason: reason.value
        })
      })
        .then((res) => res.json().then((data) => ({ res, data })))
        .then(({ res, data }) => {
          if (!res.ok) throw new Error(signoffError(res.status, data));
          renderCase(data, false);
        })
        .catch((err) => {
          error.textContent = err.message;
          submit.disabled = false;
        });
    });
    return form;
  }

  function renderSignoff(doc) {
    const block = el("div", "block");
    block.appendChild(heading("06", "Human sign-off"));
    if (doc.recorded) {
      block.appendChild(callout("amber", "Sign-off is off", "This is a recorded run, so nothing here can be signed. Run a live case to try the sign-off."));
      return block;
    }
    const signed = doc.signoffs || [];
    const signers = (doc.referral && doc.referral.signers) || [];
    if (signed.length) block.appendChild(signoffLog(signed));
    if (doc.status === "signed_off") {
      block.appendChild(callout("teal", "Signed off", "Every required signer approved. The decision and each signature are in the event log."));
    } else if (doc.status === "declined") {
      block.appendChild(callout("coral", "Declined", "A signer declined, so the case is closed without approval."));
    } else {
      const remaining = signers.filter((r) => !signed.some((s) => s.role === r));
      block.appendChild(signoffForm(doc, remaining));
    }
    return block;
  }

  function renderCase(doc, scroll, why) {
    const passages = doc.passages || {};
    result.textContent = "";
    result.hidden = false;
    if (doc.recorded) result.appendChild(recordedBanner(doc.recorded, why));
    result.appendChild(renderSummary(doc));
    result.appendChild(renderRating(doc));
    result.appendChild(renderDraft(doc, passages));
    result.appendChild(renderEvidence(doc, passages));
    result.appendChild(renderSignoff(doc));
    if (scroll) result.scrollIntoView({ behavior: "smooth", block: "start" });
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
        if (res.ok) {
          renderCase(data, true);
          return;
        }
        if (res.status === 429) return showRecorded(data.message || "Live runs are not available right now.");
        if (res.status === 502) return showRecorded("The live run failed on the server.");
        throw new Error(describeError(res.status, data));
      })
      .catch((err) => {
        if (err instanceof TypeError || err.name === "SyntaxError") {
          return showRecorded("The live service could not be reached.");
        }
        showError(err.message || "The request failed. Please try again.");
      })
      .finally(() => {
        clearInterval(timer);
        progress.hidden = true;
        busy = false;
        refresh();
        loadLimits();
      });
  }

  loadBtn.addEventListener("click", () => {
    notes.value = SAMPLES[Number(sampleSel.value)].notes;
    refresh();
  });
  notes.addEventListener("input", refresh);
  runBtn.addEventListener("click", runCase);
  recordedBtn.addEventListener("click", () => showRecorded(""));

  refresh();
  warmUp();
  loadLimits();
})();
