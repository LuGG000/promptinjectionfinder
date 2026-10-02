/* PromptInjectionFinder – offline UI (no external dependencies). */
"use strict";

const TOKEN = document.querySelector('meta[name="pif-token"]').content;
const SEV_ORDER = ["info", "low", "medium", "high", "critical"];
const sevName = (s) => t("sev")[s];
const verdictName = (v) => t("verdict")[v];
const typeName = (x) => t("type")[x] || x;
// findings carry both languages; pick the active one
const ftitle = (x) => (x.i18n && x.i18n[LANG] ? x.i18n[LANG].title : x.title);
const fdesc = (x) => (x.i18n && x.i18n[LANG] ? x.i18n[LANG].description : x.description);

const state = {
  files: [],            // scan results (with file_id)
  selected: null,       // file_id
  choice: {},           // file_id -> Set(finding ids to remove)
  tab: "findings",
  info: null,
  collapsed: new Set(),  // batch ids of collapsed scan groups in the sidebar
};

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ------------------------------------------------------------------ API */
async function api(path, opts = {}) {
  const headers = Object.assign({ "X-PIF-Token": TOKEN }, opts.headers || {});
  let body = opts.body;
  if (body && !(body instanceof Blob) && !(body instanceof ArrayBuffer) && typeof body !== "string") {
    body = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (opts.raw) {
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
    return res;
  }
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok || data.error) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), err ? 6000 : 3000);
}

function busy(on, text = t("scanning")) {
  $("#busy").hidden = !on;
  $("#busy-text").textContent = text;
}

/* ------------------------------------------------------------------ files */
function addResult(r) {
  const idx = state.files.findIndex((f) => f.file_id === r.file_id);
  if (idx >= 0) state.files[idx] = r; else state.files.push(r);
  state.choice[r.file_id] = new Set(r.findings.filter((f) => f.removable && f.default_remove).map((f) => f.id));
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList).filter((f) => f.size > 0);
  if (!files.length) return;
  let done = 0, last = null;
  // all files of one drop/selection form one scan group; a dropped folder gives it its name
  const batch = Math.random().toString(36).slice(2, 14);
  const top = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : "";
  const label = top && files.every((f) => (f.webkitRelativePath || "").startsWith(top + "/")) ? top : "";
  busy(true, t("scanning_n", 0, files.length));
  try {
    for (const f of files) {
      try {
        const r = await api("/api/upload?name=" + encodeURIComponent(f.webkitRelativePath || f.name) +
          "&batch=" + batch + "&batch_label=" + encodeURIComponent(label), { method: "POST", body: f });
        r.name = f.webkitRelativePath || f.name;
        addResult(r);
        last = r.file_id;
      } catch (e) {
        toast(`${f.name}: ${e.message}`, true);
      }
      done++;
      busy(true, t("scanning_n", done, files.length));
    }
  } finally {
    busy(false);
  }
  sortFiles();
  if (!state.selected || files.length > 1) state.selected = state.files.find((f) => f.batch?.id === batch)?.file_id || last;
  focusBatch(batch);
  renderAll();
}

async function scanPath(path) {
  busy(true, t("scanning_path"));
  try {
    const data = await api("/api/scan_path", { body: { path, recursive: true } });
    data.results.forEach(addResult);
    sortFiles();
    state.selected = state.files.find((f) => data.results.some((r) => r.file_id === f.file_id))?.file_id || state.selected;
    if (data.results[0]?.batch) focusBatch(data.results[0].batch.id);
    renderAll();
    toast(t("n_files_scanned", data.results.length));
  } catch (e) {
    toast(e.message, true);
  } finally {
    busy(false);
  }
}

function sortFiles() {
  state.files.sort((a, b) => b.risk_score - a.risk_score || a.name.localeCompare(b.name));
}

// a new scan opens its group and folds the older ones, so many scans stay tidy
function focusBatch(id) {
  state.files.forEach((f) => { if (f.batch && f.batch.id !== id) state.collapsed.add(f.batch.id); });
  state.collapsed.delete(id);
}

// sidebar groups: one per scan run, newest first; files keep their risk order inside a group
function groupFiles() {
  const groups = new Map();
  for (const f of state.files) {
    const key = f.batch ? f.batch.id : "_" + f.file_id;
    if (!groups.has(key)) groups.set(key, { id: key, batch: f.batch, files: [] });
    groups.get(key).files.push(f);
  }
  return [...groups.values()].sort((a, b) => (b.batch?.time || 0) - (a.batch?.time || 0));
}

