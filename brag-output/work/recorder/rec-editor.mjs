import { chromium } from "playwright-core";
import fs from "node:fs";
import { SP, setup, installCursor, moveCursor } from "./stubs.mjs";
import { installEditorHelpers } from "./editor-helpers.mjs";
import { recordFrames, path, pressScale } from "./rec-common.mjs";
const tex = fs.readFileSync(`${SP}/tex/editor.tex`, "utf8");
let gateOpen = 0;
const waiters = [];
const compileGate = () => new Promise((res) => { const idx = waiters.length; waiters.push(res); if (idx < gateOpen) res(); });
const openGate = () => { gateOpen++; waiters.slice(0, gateOpen).forEach((r) => r()); };
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] });
const ctx = await setup(browser, { width: 1680, height: 767, tex, compileGate });
const page = await ctx.newPage();
await page.goto("http://localhost:3000/editor/p1", { waitUntil: "networkidle", timeout: 120000 });
await page.waitForFunction(() => window.monaco && window.monaco.editor.getEditors()[0]?.getValue().includes("Methodology"), null, { timeout: 60000 });
await page.waitForTimeout(1500);
await installCursor(page);
await installEditorHelpers(page);
await page.evaluate(() => window.__presence(false, []));
const cb = await page.getByRole("button", { name: /^Compile$/ }).first().boundingBox();
const CBX = cb.x + cb.width / 2, CBY = cb.y + cb.height / 2;
const pdfSrc = () => page.evaluate(() => [...document.querySelectorAll("img")].filter((i) => { const b = i.getBoundingClientRect(); return b.x > 780 && b.width > 400 && i.complete && i.naturalWidth > 0; }).map((i) => i.src).join("|"));
async function waitPdfChange(prev) {
  await page.waitForFunction((prev) => {
    const s = [...document.querySelectorAll("img")].filter((i) => { const b = i.getBoundingClientRect(); return b.x > 780 && b.width > 400 && i.complete && i.naturalWidth > 0; }).map((i) => i.src).join("|");
    return s && s !== prev;
  }, prev, { timeout: 90000, polling: 200 });
  await page.waitForTimeout(1500);
}
// --- schedule (scene-local seconds) ---
const CLICK1 = 1.08, GATE1 = 1.6, CLICK2 = 7.08, GATE2 = 7.6;
const mouse = [[0, 1180, 560], [0.3, 1180, 560], [0.95, CBX, CBY], [1.3, CBX, CBY], [1.9, 930, 640], [6.45, 930, 640], [6.98, CBX, CBY], [7.35, CBX, CBY], [7.95, 1250, 748], [9.8, 1250, 748], [10.3, 1495, 734], [11, 1495, 734]];
const MIA_SEL = "Seminar \\& Project Report:".length;
const MIA_TXT = ", Mia Chen";
const SAM_HEAD = "\\section{Conclusion}";
const SAM_TXT = "Co-authors see every keystroke live.";
const typed = (t, t0, per, len) => (t < t0 ? 0 : Math.min(len, Math.floor((t - t0) / per + 1e-6) + 1));
const base = tex.split("\n");               // 1-based line n is base[n-1]
const AUTHOR = base[6];                     // \author{Alex Rivers, Sam Vance}
function want(t) {
  const lines = base.slice(0, 25);          // lines 1-25
  lines[6] = AUTHOR.slice(0, -1) + MIA_TXT.slice(0, typed(t, 3.9, 0.1, MIA_TXT.length)) + "}";
  lines.push("");                           // 26
  if (t >= 3.0) lines.push(SAM_HEAD.slice(0, typed(t, 3.1, 0.06, SAM_HEAD.length)));
  if (t >= 4.35) lines.push(SAM_TXT.slice(0, typed(t, 4.45, 0.05, SAM_TXT.length)));
  lines.push("\\end{document}", "");
  return lines.join("\n");
}
function carets(t) {
  if (t < 2.72) return [];
  const out = [];
  if (t < 3.81) {
    const c = 8 + Math.min(MIA_SEL, Math.floor(((t - 2.72) / 0.48) * MIA_SEL));
    out.push(c > 8 ? { id: 202, line: 6, col: c, selFrom: { line: 6, col: 8 } } : { id: 202, line: 6, col: 8 });
  } else out.push({ id: 202, line: 7, col: AUTHOR.length + typed(t, 3.9, 0.1, MIA_TXT.length) });
  if (t < 3.0) out.push({ id: 201, line: 26, col: 1 });
  else if (t < 4.35) out.push({ id: 201, line: 27, col: typed(t, 3.1, 0.06, SAM_HEAD.length) + 1 });
  else out.push({ id: 201, line: 28, col: typed(t, 4.45, 0.05, SAM_TXT.length) + 1 });
  return out;
}
const st = { clicked1: false, clicked2: false, gate1: false, gate2: false };
let prevSrc = "", fixes = 0;
await recordFrames(page, `${SP}/frames/editor`, 10.95, async (t) => {
  const [mx, my] = path(mouse, t);
  await moveCursor(page, mx, my, pressScale([CLICK1, CLICK2], t));
  if (!st.clicked1 && t >= CLICK1) { st.clicked1 = true; prevSrc = await pdfSrc(); await page.mouse.down(); await page.mouse.up(); await page.waitForTimeout(250); }
  if (!st.gate1 && t >= GATE1) { st.gate1 = true; openGate(); await waitPdfChange(prevSrc); }
  if (!st.clicked2 && t >= CLICK2) { st.clicked2 = true; prevSrc = await pdfSrc(); await page.mouse.down(); await page.mouse.up(); await page.waitForTimeout(250); }
  if (!st.gate2 && t >= GATE2) { st.gate2 = true; openGate(); await waitPdfChange(prevSrc); }
  const peers = t >= 2.45 ? [201, 202] : t >= 2.17 ? [201] : [];
  await page.evaluate(([live, peers]) => window.__presence(live, peers), [t >= 2.17, peers]);
  if (await page.evaluate((w) => window.__setDoc(w), want(t))) fixes++;
  await page.evaluate((c) => window.__setCarets(c), carets(t));
}, async (t) => (await page.evaluate(() => window.__ed().getValue())) === want(t));
console.log("doc edits applied:", fixes);
console.log("final doc ok:", (await page.evaluate(() => window.__ed().getValue())) === want(10.95));
await browser.close();
