// Drives headless Chrome through the Chrome DevTools Protocol (no dependencies).
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import path from "node:path";
import fs from "node:fs";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const APP = process.argv[2];
const SAMPLE = process.argv[3];
const OUT = process.argv[4];
const prof = fs.mkdtempSync(path.join(process.env.TEMP, "cdp-"));
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9339",
  `--user-data-dir=${prof}`, "--window-size=1300,900", "about:blank"], { stdio: "ignore" });

let ws, id = 0;
const pending = new Map();
const errors = [];
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch("http://127.0.0.1:9339/json")).json();
      const page = list.find((t) => t.type === "page");
      if (page) {
        ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((r) => (ws.onopen = r));
        ws.onmessage = (ev) => {
          const msg = JSON.parse(ev.data);
          if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
          if (msg.method === "Runtime.exceptionThrown") errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
          if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") errors.push(JSON.stringify(msg.params.args.map((a) => a.value)));
        };
        return;
      }
    } catch (e) { /* not ready */ }
    await sleep(200);
  }
  throw new Error("chrome not reachable");
}
function send(method, params = {}) {
  return new Promise((resolve) => { const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({ id: i, method, params })); });
}
async function js(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || "eval error");
  return r.result.result.value;
}
async function waitFor(expr, ms = 15000) {
  const t = Date.now();
  while (Date.now() - t < ms) { if (await js(expr)) return true; await sleep(150); }
  throw new Error("timeout waiting for " + expr);
}
const results = [];
function check(name, ok, info = "") { results.push(`${ok ? "PASS" : "FAIL"}  ${name} ${info}`); }