function groupLabel(g) {
  const b = g.batch;
  if (b.kind === "web") return b.label.replace(/^https?:\/\//, "").replace(/\/$/, "") || t("group_web");
  if (b.kind === "folder") return b.label.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || b.label;  // full path in the tooltip
  return b.label || t("files_count", g.files.length);
}

function current() {
  return state.files.find((f) => f.file_id === state.selected) || null;
}

/* ------------------------------------------------------------------ rendering */
function renderAll() {
  renderSidebar();
  renderDetail();
  $("#btn-export").disabled = state.files.length === 0;
}

function renderSidebar() {
  const ul = $("#file-list");
  $("#file-count").textContent = state.files.length ? `(${state.files.length})` : "";
  $("#btn-clear").hidden = state.files.length === 0;
  const fileItem = (f, inGroup) => {
    const n = f.findings.filter((x) => x.severity !== "info").length;
    const badge = f.error ? `<span class="badge error">${t("error")}</span>` : `<span class="badge ${f.verdict}">${verdictName(f.verdict)}</span>`;
    return `<li data-id="${f.file_id}" class="${f.file_id === state.selected ? "active" : ""}${inGroup ? " in-group" : ""}" title="${esc(f.path)}">
      <span class="fname">${esc(f.name)}</span>${badge}
      <span class="fsub">${typeName(f.filetype)} · ${t("risk")} ${Math.round(f.risk_score)} · ${t("findings_n", n)}</span></li>`;
  };
  const loc = LANG === "de" ? "de-DE" : "en-US";
  ul.innerHTML = groupFiles().map((g) => {
    if (!g.batch || (g.files.length < 2 && g.batch.kind !== "web")) return g.files.map((f) => fileItem(f, false)).join("");
    const open = !state.collapsed.has(g.id);
    const worst = g.files.reduce((a, f) => (f.risk_score > a.risk_score ? f : a), g.files[0]);
    const bad = g.files.filter((f) => f.verdict !== "clean").length;
    const when = new Date(g.batch.time).toLocaleString(loc, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    return `<li class="group${open ? " open" : ""}" data-batch="${esc(g.id)}" title="${esc(g.batch.label)}">
      <button class="g-head" aria-expanded="${open}"><span class="g-caret" aria-hidden="true">▸</span>
        <span class="fname">${esc(groupLabel(g))}</span><span class="badge ${worst.verdict}">${verdictName(worst.verdict)}</span>
        <span class="fsub">${t("group_" + g.batch.kind)} · ${esc(when)} · ${t("files_count", g.files.length)}${bad ? " · " + t("n_flagged", bad) : ""}</span>
      </button><button class="g-remove" title="${t("remove_scan")}" aria-label="${t("remove_scan")}">×</button></li>` +
      (open ? g.files.map((f) => fileItem(f, true)).join("") : "");
  }).join("");
  const counts = { dangerous: 0, suspicious: 0, clean: 0 };
  state.files.forEach((f) => counts[f.verdict]++);
  const sum = $("#summary");
  sum.hidden = state.files.length === 0;
  sum.innerHTML = ["dangerous", "suspicious", "clean"].filter((k) => counts[k])
    .map((k) => `<span class="badge ${k}">${counts[k]} ${verdictName(k)}</span>`).join("");
}

function renderDetail() {
  const f = current();
  $("#dropzone").hidden = !!f;
  $("#detail").hidden = !f;
  if (!f) return;
  $("#d-name").textContent = f.name;
  const st = f.stats || {};
  const loc = LANG === "de" ? "de-DE" : "en-US";
  const meta = [typeName(f.filetype)];
  if (st.pages) meta.push(t("pages_n", st.pages));
  if (st.chars != null) meta.push(t("chars_n", st.chars.toLocaleString(loc)));
  if (st.hidden_chars) meta.push(t("invisible_n", st.hidden_chars.toLocaleString(loc)));
  if (st.encoding && !st.web) meta.push(st.encoding);
  if (st.web) meta.push(st.rendered ? t("web_rendered") : t("web_static"));
  if (f.path && f.path !== f.name) meta.push(f.path);
  $("#d-meta").innerHTML = meta.map((m) => `<span>${esc(m)}</span>`).join("");
  $("#d-score").textContent = Math.round(f.risk_score);
  $("#d-verdict").textContent = f.error ? t("read_error") : verdictName(f.verdict);
  const color = f.verdict === "dangerous" ? "var(--sev-critical)" : f.verdict === "suspicious" ? "var(--sev-medium)" : "var(--good)";
  $("#d-bar").style.width = Math.max(3, f.risk_score) + "%";
  $("#d-bar").style.background = color;
  $("#d-verdict").style.color = color;
  $("#t-count").textContent = f.findings.length;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === state.tab));
  ["findings", "document", "preview"].forEach((t) => ($("#tab-" + t).hidden = t !== state.tab));
  if (state.tab === "findings") renderFindings(f);
  if (state.tab === "document") renderDocument(f);
  if (state.tab === "preview") renderPreview(f);
}

