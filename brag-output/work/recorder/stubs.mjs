import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
export const SP = process.env.REC_SP || new URL(".", import.meta.url).pathname; // working dir: tex/, frames/
const now = "2026-10-20T10:00:00.000Z";
const user = { id: "u1", name: "Alex Rivers", email: "alex@example.com", emailVerified: true, image: null, createdAt: now, updatedAt: now };
const P = (id, name, template, description, isOwner = true, role = "Owner") => ({ id, name, template, description, isOwner, role, ownerId: isOwner ? "u1" : "u2", createdAt: now, updatedAt: now, lastEdited: now, isFavorite: false, memberCount: 3 });
const projects = [
  P("p1", "Seminar Report", "Seminar Report", "Modern Machine Learning Systems"),
  P("p2", "Byzantine Fault-Tolerant Consensus", "IEEE Paper", "Journal paper, IEEEtran"),
  P("p3", "Final Year Project Thesis", "Thesis", "University dissertation"),
  P("p4", "Linear Algebra Assignment 3", "Assignment", "Problem set"),
  P("p5", "Lab Slides Week 9", "Beamer", "Beamer presentation"),
  P("p6", "Graph Neural Networks Survey", "IEEE Paper", "Shared literature review", false, "Editor"),
];
const members = [
  { id: "m1", userId: "u1", name: "Alex Rivers", email: "alex@example.com", role: "Owner", image: null },
  { id: "m2", userId: "u2", name: "Sam Vance", email: "sam@example.com", role: "Editor", image: null },
  { id: "m3", userId: "u3", name: "Mia Chen", email: "mia@example.com", role: "Editor", image: null },
];
const proc = {
  "projects.listProjects": projects,
  "projects.getById": { ...projects[0], role: "Owner", isOwner: true, members },
  "projects.getMembers": members,
  "invitations.listPending": [],
  "notifications.unreadCount": 0,
  "notifications.listNotifications": [],
  "templates.listTemplates": [],
};
let n = 0;
export function compileTex(code) {
  const dir = path.join(SP, "tex", "build", String(n++));
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "main.tex"), code);
  try { execFileSync("pdflatex", ["-interaction=nonstopmode", "-halt-on-error", "main.tex"], { cwd: dir, stdio: "ignore", timeout: 60000 }); } catch {}
  return fs.readFileSync(path.join(dir, "main.pdf")).toString("base64");
}
// opts.tex: initial main.tex; opts.compileGate: async () => void, awaited before a compile answers
export async function setup(browser, { width, height, tex, compileGate }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 2, colorScheme: "dark" });
  await ctx.addCookies([
    { name: "better-auth.session_token", value: "stub", url: "http://localhost:3000" },
    { name: "ob_guest_token", value: "stub", url: "http://localhost:3000" },
  ]);
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem("theme", "dark");
      localStorage.setItem("overbranch_cookie_consent", JSON.stringify({ status: "essential", analytics: false, timestamp: Date.now() }));
    } catch {}
    document.addEventListener("DOMContentLoaded", () => {
      const st = document.createElement("style");
      st.textContent = 'a[href="https://upzare.com"]{visibility:hidden!important} [data-sonner-toaster]{display:none!important} nextjs-portal{display:none!important}';
      document.head.appendChild(st);
    });
  });
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await ctx.route("**/*", async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.startsWith("/api/auth/")) return json(route, { session: { id: "s1", userId: "u1", expiresAt: "2027-01-01T00:00:00.000Z", token: "stub", createdAt: now, updatedAt: now }, user });
    if (u.pathname.startsWith("/api/trpc/")) {
      const names = decodeURIComponent(u.pathname.slice("/api/trpc/".length)).split(",");
      const out = names.map((nm) => ({ result: { data: { json: proc[nm] ?? null } } }));
      return json(route, u.searchParams.get("batch") ? out : out[0]);
    }
    if (u.pathname.startsWith("/api/projects/get-file")) return json(route, { raw_code: tex });
    if (u.pathname.endsWith("/api/projects/list-files")) return json(route, { files: [
      { path: "main.tex", name: "main.tex", size: 812, type: "document", ext: ".tex" },
      { path: "refs.bib", name: "refs.bib", size: 2304, type: "document", ext: ".bib" },
      { path: "figures/architecture.png", name: "architecture.png", size: 48211, type: "image", ext: ".png" },
      { path: "figures/results.png", name: "results.png", size: 39120, type: "image", ext: ".png" },
    ] });
    if (u.pathname.endsWith("/api/compile")) {
      const body = JSON.parse(route.request().postData() || "{}");
      if (compileGate) await compileGate();
      return json(route, { success: true, pdf_base64: compileTex(body.latex_code || tex) });
    }
    if (u.pathname.endsWith("/api/projects/save-file")) return json(route, { success: true });
    if (u.host === "cdn.jsdelivr.net") return route.continue();
    if (u.host !== "localhost:3000") { if (process.env.LOGABORT) console.log("abort", u.href.slice(0, 140)); return route.abort(); }
    if (u.pathname.startsWith("/api/")) return json(route, {}, 404);
    return route.continue();
  });
  return ctx;
}
// White arrow cursor (same shape as the composition's), drawn into the page so it is in every frame
export async function installCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById("rec-cursor")) return;
    const d = document.createElement("div");
    d.id = "rec-cursor";
    d.style.cssText = "position:fixed;left:0;top:0;width:22px;height:31px;z-index:2147483647;pointer-events:none;transform-origin:2px 2px;will-change:transform";
    d.innerHTML = '<svg viewBox="0 0 30 42" width="22" height="31"><path d="M2 2 L2 34 L10 26 L16 40 L22 37 L16 24 L27 24 Z" fill="#ffffff" stroke="#000000" stroke-width="2.5" stroke-linejoin="round"/></svg>';
    document.body.appendChild(d);
  });
}
export async function moveCursor(page, x, y, scale = 1, opacity = 1) {
  await page.mouse.move(x, y);
  await page.evaluate(([x, y, s, o]) => {
    const d = document.getElementById("rec-cursor");
    d.style.transform = `translate(${x - 2}px, ${y - 2}px) scale(${s})`;
    d.style.opacity = String(o);
  }, [x, y, scale, opacity]);
}
export const frameSettle = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))));