try {
  await connect();
  await send("Runtime.enable");
  await send("Page.enable");
  await send("DOM.enable");
  await send("Page.navigate", { url: APP });
  await waitFor("document.readyState === 'complete' && !!document.querySelector('#file-list')");
  await js("fetch('/api/clear',{method:'POST',headers:{'X-PIF-Token':document.querySelector('meta[name=pif-token]').content,'Content-Type':'application/json'},body:'{}'}).then(()=>location.reload())");
  await sleep(800);
  await waitFor("document.readyState === 'complete' && !document.querySelector('#dropzone').hidden");
  check("dropzone visible when empty", true);

  // upload through the real file input
  const doc = await send("DOM.getDocument", { depth: -1 });
  const q = await send("DOM.querySelector", { nodeId: doc.result.root.nodeId, selector: "#file-input" });
  await send("DOM.setFileInputFiles", { nodeId: q.result.nodeId, files: SAMPLE.split(",") });
  await waitFor("document.querySelectorAll('#file-list li').length >= 2");
  const items = await js("Array.from(document.querySelectorAll('#file-list li')).map(li => li.innerText.replace(/\\s+/g,' '))");
  check("upload via file input", items.length >= 2, JSON.stringify(items));
  check("dangerous file sorted first", /Gefährlich/.test(items[0]));

  // select markdown attack file
  await js("Array.from(document.querySelectorAll('#file-list li')).find(li => li.innerText.includes('angriff_rezept')).click()");
  await waitFor("document.querySelector('#d-name').textContent.includes('angriff_rezept')");
  const cards = await js("document.querySelectorAll('.finding').length");
  check("finding cards rendered", cards >= 5, `(${cards})`);
  const checked = await js("document.querySelectorAll('.finding input:checked').length");
  check("recommended preselected", checked >= 5, `(${checked})`);

  // 'Im Dokument zeigen'
  await js("document.querySelector('[data-show]').click()");
  await waitFor("document.querySelector('.docview mark') !== null");
  const marks = await js("document.querySelectorAll('.docview mark').length");
  check("document view highlights", marks >= 5, `(${marks})`);
  const flash = await js("document.querySelectorAll('.docview mark.flash').length");
  check("jump to finding flashes mark", flash >= 1);

  // click a mark -> back to finding card
  await js("document.querySelector('.docview mark').click()");
  await waitFor("!document.querySelector('#tab-findings').hidden");
  check("mark click returns to findings", true);

  // deselect all -> preview keeps attack
  await js("document.querySelector('#sel-none').click()");
  await js("document.querySelector('[data-tab=preview]').click()");
  await waitFor("document.querySelector('#tab-preview .note') !== null");
  const p0 = await js("document.querySelector('#tab-preview .note').innerText");
  check("preview with nothing selected keeps risk", /0<\/b>|^0 Fund|0 Fund/.test(p0) && /Gefährlich/.test(p0), p0.slice(0, 90));

  // select recommended -> clean
  await js("document.querySelector('#sel-rec').click(); document.querySelector('[data-tab=preview]').click()");
  await waitFor("document.querySelector('#tab-preview .note.ok') !== null");
  const p1 = await js("document.querySelector('#tab-preview').innerText");
  check("preview after cleaning is clean", /Unauffällig/.test(p1) && !p1.includes("Ignore all previous"));

  // PDF view with overlays
  await js("Array.from(document.querySelectorAll('#file-list li')).find(li => li.innerText.includes('.pdf')).click()");
  await js("document.querySelector('[data-tab=document]').click()");
  await waitFor("document.querySelector('.pdf-page img') && document.querySelector('.pdf-page img').complete && document.querySelector('.pdf-page img').naturalWidth > 0");
  const hl = await js("document.querySelectorAll('.pdf-hl').length");
  check("pdf page rendered with overlays", hl >= 5, `(${hl})`);

  // export dialog
  await js("document.querySelector('#btn-export').click()");
  await waitFor("document.querySelector('#dlg-export').open");
  await js(`document.querySelector('#export-dir').value = ${JSON.stringify(OUT)}; document.querySelector('#export-go').click()`);
  await waitFor("document.querySelector('#export-result .note') !== null", 60000);
  const ex = await js("document.querySelector('#export-result').innerText");
  check("export dialog writes folder", /Export abgeschlossen/.test(ex), ex.replace(/\s+/g, " ").slice(0, 160));
  check("export folder exists", fs.existsSync(path.join(OUT, "report.html")) && fs.existsSync(path.join(OUT, "bereinigt")));

  // ZIP download straight from the browser
  const dl = path.join(OUT, "_downloads");
  fs.mkdirSync(dl, { recursive: true });
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: dl });
  await js("document.querySelector('#export-zip').click()");
  await waitFor("/ZIP mit/.test(document.querySelector('#export-result').innerText)", 60000);
  for (let i = 0; i < 40 && !fs.existsSync(path.join(dl, "PromptInjectionFinder_Export.zip")); i++) await sleep(250);
  check("zip download via browser", fs.existsSync(path.join(dl, "PromptInjectionFinder_Export.zip")));

  // website scan through the dialog (optional 5th argument: URL)
  const SITE = process.argv[5];
  if (SITE) {
    await js("document.querySelector('#dlg-export').open && document.querySelector('#dlg-export').close()");
    const before = await js("document.querySelectorAll('#file-list li').length");
    await js("document.querySelector('#btn-url').click()");
    await waitFor("document.querySelector('#dlg-url').open");
    await js(`document.querySelector('#url-input').value = ${JSON.stringify(SITE)}; document.querySelector('#url-depth').value = '1'; document.querySelector('#url-go').click()`);
    await waitFor("!document.querySelector('#url-progress').hidden");
    await waitFor("document.querySelector('#url-go').hidden === false && /gescannt|Fehler/.test(document.querySelector('#url-status').innerText)", 180000);
    const status = await js("document.querySelector('#url-status').innerText");
    const after = await js("document.querySelectorAll('#file-list li').length");
    const logRows = await js("document.querySelectorAll('.crawl-log li').length");
    check("website scan via dialog", /gescannt/.test(status) && after > before, `${status} (+${after - before} Dateien, ${logRows} Protokollzeilen)`);
    const shotUrl = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(process.env.TEMP, "pif_cdp_url.png"), Buffer.from(shotUrl.result.data, "base64"));
    await js("document.querySelector('#dlg-url').close()");
    // the crawled page: preview must be readable text with tasks, not HTML
    await js("Array.from(document.querySelectorAll('#file-list li')).find(li => /Webseite|html/i.test(li.innerText) && !/angriff|harmlos/.test(li.innerText)).click()");
    await js("document.querySelector('[data-tab=preview]').click()");
    await waitFor("document.querySelector('#tab-preview .docview') !== null", 60000);
    const prev = await js("document.querySelector('#tab-preview .docview').innerText");
    check("web preview is text with tasks", /Erkannte Aufgaben/.test(prev) && !/<html|<div|<script/i.test(prev),
      prev.split("\n").filter((l) => l.startsWith("### ")).slice(0, 4).join(" | "));
    const shotPrev = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(process.env.TEMP, "pif_cdp_webprev.png"), Buffer.from(shotPrev.result.data, "base64"));
  }

  // theme toggle
  const before = await js("getComputedStyle(document.body).backgroundColor");
  await js("document.querySelector('#dlg-export').close(); document.querySelector('#btn-theme').click()");
  const after = await js("getComputedStyle(document.body).backgroundColor");
  check("theme toggle changes colors", before !== after, `${before} -> ${after}`);

  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(process.env.TEMP, "pif_cdp_final.png"), Buffer.from(shot.result.data, "base64"));
} catch (e) {
  results.push("ERROR " + e.message);
} finally {
  check("no JS errors", errors.length === 0, errors.join(" | "));
  console.log(results.join("\n"));
  try { ws?.close(); } catch (e) { /* ignore */ }
  chrome.kill();
  process.exit(results.some((r) => !r.startsWith("PASS")) ? 1 : 0);
}