function visible(s) {
  // Make invisible / control characters visible as chips; long runs are compacted.
  let out = "";
  const cps = Array.from(String(s ?? ""));
  for (let i = 0; i < cps.length; i++) {
    const cp = cps[i].codePointAt(0);
    if (!isInvisible(cp)) { out += esc(cps[i]); continue; }
    let j = i;
    while (j < cps.length && isInvisible(cps[j].codePointAt(0))) j++;
    const run = j - i;
    if (run > 6) {
      out += cps.slice(i, i + 3).map((c) => `<span class="inv">${cpLabel(c.codePointAt(0))}</span>`).join("") +
        `<span class="inv-run" title="${t("invisible_chars", run)}">${t("more_invisible", run - 3)}</span>`;
    } else {
      out += cps.slice(i, j).map((c) => `<span class="inv">${cpLabel(c.codePointAt(0))}</span>`).join("");
    }
    i = j - 1;
  }
  return out;
}
function cpLabel(cp) { return "U+" + cp.toString(16).toUpperCase().padStart(4, "0"); }
function isInvisible(cp) {
  return (cp >= 0x200b && cp <= 0x200f) || (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2060 && cp <= 0x206f) ||
    cp === 0xfeff || cp === 0xad || cp === 0x34f || cp === 0x180e || cp === 0x61c || (cp >= 0xfe00 && cp <= 0xfe0f) ||
    (cp >= 0xe0000 && cp <= 0xe01ef) || cp === 0x1b || (cp < 0x20 && cp !== 9 && cp !== 10 && cp !== 13) ||
    (cp >= 0x7f && cp <= 0x9f) || cp === 0x115f || cp === 0x1160 || cp === 0x3164 || cp === 0xffa0 ||
    (cp >= 0xfff9 && cp <= 0xfffb) || (cp >= 0xe000 && cp <= 0xf8ff);
}
// Evidence strings from the server already contain ⟦U+XXXX⟧ markers. Runs are compacted.
function evidenceHtml(s) {
  const html = esc(s).replace(/(⟦U\+[0-9A-F]{4,6}⟧)+/g, (run) => {
    const parts = run.match(/⟦U\+([0-9A-F]{4,6})⟧/g);
    if (parts.length <= 3) return parts.map((p) => `<span class="inv">${p.slice(1, -1)}</span>`).join("");
    return `<span class="inv-run" title="${t("invisible_chars", parts.length)}">${t("invisible_short", parts.length, parts[0].slice(1, -1))}</span>`;
  });
  return html;
}

function locText(x) {
  const l = x.location;
  if (l.target === "pdf_meta") return t("loc_meta");
  if (l.target === "pdf_js") return t("loc_js");
  if (l.target === "pdf_embedded") return t("loc_attach");
  if (l.target === "source") return t("loc_source");
  if (l.page != null) return t("loc_page", l.page + 1);
  if (l.line) return t("loc_line", l.line);
  return "";
}

function renderFindings(f) {
  const box = $("#tab-findings");
  if (f.error) {
    box.innerHTML = `<div class="empty">${t("not_analysed")}${esc(f.error)}</div>`;
    return;
  }
  if (!f.findings.length) {
    box.innerHTML = `<div class="empty ok">${t("no_findings")}</div>`;
    return;
  }
  const sel = state.choice[f.file_id];
  let html = "";
  if (f.stats && f.stats.ocr_pages && f.stats.ocr_pages.length) {
    html += `<div class="note">${t("ocr_note", f.stats.ocr_pages.join(", "))}</div>`;
  }
  const groups = [[t("grp_dangerous"), (x) => x.score >= 65], [t("grp_suspicious"), (x) => x.score >= 20 && x.score < 65],
    [t("grp_hints"), (x) => x.score < 20]];
  for (const [label, pred] of groups) {
    const items = f.findings.filter(pred);
    if (!items.length) continue;
    html += `<div class="group-title">${label} (${items.length})</div>`;
    html += items.map((x) => `
      <article class="finding ${x.severity}" id="card-${x.id}">
        <input type="checkbox" data-fid="${x.id}" ${sel.has(x.id) ? "checked" : ""} ${x.removable ? "" : "disabled"}
          title="${x.removable ? t("remove_on_clean") : t("not_removable")}" aria-label="${t("remove_finding")}">
        <div>
          <div class="f-top">
            <span class="badge sev-${x.severity}">${sevName(x.severity)} · ${Math.round(x.score)}</span>
            <span class="f-title">${esc(ftitle(x))}</span>
            <span class="f-loc">${esc(locText(x))}</span>
          </div>
          <div class="f-desc">${esc(fdesc(x))}</div>
          ${x.evidence ? `<div class="f-block"><div class="lbl">${t("evidence")}</div><pre>${evidenceHtml(x.evidence)}</pre></div>` : ""}
          ${x.decoded && x.decoded !== x.evidence ? `<div class="f-block decoded"><div class="lbl">${t("decoded")}</div><pre>${esc(x.decoded)}</pre></div>` : ""}
          <div class="f-actions">
            ${hasDocLocation(f, x) ? `<button class="link" data-show="${x.id}">${t("show_in_doc")}</button>` : ""}
            <span class="muted mono" style="font-size:11px">${esc(x.rule)}</span>
          </div>
        </div>
      </article>`).join("");
  }
  box.innerHTML = html;
}

