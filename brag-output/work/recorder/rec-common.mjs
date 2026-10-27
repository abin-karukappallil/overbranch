import fs from "node:fs";
import { frameSettle } from "./stubs.mjs";
export const FPS = 30;
export const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
// keys: [[t, x, y], ...] -> eased position at time t
export function path(keys, t) {
  if (t <= keys[0][0]) return keys[0].slice(1);
  for (let i = 1; i < keys.length; i++) {
    const [t1, x1, y1] = keys[i];
    const [t0, x0, y0] = keys[i - 1];
    if (t <= t1) { const u = t1 === t0 ? 1 : ease((t - t0) / (t1 - t0)); return [x0 + (x1 - x0) * u, y0 + (y1 - y0) * u]; }
  }
  return keys[keys.length - 1].slice(1);
}
// press: cursor dips to 0.82 for 0.08s at each click time, then springs back over 0.12s
export function pressScale(clicks, t) {
  for (const c of clicks) {
    if (t >= c && t < c + 0.08) return 1 - 0.18 * ((t - c) / 0.08);
    if (t >= c + 0.08 && t < c + 0.2) return 0.82 + 0.18 * ((t - c - 0.08) / 0.12);
  }
  return 1;
}
export async function recordFrames(page, dir, seconds, step, verify) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const n = Math.round(seconds * FPS);
  for (let i = 0; i < n; i++) {
    const t = i / FPS;
    for (let attempt = 0; ; attempt++) {
      await step(t, i);
      await frameSettle(page);
      await page.screenshot({ path: `${dir}/${String(i).padStart(5, "0")}.jpg`, quality: 95 });
      if (!verify || (await verify(t))) break;
      if (attempt >= 5) { console.log(`frame ${i}: state still drifting after retries`); break; }
      console.log(`frame ${i}: state drifted during capture, re-shooting`);
    }
    if (i % 30 === 0) console.log(`frame ${i}/${n}`);
  }
}
