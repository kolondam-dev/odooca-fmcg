/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
// Approved popover/inline interaction from the owner-reviewed D1 simulation.
// Values and locked scope are supplied by the caller; no mock master data here.
let instanceNumber = 0;
const htmlText = (text) => String(text).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"})[char]);
const toolbar = () =>
  `<div class="d1-controls">\n      <div class="d1-tools">\n        <button type="button" class="d1-button cursor-interaction" id="d1-period-trigger" data-action="open-period" aria-expanded="false" aria-controls="d1-popover"><i class="fa fa-calendar" aria-hidden="true"></i><span data-period-label></span><span aria-hidden="true">▾</span></button>\n        <button type="button" class="d1-button cursor-interaction" id="d1-compare-trigger" data-action="open-period" aria-expanded="false" aria-controls="d1-popover"><span data-compare-label></span><span aria-hidden="true">▾</span></button>\n        <button type="button" class="d1-button cursor-interaction" id="d1-filter-trigger" data-action="open-filter" aria-expanded="false" aria-controls="d1-popover"><i class="fa fa-filter" aria-hidden="true"></i><span data-filter-label>Filter</span><span aria-hidden="true">▾</span></button>\n        <button type="button" class="d1-button quiet cursor-interaction" data-action="reset">Reset</button>\n        <span class="d1-hint">${htmlText(_t("Period & filters stay on the toolbar"))}</span>\n      </div>\n      <div class="d1-chips" data-chips></div>\n      <div class="d1-popover" id="d1-popover" role="dialog" aria-modal="false" aria-labelledby="d1-popover-title" hidden></div>\n    </div>`;