function hasDocLocation(f, x) {
  if (f.filetype === "pdf") return (x.location.view_rects || []).length > 0;
  return x.location.start != null;
}

/* ---------- document view ---------- */
function renderDocument(f, focusId) {
  const box = $("#tab-document");
  if (f.filetype === "pdf") return renderPdf(f, box, focusId);
  // Offsets from the server are Unicode code points; JS strings are UTF-16.
  const chars = Array.from(f.text_preview || "");
  const n = chars.length;
  const sevRank = new Int8Array(n).fill(-1);
  const owner = new Int32Array(n).fill(-1);
  const anchors = new Map();
  f.findings.forEach((x, i) => {
    const l = x.location;
    const ranges = (l.ranges && l.ranges.length) ? l.ranges.map((r) => [r[0], r[1]]) : (l.start != null ? [[l.start, l.end]] : []);
    if (!ranges.length) return;
    const rank = SEV_ORDER.indexOf(x.severity);
    const a = Math.min(ranges[0][0], n);
    if (!anchors.has(a)) anchors.set(a, []);
    anchors.get(a).push(x.id);
    for (const [s, e] of ranges) {
      for (let k = Math.max(0, s); k < Math.min(e, n); k++) {
        if (rank > sevRank[k]) { sevRank[k] = rank; owner[k] = i; }
      }
    }
  });
  const parts = [];
  let k = 0;
  while (k < n) {
    let j = k + 1;
    while (j < n && owner[j] === owner[k] && !anchors.has(j)) j++;
    if (anchors.has(k)) parts.push(anchors.get(k).map((id) => `<a id="anc-${id}"></a>`).join(""));
    const seg = chars.slice(k, j).join("");
    if (owner[k] >= 0) {
      const x = f.findings[owner[k]];
      parts.push(`<mark class="${x.severity}" data-card="${x.id}" title="${esc(ftitle(x))}">${visible(seg)}</mark>`);
    } else {
      parts.push(visible(seg));
    }
    k = j;
  }
  const legend = `<div class="legend">${t("marks")} ${["critical", "high", "medium", "low"].map((s) => `<span><i class="sev-${s}"></i>${sevName(s)}</span>`).join("")}
    <span>· <span class="inv">U+200B</span> ${t("invisible_char")}</span>
    ${f.stats && f.stats.truncated_preview ? `<span>${t("preview_truncated")}</span>` : ""}</div>`;
  box.innerHTML = legend + `<div class="docview mono">${parts.join("")}</div>`;
  if (focusId) {
    const a = document.getElementById("anc-" + focusId);
    if (a) {
      a.scrollIntoView({ block: "center" });
      const m = a.nextElementSibling;
      if (m && m.tagName === "MARK") { m.classList.add("flash"); }
    }
  }
}

