import { chromium } from "playwright-core";
import { SP, setup, installCursor, moveCursor } from "./stubs.mjs";
import { recordFrames, path, pressScale, ease } from "./rec-common.mjs";
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox"] });
const ctx = await setup(browser, { width: 1680, height: 767, tex: "" });
const page = await ctx.newPage();
await page.goto("http://localhost:3000/dashboard", { waitUntil: "networkidle", timeout: 120000 });
await page.waitForTimeout(3000);
await installCursor(page);
const conv = await page.getByText("Import PDF & Convert").first().boundingBox();
const CX = conv.x + 90, CY = conv.y + conv.height / 2 + 4;
console.log("click target", CX, CY);
// Scroll down to the project grid and back up; hover the Seminar Report card on the way
const scrollAt = (t) => {
  const S = 420;
  if (t < 0.8) return 0;
  if (t < 2.2) return S * ease((t - 0.8) / 1.4);
  if (t < 2.5) return S;
  if (t < 3.4) return S * (1 - ease((t - 2.5) / 0.9));
  return 0;
};
const mouse = [[0, 1180, 640], [0.75, 1180, 640], [2.2, 700, 330], [2.5, 700, 330], [3.5, CX, CY], [5.6, CX, CY]];
await recordFrames(page, `${SP}/frames/dash`, 5.5, async (t) => {
  const y = Math.round(scrollAt(t));
  await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), y);
  const [x, yy] = path(mouse, t);
  await moveCursor(page, x, yy, pressScale([4.09], t));
});
await browser.close();
