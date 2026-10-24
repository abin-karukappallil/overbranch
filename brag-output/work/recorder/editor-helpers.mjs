// Page-side helpers for the editor recording: presence bar in its "Live" state and
// remote carets drawn exactly as lib/collab/monaco-binding.ts draws them.
export async function installEditorHelpers(page) {
  await page.evaluate(() => {
    const W = window;
    W.__ed = () => W.monaco.editor.getEditors()[0];
    W.__peers = {
      201: { name: "Sam Vance", solid: "#F59E0B", translucent: "rgba(245, 158, 11, 0.22)", initials: "SV" },
      202: { name: "Mia Chen", solid: "#06B6D4", translucent: "rgba(6, 182, 212, 0.22)", initials: "MC" },
    };
    const style = document.createElement("style");
    style.id = "ob-collab-remote-cursor-styles";
    style.textContent = Object.entries(W.__peers).map(([id, p]) => `
.ob-remote-selection-${id} { background-color: ${p.translucent}; }
.ob-remote-head-${id} { position: relative; border-left: 2px solid ${p.solid}; box-sizing: border-box; }
.ob-remote-head-${id}::after { content: '${p.name}'; position: absolute; left: -2px; top: -1.25em; padding: 0 4px; border-radius: 4px 4px 4px 0; background-color: ${p.solid}; color: #fff; font-size: 10px; line-height: 1.25em; font-family: var(--font-space-mono), ui-monospace, monospace; white-space: nowrap; pointer-events: none; z-index: 30; opacity: 1; }`).join("\n");
    document.head.appendChild(style);
    W.__deco = null;
    // carets: [{id, line, col, selFrom?:{line,col}}]
    W.__setCarets = (carets) => {
      const ed = W.__ed();
      const ds = [];
      for (const c of carets) {
        if (c.selFrom) ds.push({ range: new W.monaco.Range(c.selFrom.line, c.selFrom.col, c.line, c.col), options: { className: `ob-remote-selection ob-remote-selection-${c.id}` } });
        ds.push({ range: new W.monaco.Range(c.line, c.col, c.line, c.col), options: { className: `ob-remote-head ob-remote-head-${c.id}` } });
      }
      if (!W.__deco) W.__deco = ed.createDecorationsCollection(ds); else W.__deco.set(ds);
    };
    W.__insert = (line, col, text) => {
      const ed = W.__ed();
      ed.getModel().applyEdits([{ range: new W.monaco.Range(line, col, line, col), text }]);
    };
    // Bring the buffer to exactly `want` with one minimal edit (common prefix/suffix kept)
    W.__setDoc = (want) => {
      const m = W.__ed().getModel();
      const cur = m.getValue();
      if (cur === want) return false;
      let p = 0;
      while (p < cur.length && p < want.length && cur[p] === want[p]) p++;
      let s = 0;
      while (s < cur.length - p && s < want.length - p && cur[cur.length - 1 - s] === want[want.length - 1 - s]) s++;
      const a = m.getPositionAt(p), b = m.getPositionAt(cur.length - s);
      m.applyEdits([{ range: new W.monaco.Range(a.lineNumber, a.column, b.lineNumber, b.column), text: want.slice(p, want.length - s) }]);
      return true;
    };
    // Presence bar: live dot + peer avatars (CollabPresenceBar markup), self initials "AR"
    W.__presence = (live, peerIds) => {
      const bar = document.querySelector('[data-testid="collab-presence-bar"]');
      if (!bar) return false;
      const status = bar.children[0];
      const wantLive = live ? "1" : "0";
      if (status.dataset.rec !== wantLive) {
        if (live) {
          status.className = "flex items-center gap-1 text-emerald-600 dark:text-[#10B981]";
          status.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-3 h-3"><path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.859a10 10 0 0 1 14 0"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/></svg><span class="hidden lg:inline">Live</span>';
        }
        status.dataset.rec = wantLive;
      }
      const avatars = bar.querySelector(".-space-x-1\\.5") || bar.children[2];
      const self = avatars.children[0]?.firstElementChild;
      if (self && self.textContent !== "AR") self.textContent = "AR";
      for (const id of Object.keys(W.__peers)) {
        const want = peerIds.includes(Number(id));
        let el = avatars.querySelector(`[data-rec-peer="${id}"]`);
        if (want && !el) {
          const p = W.__peers[id];
          el = document.createElement("div");
          el.className = "relative";
          el.dataset.recPeer = id;
          el.innerHTML = `<div class="w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-archivo font-bold text-white overflow-hidden ring-2 transition-opacity opacity-100" style="background-color:${p.solid};box-shadow:0 0 0 2px ${p.solid}33">${p.initials}</div>`;
          avatars.appendChild(el);
        } else if (!want && el) el.remove();
      }
      return true;
    };
  });
}