function renderPdf(f, box, focusId) {
  const sizes = (f.stats && f.stats.page_sizes) || [];
  const byPage = new Map();
  f.findings.forEach((x) => (x.location.view_rects || []).forEach((r) => {
    if (!byPage.has(r[0])) byPage.set(r[0], []);
    byPage.get(r[0]).push([x, r]);
  }));
  const pages = sizes.map((sz, p) => {
    const hls = (byPage.get(p) || []).map(([x, r]) => {
      const off = r[3] <= 0 || r[4] <= 0 || r[1] >= 1 || r[2] >= 1;
      const x0 = Math.min(Math.max(r[1], 0), 0.99), y0 = Math.min(Math.max(r[2], 0), 0.99);
      const w = Math.max(Math.min(r[3], 1) - x0, 0.006), h = Math.max(Math.min(r[4], 1) - y0, 0.006);
      return `<div class="pdf-hl ${x.severity}${off ? " offpage" : ""}" data-card="${x.id}" data-hl="${x.id}" title="${esc(ftitle(x))}${off ? t("off_page") : ""}"
        style="left:${x0 * 100}%;top:${y0 * 100}%;width:${w * 100}%;height:${h * 100}%"></div>`;
    }).join("");
    const width = Math.min(900, sz[0] * 1.5);
    return `<div class="pdf-page" style="width:${width}px" id="pdfp-${p}"><span class="pno">${t("page")} ${p + 1}</span>
      <img loading="lazy" alt="${t("page")} ${p + 1}" src="/api/page?id=${f.file_id}&page=${p}&zoom=1.5&t=${encodeURIComponent(TOKEN)}"
        style="aspect-ratio:${sz[0]}/${sz[1]}">${hls}</div>`;
  }).join("");
  box.innerHTML = `<div class="note">${t("pdf_note")}</div>
    <div class="pdf-pages">${pages || `<div class="empty">${t("no_pages")}</div>`}</div>`;
  if (focusId) {
    const el = box.querySelector(`[data-hl="${focusId}"]`);
    if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); }
  }
}

/* ---------- cleaned preview ---------- */
async function renderPreview(f) {
  const box = $("#tab-preview");
  const ids = Array.from(state.choice[f.file_id] || []);
  box.innerHTML = `<div class="empty">${t("making_preview")}</div>`;
  try {
    const data = await api("/api/preview", { body: { id: f.file_id, ids, lang: LANG } });
    if (state.selected !== f.file_id || state.tab !== "preview") return;
    const a = data.after;
    const cls = a.verdict === "clean" ? "note ok" : "note";
    const rest = a.findings.filter((x) => x.score >= 20);
    const web = f.stats && f.stats.web;
    box.innerHTML = `<div class="${cls}">${t("removed_risk", data.removed, Math.round(a.risk_score), verdictName(a.verdict))}
      ${web ? "<br>" + t("web_preview_note") : ""}
      ${rest.length ? `<br>${t("remaining")}${rest.map((x) => esc(ftitle(x))).join(" · ")}` : ""}
      ${f.filetype === "pdf" ? `<br><span class='muted'>${t("pdf_preview_note")}</span>` : ""}</div>
      <div class="docview mono">${visible(data.text)}</div>`;
  } catch (e) {
    box.innerHTML = `<div class="empty">${t("error")}: ${esc(e.message)}</div>`;
  }
}

/* ------------------------------------------------------------------ actions */
async function downloadCleaned() {
  const f = current();
  if (!f) return;
  try {
    const res = await api("/api/download", { body: { id: f.file_id, ids: Array.from(state.choice[f.file_id]), lang: LANG }, raw: true });
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    saveBlob(await res.blob(), m ? decodeURIComponent(m[1]) : f.name.split("/").pop());
  } catch (e) {
    toast(e.message, true);
  }
}

function openExport() {
  $("#export-result").innerHTML = "";
  if (!$("#export-dir").value && state.info) $("#export-dir").value = state.info.default_export_dir;
  $("#dlg-export").showModal();
}

function exportItems() {
  const onlyFindings = $("#export-only-findings").checked;
  return state.files.filter((f) => !f.error && (!onlyFindings || f.findings.length))
    .map((f) => ({ id: f.file_id, ids: Array.from(state.choice[f.file_id] || []) }));
}

function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}

async function doExportZip(ev) {
  ev.preventDefault();
  const items = exportItems();
  if (!items.length) { toast(t("no_files_export"), true); return; }
  busy(true, t("cleaning_zip"));
  try {
    const res = await api("/api/export_zip", { body: { items, lang: LANG }, raw: true });
    saveBlob(await res.blob(), "PromptInjectionFinder_Export.zip");
    $("#export-result").innerHTML = `<div class="note ok">${t("zip_done", items.length)}</div>`;
  } catch (e) {
    $("#export-result").innerHTML = `<div class="note" style="border-color:var(--sev-critical)">${t("error")}: ${esc(e.message)}</div>`;
  } finally {
    busy(false);
  }
}