export function mountDashboardControls(root, options = {}) {
  const uid = "id-dash-control-" + ++instanceNumber;
  const ns = (html) =>
    html.replace(
      /(id|aria-controls|aria-labelledby)="d1-([^"]+)"/g,
      (_, attr, name) => `${attr}="${uid}-${name}"`,
    );
  const select = (node, s) =>
    node.querySelector(s.replace(/#d1-/g, "#" + uid + "-"));
  let destroyed = false;
  const esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const TODAY =
    options.today ||
    new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Makassar" }).format(
      new Date(),
    );
  const parse = (s) => new Date(s + "T12:00:00");
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const add = (s, n) => {
    const d = parse(s);
    d.setDate(d.getDate() + n);
    return iso(d);
  };
  const monthShift = (s, n) => {
    const d = parse(s),
      day = d.getDate();
    d.setDate(1);
    d.setMonth(d.getMonth() + n);
    d.setDate(
      Math.min(day, new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()),
    );
    return iso(d);
  };
  const monthStart = (s) => s.slice(0, 8) + "01";
  const valid = (s) =>
    /^\d{4}-\d{2}-\d{2}$/.test(s) && !isNaN(+parse(s)) && iso(parse(s)) === s;
  const span = (a, b) => Math.round((parse(b) - parse(a)) / 86400000) + 1;
  const countWork = (a, b) => {
    let n = 0;
    for (let s = a, i = 0; s <= b && i < 4000; s = add(s, 1), i++)
      if (parse(s).getDay() !== 0) n++;
    return n;
  };
  const endAtWorkCount = (a, n) => {
    let s = a,
      c = 0;
    for (let i = 0; i < 4000; i++, s = add(s, 1)) {
      if (parse(s).getDay() !== 0) c++;
      if (c >= n) return s;
    }
    return s;
  };
  const range = (a, b) => {
    if (!valid(a) || !valid(b)) return "Select range";
    const d = parse(a),
      e = parse(b);
    if (a.slice(0, 7) === b.slice(0, 7))
      return `${d.getDate()}–${e.getDate()} ${e.toLocaleDateString("id-ID", { month: "short", year: "numeric" })}`;
    return `${d.toLocaleDateString("id-ID", { day: "numeric", month: "short" })} – ${e.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}`;
  };
  const DIMENSIONS = (options.dimensions || []).map((d) => ({
    ...d,
    values: d.values.map((v) => v.map((x, i) => (i === 0 ? String(x) : x))),
  }));
  const initial = options.initialQuery
    ? JSON.parse(JSON.stringify(options.initialQuery))
    : {
        period: {
          preset: "mtd",
          from: monthStart(TODAY),
          to: TODAY,
          compare: false,
          compareMode: "previous",
          align: false,
          customFrom: monthStart(monthShift(TODAY, -1)),
          customTo: monthShift(TODAY, -1),
        },
        filters: {},
      };
  const state = {
    applied: clone(initial),
    draft: null,
    open: null,
    pinned: false,
    dimension: DIMENSIONS[0]?.id || "unavailable",
    search: "",
    calendarMonth: monthStart(monthShift(initial.period.to, -1)),
    selectingEnd: false,
    lastTrigger: null,
    status: "",
    monthClicks: 0,
  };
  let controls, panel;
  function comparison(p) {
    if (!p.compare || !valid(p.from) || !valid(p.to) || p.from > p.to)
      return null;
    let a, b;
    if (p.compareMode === "custom") {
      a = p.customFrom;
      b = p.customTo;
    } else if (p.compareMode === "year") {
      a = monthShift(p.from, -12);
      b = monthShift(p.to, -12);
    } else if (p.compareMode === "quarter") {
      a = monthShift(p.from, -3);
      b = monthShift(p.to, -3);
    } else if (["mtd", "lastmonth"].includes(p.preset)) {
      a = monthShift(p.from, -1);
      b = monthShift(p.to, -1);
    } else if (p.preset === "ytd") {
      a = monthShift(p.from, -12);
      b = monthShift(p.to, -12);
    } else if (p.preset === "last3") {
      a = monthShift(p.from, -3);
      b = monthShift(p.to, -3);
    } else {
      const n = span(p.from, p.to);
      a = add(p.from, -n);
      b = add(p.from, -1);
    }
    if (!valid(a) || !valid(b) || a > b) return null;
    if (p.align && p.compareMode !== "custom")
      b = endAtWorkCount(a, countWork(p.from, p.to));
    return { from: a, to: b, count: countWork(a, b) };
  }
  function filterLabel(dim, entry) {
    const names = (entry?.ids || []).map(
      (id) => dim.values.find((v) => v[0] === id)?.[1] || id,
    );
    return `${dim.short}${entry.mode === "out" ? " ≠" : ":"} ${names.join(", ")}`;
  }
  function chipHTML(filters, removable) {
    let s = `<span class="d1-chip locked"><i class="fa fa-lock" aria-hidden="true"></i>${esc(options.scopeLabel || "Access scope")}</span>`;
    for (const dim of DIMENSIONS) {
      const e = filters[dim.id];
      if (e?.ids.length)
        s += `<span class="d1-chip">${esc(filterLabel(dim, e))}${removable ? `<button type="button" class="cursor-interaction" data-action="remove-chip" data-dim="${esc(dim.id)}" aria-label="Remove filter ${esc(dim.short)}">×</button>` : ""}</span>`;
    }
    return s;
  }
  function renderToolbar() {
    const p = state.applied.period,
      c = comparison(p);
    select(controls, "[data-period-label]").textContent =
      `Period · ${range(p.from, p.to)}`;
    select(controls, "[data-compare-label]").textContent = c
      ? `Bandingkan · ${range(c.from, c.to)}`
      : "No comparison";
    const n = Object.values(state.applied.filters).filter(
      (x) => x.ids.length,
    ).length;
    select(controls, "[data-filter-label]").textContent = `Filter (${n})`;
    select(controls, "[data-chips]").innerHTML =
      chipHTML(state.applied.filters, true) +
      `<span class="d1-status" aria-live="polite">${esc(state.status || (options.demo ? "Sample data · values are static" : "Selection follows source scope"))}</span>`;
    for (const el of controls.querySelectorAll(
      '[data-action="open-period"],[data-action="open-filter"]',
    ))
      el.setAttribute(
        "aria-expanded",
        String(
          Boolean(
            state.open &&
              (el.dataset.action === "open-filter") ===
                (state.open === "filter"),
          ),
        ),
      );
    icons();
  }
  function icons() {
    if (window.lucide)
      window.lucide.createIcons({ attrs: { width: 13, height: 13 } });
  }
  function open(kind, trigger) {
    if (state.open === kind && state.lastTrigger === trigger) {
      close();
      return;
    }
    state.open = kind;
    state.lastTrigger = trigger;
    state.draft = clone(state.applied);
    state.search = "";
    state.selectingEnd = false;
    state.calendarMonth = monthStart(monthShift(state.draft.period.to, -1));
    renderToolbar();
    renderPanel();
    const first =
      select(panel, 'input[type="search"]') || select(panel, "[data-preset]");
    first?.focus();
  }
  function close(restore = true) {
    if (!state.open) return;
    state.open = null;
    panel.hidden = true;
    panel.innerHTML = "";
    renderToolbar();
    if (restore && state.lastTrigger?.isConnected) state.lastTrigger.focus();
  }
  function position() {
    if (!state.open) return;
    panel.classList.toggle("is-inline", state.pinned);
    if (state.pinned) {
      panel.style.width = "100%";
      return;
    }
    const rect = controls.getBoundingClientRect(),
      trigger = (
        state.lastTrigger || select(controls, "#d1-period-trigger")
      ).getBoundingClientRect();
    const width = Math.min(760, Math.max(280, rect.width - 32));
    panel.style.width = width + "px";
    const left = Math.max(
      8,
      Math.min(trigger.left - rect.left, rect.width - width - 8),
    );
    panel.style.left = left + "px";
    panel.style.top = trigger.bottom - rect.top + 9 + "px";
    panel.style.setProperty(
      "--d1-arrow",
      Math.max(20, Math.min(width - 28, trigger.left - rect.left - left + 24)) +
        "px",
    );
  }
  function panelHeader() {
    return `<div class="d1-popover-head"><div><strong id="d1-popover-title">${state.open === "period" ? "Period & comparison" : "Multiple filters"}</strong><small>${state.pinned ? "Inline panel · charts move below" : "Anchored to the button"}</small></div><div class="d1-head-actions"><button type="button" class="d1-button quiet cursor-interaction" data-action="pin" aria-pressed="${state.pinned}"><i class="fa fa-thumb-tack" aria-hidden="true"></i>${state.pinned ? "Use popover" : "Pin inline"}</button><button type="button" class="d1-iconbutton cursor-interaction" data-action="cancel" aria-label="Close without applying">×</button></div></div>`;
  }
  function calendar(month) {
    const start = parse(month),
      year = start.getFullYear(),
      m = start.getMonth(),
      last = new Date(year, m + 1, 0).getDate(),
      pad = (start.getDay() + 6) % 7,
      p = state.draft.period,
      c = comparison(p);
    let days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
      .map((d) => `<span class="d1-weekday">${d}</span>`)
      .join("");
    days += "<span></span>".repeat(pad);
    for (let n = 1; n <= last; n++) {
      const date = iso(new Date(year, m, n, 12)),
        on = date >= p.from && date <= p.to,
        edge = date === p.from || date === p.to,
        cmp = c && date >= c.from && date <= c.to;
      days += `<button type="button" class="d1-day cursor-interaction ${on ? "range" : ""} ${edge ? "edge" : ""} ${cmp ? "compare" : ""} ${parse(date).getDay() === 0 ? "sunday" : ""}" data-date="${date}" aria-label="${parse(date).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}" aria-pressed="${on}">${n}</button>`;
    }
    return `<div><div class="d1-cal-title">${start.toLocaleDateString("id-ID", { month: "long", year: "numeric" })}</div><div class="d1-days">${days}</div></div>`;
  }
  function periodError() {
    const p = state.draft.period;
    if (!valid(p.from) || !valid(p.to)) return "Enter start and end dates.";
    if (p.from > p.to) return "End date must follow start date.";
    if (p.compare && p.align && countWork(p.from, p.to) === 0)
      return _t("No working days in this range. Change the range or disable alignment.");
    if (!options.allowFuture && p.to > TODAY)
      return _t("End date exceeds the data boundary.");
    if (span(p.from, p.to) > (options.maxDays || 730))
      return `Limit range to ${options.maxDays || 730} days.`;
    if (
      p.compare &&
      (!comparison(p) || !valid(comparison(p).from) || !valid(comparison(p).to))
    )
      return _t("Complete the comparison range.");
    return "";
  }
  function periodHTML() {
    const p = state.draft.period,
      c = comparison(p),
      error = periodError();
    const presets = [
      ["week", _t("This week"), "Current week"],
      ["mtd", _t("This month (MTD)"), "Through the data boundary"],
      ["lastmonth", _t("Last month"), "Full calendar month"],
      ["ytd", "YTD", "Year to date"],
      ["last3", _t("Last 3 months"), "Three full calendar months"],
      ["custom", "Custom", "Select dates"],
    ];
    return `<div class="d1-period-grid"><aside class="d1-presets">${presets.map(([id, t, sub]) => `<button type="button" class="d1-preset cursor-interaction" data-preset="${id}" aria-pressed="${p.preset === id}">${t}<small>${sub}</small></button>`).join("")}</aside><div class="d1-calendar-content"><div class="d1-month-nav"><button type="button" class="d1-iconbutton cursor-interaction" data-action="month-back" aria-label="Previous calendar month">‹</button><span>${state.selectingEnd ? "Select the end date" : "Select start, then end date"}</span><button type="button" class="d1-iconbutton cursor-interaction" data-action="month-next" aria-label="Next calendar month">›</button></div><div class="d1-calendars">${calendar(state.calendarMonth)}${calendar(monthShift(state.calendarMonth, 1))}</div><div class="d1-date-inputs"><label>${esc(_t("From"))}<input type="date" id="d1-date-from" data-field="from" value="${esc(p.from)}" ${options.allowFuture ? "" : `max="${TODAY}"`}/></label><span>→</span><label>To<input type="date" id="d1-date-to" data-field="to" value="${esc(p.to)}" ${options.allowFuture ? "" : `max="${TODAY}"`}/></label></div><div class="d1-comparison"><label class="d1-check"><input type="checkbox" data-field="compare" ${p.compare ? "checked" : ""}/>${esc(_t("Compare with"))}</label>${
      p.compare
        ? `<div class="d1-compare-controls"><label>${esc(_t("Comparison"))}<select id="d1-compare-mode" data-field="compareMode">${[
            ["previous", "Previous period"],
            ["year", "Same period last year"],
            ["quarter", "Same period last quarter"],
            ["custom", "Custom range"],
          ]
            .map(
              ([id, t]) =>
                `<option value="${id}" ${p.compareMode === id ? "selected" : ""}>${t}</option>`,
            )
            .join(
              "",
            )}</select></label><div class="d1-workdays">${c ? `${range(c.from, c.to)}<br/>${options.workdayAlignment === false ? `${span(p.from, p.to)} vs ${span(c.from, c.to)} calendar days` : `${countWork(p.from, p.to)} vs ${c.count} working days`}` : ""}</div></div>${p.compareMode === "custom" ? `<div class="d1-date-inputs"><label>${esc(_t("From"))}<input type="date" id="d1-custom-from" data-field="customFrom" value="${esc(p.customFrom)}"/></label><label>To<input type="date" id="d1-custom-to" data-field="customTo" value="${esc(p.customTo)}"/></label></div>` : ""}<label class="d1-check"><input type="checkbox" data-field="align" ${p.align ? "checked" : ""} ${p.compareMode === "custom" || options.workdayAlignment === false ? "disabled" : ""}/>${esc(_t("Align working days"))}</label><div class="d1-workdays">${options.workdayAlignment === false ? "Alignment requires a company work calendar" : "Preview calendar: Monday–Saturday"}</div>`
        : ""
    }</div>${error ? `<div class="d1-error" role="alert">${esc(error)}</div>` : ""}</div></div><div class="d1-popover-foot"><small>Selection is not applied</small><button type="button" class="d1-button cursor-interaction" data-action="cancel">${esc(_t("Cancel"))}</button><button type="button" class="d1-button primary cursor-interaction" data-action="apply" ${error ? "disabled" : ""}>${esc(_t("Apply"))}</button></div>`;
  }
  function allows(entry, id) {
    return (
      !entry?.ids.length ||
      (entry.mode === "out" ? !entry.ids.includes(id) : entry.ids.includes(id))
    );
  }
  function relevant(dim, value) {
    return dim.id === "brand" || dim.id === "sku"
      ? allows(state.draft.filters.principal, value[2]) &&
          (dim.id !== "sku" || allows(state.draft.filters.brand, value[3]))
      : true;
  }
  function filterError() {
    for (const dim of DIMENSIONS) {
      const e = state.draft.filters[dim.id];
      if (e?.mode === "in")
        for (const id of e.ids) {
          const v = dim.values.find((x) => x[0] === id);
          if (v && !relevant(dim, v))
            return `${esc(v[1])} is outside the parent selection. Review the selection before applying.`;
        }
    }
    return "";
  }
  function filterHTML() {
    const dim = DIMENSIONS.find((d) => d.id === state.dimension) || {
        id: "unavailable",
        name: "Filters are not available",
        values: [],
      },
      entry = state.draft.filters[dim.id] || { mode: "in", ids: [] };
    let group = "";
    const dimensions = DIMENSIONS.map((d) => {
      let heading = "";
      if (group !== d.group) {
        group = d.group;
        heading = `<div class="d1-dimgroup">${esc(d.group)}</div>`;
      }
      const e = state.draft.filters[d.id];
      return (
        heading +
        `<button type="button" class="d1-dimension cursor-interaction" data-dimension="${esc(d.id)}" aria-pressed="${d.id === dim.id}"><span>${esc(d.name)}</span><small>${e?.ids.length ? `${e.mode === "out" ? "≠ " : ""}${e.ids.length}` : ""}</small></button>`
      );
    }).join("");
    const choices = dim.values.filter(
      (v) =>
        v[1].toLowerCase().includes(state.search.toLowerCase()) &&
        (relevant(dim, v) || entry.ids.includes(v[0])),
    );
    const error = filterError();
    return `<div class="d1-filter-grid"><aside class="d1-dimensions">${dimensions}<button type="button" class="d1-dimension" disabled><span>${esc(options.scopeLabel || "Access scope")}</span><i class="fa fa-lock" aria-hidden="true"></i></button></aside><div class="d1-values"><div class="d1-values-title">${esc(dim.name)}</div><input type="search" id="d1-value-search" aria-label="Search filter values" placeholder="Search ${esc(dim.name.toLowerCase())}…" data-field="search" value="${esc(state.search)}"/><div class="d1-mode-switch"><button type="button" class="cursor-interaction" data-mode="in" aria-pressed="${entry.mode === "in"}">${esc(_t("Include"))}</button><button type="button" class="cursor-interaction" data-mode="out" aria-pressed="${entry.mode === "out"}">${esc(_t("Exclude"))}</button></div><div class="d1-value-list">${choices.map((v) => `<label class="d1-value ${!relevant(dim, v) ? "outside" : ""}"><input type="checkbox" data-choice="${esc(v[0])}" ${entry.ids.includes(v[0]) ? "checked" : ""}/><span>${esc(v[1])}</span>${!relevant(dim, v) ? `<small>${esc(_t("outside selection"))}</small>` : ""}</label>`).join("") || `<p class="d1-value-help">${esc(_t("No matching values."))}</p>`}</div><button type="button" class="d1-button quiet cursor-interaction" data-action="clear-dimension">${esc(_t("Clear selection"))}</button><p class="d1-value-help">${dim.id === "principal" ? "Principal narrows Brand and SKU choices. Child selections are retained." : dim.id === "brand" ? "Brand follows Principal and narrows SKU choices." : "Select multiple values for this dimension."}</p>${error ? `<div class="d1-error" role="alert">${esc(error)}</div>` : ""}</div><aside class="d1-summary"><h4>${esc(_t("Draft summary"))}</h4>${chipHTML(state.draft.filters, false)}<div class="d1-rule">${esc(_t("AND between dimensions"))}<br/>${esc(_t("OR within a dimension"))}<br/><br/>${esc(_t("Branches follow access scope."))}</div></aside></div><div class="d1-popover-foot"><button type="button" class="d1-button quiet cursor-interaction" data-action="clear-all">${esc(_t("Clear filters"))}</button><small>${esc(_t("Changes apply after Apply"))}</small><button type="button" class="d1-button cursor-interaction" data-action="cancel">${esc(_t("Cancel"))}</button><button type="button" class="d1-button primary cursor-interaction" data-action="apply" ${error ? "disabled" : ""}>${esc(_t("Apply"))}</button></div>`;
  }
  function renderPanel() {
    const active = document.activeElement,
      restore =
        panel?.contains(active) && active.id
          ? {
              id: active.id,
              start: active.selectionStart,
              end: active.selectionEnd,
            }
          : null;
    panel.hidden = false;
    panel.innerHTML = ns(
      panelHeader() + (state.open === "period" ? periodHTML() : filterHTML()),
    );
    position();
    icons();
    if (restore) {
      const el = select(panel, "#" + restore.id);
      el?.focus();
      if (el && restore.start !== null && el.type === "search")
        el.setSelectionRange(restore.start, restore.end);
    }
  }
  function preset(id) {
    const p = state.draft.period;
    p.preset = id;
    if (id === "week") {
      p.from = add(TODAY, -((parse(TODAY).getDay() + 6) % 7));
      p.to = TODAY;
    }
    if (id === "mtd") {
      p.from = monthStart(TODAY);
      p.to = TODAY;
    }
    if (id === "lastmonth") {
      p.from = monthStart(monthShift(TODAY, -1));
      p.to = add(monthStart(TODAY), -1);
    }
    if (id === "ytd") {
      p.from = TODAY.slice(0, 4) + "-01-01";
      p.to = TODAY;
    }
    if (id === "last3") {
      p.from = monthStart(monthShift(TODAY, -3));
      p.to = add(monthStart(TODAY), -1);
    }
    state.calendarMonth = monthStart(monthShift(p.to, -1));
    state.selectingEnd = false;
    renderPanel();
  }
  async function act(ev) {
    const choice = ev.target.closest("[data-choice]");
    if (choice) return;
    const btn = ev.target.closest("button");
    if (!btn || btn.disabled) return;
    if (btn.dataset.preset) {
      preset(btn.dataset.preset);
      return;
    }
    if (btn.dataset.date) {
      const p = state.draft.period,
        day = btn.dataset.date;
      p.preset = "custom";
      if (!state.selectingEnd) {
        p.from = day;
        p.to = day;
        state.selectingEnd = true;
      } else {
        const a = p.from;
        p.from = day < a ? day : a;
        p.to = day < a ? a : day;
        state.selectingEnd = false;
      }
      renderPanel();
      return;
    }
    if (btn.dataset.dimension) {
      state.dimension = btn.dataset.dimension;
      state.search = "";
      renderPanel();
      return;
    }
    if (btn.dataset.mode) {
      const id = state.dimension;
      state.draft.filters[id] ??= { mode: "in", ids: [] };
      state.draft.filters[id].mode = btn.dataset.mode;
      renderPanel();
      return;
    }
    switch (btn.dataset.action) {
      case "open-period":
        open("period", btn);
        break;
      case "open-filter":
        open("filter", btn);
        break;
      case "cancel":
        close();
        break;
      case "pin":
        state.pinned = !state.pinned;
        renderPanel();
        break;
      case "month-back":
        state.calendarMonth = monthStart(monthShift(state.calendarMonth, -1));
        renderPanel();
        break;
      case "month-next":
        state.calendarMonth = monthStart(monthShift(state.calendarMonth, 1));
        renderPanel();
        break;
      case "clear-dimension":
        delete state.draft.filters[state.dimension];
        renderPanel();
        break;
      case "clear-all":
        state.draft.filters = {};
        renderPanel();
        break;
      case "remove-chip": {
        const next = clone(state.applied);
        delete next.filters[btn.dataset.dim];
        if (await commit(next)) {
          close(false);
          select(controls, "#d1-filter-trigger").focus();
        }
        break;
      }
      case "reset":
        if (await commit(initial)) close(false);
        break;
      case "apply":
        if (state.open === "period" ? periodError() : filterError()) return;
        if (await commit(state.draft)) close();
        break;
    }
  }
  function changed(ev) {
    const el = ev.target;
    if (el.dataset.choice) {
      const id = state.dimension;
      const e = (state.draft.filters[id] ??= { mode: "in", ids: [] });
      e.ids = el.checked
        ? [...new Set([...e.ids, el.dataset.choice])]
        : e.ids.filter((x) => x !== el.dataset.choice);
      renderPanel();
      return;
    }
    const f = el.dataset.field;
    if (!f) return;
    if (f === "search") {
      state.search = el.value;
      renderPanel();
      return;
    }
    const p = state.draft.period;
    p[f] = el.type === "checkbox" ? el.checked : el.value;
    if (f === "from" || f === "to") p.preset = "custom";
    renderPanel();
  }
  function init() {
    controls = root;
    if (!controls) return false;
    const holder = document.createElement("template");
    holder.innerHTML = ns(toolbar());
    controls.append(holder.content.cloneNode(true));
    controls = controls.firstElementChild;
    panel = select(controls, "#d1-popover");
    controls.addEventListener("click", act);
    controls.addEventListener("input", (ev) => {
      if (ev.target.dataset.field === "search") changed(ev);
    });
    controls.addEventListener("change", (ev) => {
      if (ev.target.dataset.field !== "search") changed(ev);
    });
    root.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onOutside);
    window.addEventListener("resize", position);
    renderToolbar();
    root.dataset.ready = "true";
    root.__controls = {
      getState: () => clone(state.applied),
      getDraft: () => clone(state.draft),
      isOpen: () => state.open,
    };
    return true;
  }
  const onKey = (ev) => {
    if (ev.key === "Escape" && state.open) {
      ev.preventDefault();
      close();
    }
  };
  const onOutside = (ev) => {
    if (state.open && !controls.contains(ev.target)) close(false);
  };
  let applying = false;
  async function commit(next) {
    if (applying) return false;
    applying = true;
    root.setAttribute("aria-busy", "true");
    const pendingControls = [...root.querySelectorAll("button,input,select")].map(el => [el, el.disabled]);
    for (const [el] of pendingControls) el.disabled = true;
    let result;
    try {
      result = await options.onApply?.(clone(next));
    } catch (error) {
      result = false;
      state.status = error.message;
    }
    for (const [el, disabled] of pendingControls) el.disabled = disabled;
    applying = false;
    root.removeAttribute("aria-busy");
    if (destroyed) return false;
    if (result === false) {
      state.status = _t("Filters were not applied. Review the source error.");
      renderToolbar();
      return false;
    }
    state.applied = clone(next);
    state.status = options.demo
      ? "Selection applied · values remain examples"
      : "Selection applied";
    root.dataset.query = JSON.stringify(state.applied);
    renderToolbar();
    return true;
  }
  init();
  return {
    getState: () => clone(state.applied),
    destroy() {
      destroyed = true;
      root.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onOutside);
      window.removeEventListener("resize", position);
      root.replaceChildren();
    },
  };
}