async function doExport(ev) {
  ev.preventDefault();
  const items = exportItems();
  if (!items.length) { toast(t("no_files_export"), true); return; }
  busy(true, t("cleaning_export"));
  try {
    const data = await api("/api/export", { body: { out_dir: $("#export-dir").value.trim(), items, lang: LANG } });
    $("#export-result").innerHTML = `<div class="note ok">${t("export_done")}<b class="mono">${esc(data.out_dir)}</b>
      <ul class="export-list">${data.summary.map((s) => `<li><span>${esc(s.file)}</span><span>${t("risk_short")} ${Math.round(s.before)} → <b>${Math.round(s.after)}</b> · ${t("removed_n", s.removed)}</span></li>`).join("")}</ul>
      <p><button class="btn small" type="button" id="open-folder">${t("open_folder")}</button></p></div>`;
    $("#open-folder").onclick = () => api("/api/open_folder", { body: { path: data.out_dir } }).catch((e) => toast(e.message, true));
    if (state.info) state.info.default_export_dir = $("#export-dir").value;
  } catch (e) {
    $("#export-result").innerHTML = `<div class="note" style="border-color:var(--sev-critical)">${t("error")}: ${esc(e.message)}</div>`;
  } finally {
    busy(false);
  }
}

function setSelection(mode) {
  const f = current();
  if (!f) return;
  const set = new Set();
  f.findings.forEach((x) => {
    if (!x.removable) return;
    if (mode === "all" || (mode === "rec" && x.default_remove)) set.add(x.id);
  });
  state.choice[f.file_id] = set;
  renderDetail();
}

/* ------------------------------------------------------------------ website scan */
const crawl = { job: null, timer: null };

function openUrlDialog() {
  const browser = state.info && state.info.browser;
  $("#url-render-label").textContent = browser ? t("render_with", browser) : t("render_none");
  $("#url-render").checked = !!browser;
  $("#url-log").innerHTML = "";
  $("#url-progress").hidden = true;
  setCrawlRunning(false);
  $("#dlg-url").showModal();
  $("#url-input").focus();
}

function setCrawlRunning(on) {
  $("#url-go").hidden = on;
  $("#url-cancel").hidden = !on;
  $("#url-cancel").disabled = false;
  $("#url-close").disabled = on;
  ["#url-input", "#url-depth", "#url-max", "#url-same", "#url-docs", "#url-discover", "#url-robots"]
    .forEach((s) => ($(s).disabled = on));
  $("#url-render").disabled = on || !(state.info && state.info.browser);
}

async function startCrawl(ev) {
  ev.preventDefault();
  const url = $("#url-input").value.trim();
  if (!url) { $("#url-input").focus(); return; }
  const body = {
    url,
    depth: Number($("#url-depth").value),
    max_pages: Math.max(1, Math.min(300, Number($("#url-max").value) || 30)),
    same_host: $("#url-same").checked,
    documents: $("#url-docs").checked,
    discover: $("#url-discover").checked,
    robots: $("#url-robots").checked,
    render: $("#url-render").checked && !$("#url-render").disabled,
  };
  $("#url-log").innerHTML = "";
  $("#url-progress").hidden = false;
  $("#url-bar").style.width = "2%";
  $("#url-status").textContent = t("starting");
  setCrawlRunning(true);
  try {
    const { job } = await api("/api/crawl", { body });
    crawl.job = job;
    pollCrawl();
  } catch (e) {
    setCrawlRunning(false);
    $("#url-status").textContent = t("error") + ": " + e.message;
  }
}

async function pollCrawl() {
  if (!crawl.job) return;
  let st;
  try {
    st = await api("/api/crawl?job=" + encodeURIComponent(crawl.job));
  } catch (e) {
    $("#url-status").textContent = t("error") + ": " + e.message;
    setCrawlRunning(false);
    return;
  }
  const pct = st.total ? Math.min(100, Math.round((st.done / st.total) * 100)) : 0;
  $("#url-bar").style.width = Math.max(2, st.phase === "analyze" ? 50 + pct / 2 : pct / 2) + "%";
  $("#url-status").textContent = crawl.cancelling ? t("cancelling")
    : `${t(st.phase === "analyze" ? "phase_analyze" : "phase_fetch")}: ${Math.min(st.done + (st.phase === "analyze" ? 1 : 0), st.total)}/${st.total} · ${st.current || ""}`;
  if (st.status === "running") {
    crawl.timer = setTimeout(pollCrawl, 400);
    return;
  }
  crawl.job = null;
  crawl.cancelling = false;
  setCrawlRunning(false);
  $("#url-bar").style.width = "100%";
  if (st.status === "error") {
    $("#url-status").textContent = t("error") + ": " + st.error;
  } else {
    const results = st.results || [];
    results.forEach(addResult);
    sortFiles();
    if (results.length) {
      state.selected = results.slice().sort((a, b) => b.risk_score - a.risk_score)[0].file_id;
      if (results[0].batch) focusBatch(results[0].batch.id);
    }
    renderAll();
    const bad = results.filter((r) => r.verdict !== "clean").length;
    $("#url-status").textContent = `${st.status === "cancelled" ? t("cancelled") : ""}${t("pages_scanned", results.length)}` +
      (bad ? t("n_suspicious", bad) : t("all_clean"));
  }
  renderCrawlLog(st.log || []);
}

function renderCrawlLog(log) {
  if (!log.length) { $("#url-log").innerHTML = ""; return; }
  $("#url-log").innerHTML = `<div class="lbl muted" style="margin-top:10px;font-size:12px">${t("log")}</div><ul class="crawl-log">` +
    log.map((e) => {
      const ok = e.status === "loaded";
      const label = (t("log_status")[e.status] || e.status) + (e.code ? " " + e.code : "");
      return `<li><span class="st ${ok ? "ok" : "bad"}">${esc(label)}</span><span class="u">${esc(e.url || "")}</span>` +
        (e.note ? `<span class="n">${esc(e.note)}</span>` : "") + `</li>`;
    }).join("") + `</ul>`;
}

async function cancelCrawl() {
  if (!crawl.job) return;
  $("#url-cancel").disabled = true;
  $("#url-status").textContent = t("cancelling");
  crawl.cancelling = true;
  await api("/api/crawl_cancel", { body: { job: crawl.job } }).catch(() => {});
}

/* ------------------------------------------------------------------ updates */
async function openUpdate() {
  $("#upd-current").textContent = (state.info && state.info.version) || "?";
  $("#upd-status").className = "note";
  $("#upd-status").textContent = t("checking_update");
  $("#upd-log").hidden = true;
  $("#upd-go").hidden = true;
  $("#dlg-update").showModal();
  try {
    const r = await api("/api/update_check");
    if (r.error) {
      $("#upd-status").textContent = r.error;
    } else if (r.update_available) {
      $("#upd-status").className = "note ok";
      $("#upd-status").innerHTML = t("new_version", esc(r.latest)) +
        (r.notes ? `<br><span class="muted">${esc(r.notes).slice(0, 400)}</span>` : "");
      $("#upd-go").hidden = r.method === "exe";
      if (r.method === "exe") $("#upd-status").innerHTML += t("exe_redownload");
    } else {
      $("#upd-status").className = "note ok";
      $("#upd-status").textContent = t("newest", r.current);
    }
  } catch (e) {
    $("#upd-status").textContent = t("check_failed") + e.message;
  }
}

async function runUpdate() {
  $("#upd-go").disabled = true;
  $("#upd-status").textContent = t("updating");
  try {
    const r = await api("/api/update", { body: {} });
    $("#upd-log").hidden = false;
    $("#upd-log").textContent = (r.log || []).join("\n");
    $("#upd-status").className = r.ok ? "note ok" : "note";
    $("#upd-status").textContent = r.ok
      ? t("update_done")
      : t("update_failed") + r.error;
    $("#upd-go").hidden = !!r.ok;
  } catch (e) {
    $("#upd-status").textContent = t("update_failed") + e.message;
  } finally {
    $("#upd-go").disabled = false;
  }
}

/* ------------------------------------------------------------------ events */
function initTheme() {
  let t = null;
  try { t = localStorage.getItem("pif-theme"); } catch (e) { /* storage blocked */ }
  if (t) document.documentElement.dataset.theme = t;
  $("#btn-theme").onclick = () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("pif-theme", next); } catch (e) { /* ignore */ }
  };
}

function initLang() {
  applyStaticI18n();
  $("#btn-lang").onclick = () => {
    setLang(LANG === "de" ? "en" : "de");
    renderAll();
  };
}

function initEvents() {
  $("#file-input").onchange = (e) => { uploadFiles(e.target.files); e.target.value = ""; };
  $("#dir-input").onchange = (e) => { uploadFiles(e.target.files); e.target.value = ""; };
  $("#btn-path").onclick = () => { $("#dlg-path").showModal(); $("#path-input").focus(); };
  $("#path-go").onclick = (e) => {
    e.preventDefault();
    const p = $("#path-input").value.trim();
    $("#dlg-path").close();
    if (p) scanPath(p);
  };
  $("#btn-export").onclick = openExport;
  $("#btn-update").onclick = openUpdate;
  $("#upd-go").onclick = runUpdate;
  $("#btn-url").onclick = openUrlDialog;
  $("#drop-url").onclick = openUrlDialog;
  $("#url-go").onclick = startCrawl;
  $("#url-cancel").onclick = cancelCrawl;
  $("#url-input").addEventListener("keydown", (e) => { if (e.key === "Enter") startCrawl(e); });
  $("#export-go").onclick = doExport;
  $("#export-zip").onclick = doExportZip;
  $("#btn-download").onclick = downloadCleaned;
  $("#sel-rec").onclick = () => setSelection("rec");
  $("#sel-all").onclick = () => setSelection("all");
  $("#sel-none").onclick = () => setSelection("none");
  $("#btn-clear").onclick = async () => {
    await api("/api/clear", { body: {} }).catch(() => {});
    state.files = []; state.selected = null; state.choice = {};
    renderAll();
  };
  $("#file-list").onclick = async (e) => {
    const group = e.target.closest("li.group");
    if (group && e.target.closest(".g-remove")) {
      const ids = state.files.filter((f) => f.batch?.id === group.dataset.batch).map((f) => f.file_id);
      await api("/api/remove", { body: { ids } }).catch(() => {});
      state.files = state.files.filter((f) => !ids.includes(f.file_id));
      ids.forEach((id) => delete state.choice[id]);
      if (ids.includes(state.selected)) state.selected = state.files[0]?.file_id || null;
      renderAll();
      return;
    }
    if (group) {
      const id = group.dataset.batch;
      if (state.collapsed.has(id)) state.collapsed.delete(id); else state.collapsed.add(id);
      renderSidebar();
      return;
    }
    const li = e.target.closest("li[data-id]");
    if (!li) return;
    state.selected = li.dataset.id;
    renderAll();
  };
  $$(".tab").forEach((t) => (t.onclick = () => { state.tab = t.dataset.tab; renderDetail(); }));
  $("#tab-findings").addEventListener("change", (e) => {
    const cb = e.target.closest("input[data-fid]");
    if (!cb) return;
    const set = state.choice[state.selected];
    if (cb.checked) set.add(cb.dataset.fid); else set.delete(cb.dataset.fid);
  });
  $("#tab-findings").addEventListener("click", (e) => {
    const b = e.target.closest("[data-show]");
    if (!b) return;
    state.tab = "document";
    renderDetail();
    renderDocument(current(), b.dataset.show);
  });
  $("#tab-document").addEventListener("click", (e) => {
    const m = e.target.closest("[data-card]");
    if (!m) return;
    state.tab = "findings";
    renderDetail();
    const card = document.getElementById("card-" + m.dataset.card);
    if (card) { card.scrollIntoView({ block: "center" }); card.animate([{ outline: "3px solid var(--accent)" }, { outline: "0" }], 1600); }
  });
  // drag & drop anywhere
  let depth = 0;
  document.addEventListener("dragenter", (e) => { if (e.dataTransfer.types.includes("Files")) { depth++; document.body.classList.add("drag"); } });
  document.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) document.body.classList.remove("drag"); });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", async (e) => {
    e.preventDefault();
    depth = 0;
    document.body.classList.remove("drag");
    const files = await collectDropped(e.dataTransfer);
    uploadFiles(files);
  });
}

// Supports dropped folders through the entries API.
async function collectDropped(dt) {
  const entries = Array.from(dt.items || []).map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return Array.from(dt.files);
  const out = [];
  const walk = (entry, prefix) => new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((file) => {
        Object.defineProperty(file, "webkitRelativePath", { value: prefix + file.name });
        out.push(file);
        resolve();
      }, () => resolve());
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const read = () => reader.readEntries(async (batch) => {
        if (!batch.length) {
          for (const b of all) await walk(b, prefix + entry.name + "/");
          resolve();
        } else { all.push(...batch); read(); }
      }, () => resolve());
      read();
    } else resolve();
  });
  for (const en of entries) await walk(en, "");
  const ok = /\.(pdf|md|markdown|mdown|mkd|mdx|txt|text|log|csv|tsv|json|jsonl|xml|ya?ml|ini|cfg|rst|tex|srt|vtt|html?|xhtml|svg|eml)$/i;
  return out.filter((f) => ok.test(f.name));
}

async function init() {
  initLang();
  initTheme();
  initEvents();
  try {
    state.info = await api("/api/info");
    const existing = await api("/api/files");
    existing.results.forEach(addResult);
    sortFiles();
    state.selected = state.files[0]?.file_id || null;
    const newest = groupFiles().find((g) => g.batch);
    if (newest) {  // after a reload only the latest scan is unfolded, with its riskiest file selected
      focusBatch(newest.id);
      state.selected = newest.files[0].file_id;
    }
    // Deep links: #file=<name>&tab=document
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("file")) {
      const hit = state.files.find((f) => f.name === h.get("file"));
      if (hit) state.selected = hit.file_id;
    }
    if (["findings", "document", "preview"].includes(h.get("tab"))) state.tab = h.get("tab");
  } catch (e) {
    toast(t("server_failed") + e.message, true);
  }
  renderAll();
}

init();
