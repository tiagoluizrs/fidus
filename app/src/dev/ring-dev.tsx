// Prévia do ANEL no NAVEGADOR, sem Electron e sem núcleo: encena conversas com eventos de mentira (npm run dev:web).
import { installFakeCore, makeProfile } from "../../tests/fakeCore";
import type { Theme } from "../shared/theme";

const params = new URLSearchParams(location.search);
let theme: Theme = params.get("theme") === "light" ? "light" : "dark";
const themeListeners = new Set<(t: Theme) => void>();

const core = installFakeCore();
const api = window.fidus;
Object.assign(api, {
  getTheme: async () => theme,
  onThemeChange: (cb: (t: Theme) => void) => { themeListeners.add(cb); return () => themeListeners.delete(cb); },
});
const original = api.command;
api.command = async (name, args) => {
  if (name === "confirm_reply") {
    core.emit({ type: "confirm_done", id: String((args as { id?: string })?.id) });
    core.emit({ type: "state", state: "idle", mic: "passive" });
    return { type: "reply", id: "1", ok: true, data: { accepted: true } };
  }
  return original(name, args);
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
let run = 0; // cada encenação cancela a anterior

async function conversa(user = "O que tenho na agenda hoje?", assistant = "Bom dia. Você tem duas reuniões; a primeira é às 9h.") {
  const me = ++run;
  const alive = () => me === run;
  core.emit({ type: "state", state: "listening", mic: "recording" });
  for (let i = 0; i < 60 && alive(); i++) {
    if (i % 2 === 0) core.emit({ type: "level", values: [0, 1, 2].map((k) => Math.round(Math.abs(Math.sin((i + k) / 3)) * 800) / 1000) });
    await sleep(33);
  }
  if (!alive()) return;
  core.emit({ type: "caption", role: "user", text: user, final: true });
  core.emit({ type: "state", state: "thinking", mic: "paused" });
  await sleep(1200);
  if (!alive()) return;
  core.emit({ type: "state", state: "speaking", mic: "paused" });
  for (const w of assistant.split(" ")) {
    if (!alive()) return;
    core.emit({ type: "caption", role: "assistant", text: w + " ", final: false });
    await sleep(180);
  }
  core.emit({ type: "caption", role: "assistant", text: "", final: true });
  await sleep(600);
  if (alive()) core.emit({ type: "state", state: "idle", mic: "passive" });
}

function confirmacao() {
  run++;
  core.emit({ type: "state", state: "thinking", mic: "paused" });
  core.emit({ type: "confirm", id: "c1", text: "Fidus quer abrir o regedit. Permitir?" });
}

function personagem(id: string) {
  const p = makeProfile(id);
  core.emit({ type: "character", id: p.id, name: p.name, call: p.call, ring: p.ring });
}

// painel de controle da prévia
const panel = document.createElement("div");
panel.style.cssText = "position:fixed;left:12px;bottom:12px;z-index:99;display:flex;gap:6px;flex-wrap:wrap;max-width:560px;font:13px system-ui";
const btn = (label: string, fn: () => void) => {
  const b = document.createElement("button");
  b.textContent = label;
  b.style.cssText = "padding:7px 11px;border-radius:9px;border:1px solid #888;background:#fff;color:#111;cursor:pointer";
  b.onclick = fn;
  panel.append(b);
};
btn("▶ Conversa", () => void conversa());
btn("Confirmação", confirmacao);
btn("Parar", () => { run++; core.emit({ type: "state", state: "idle", mic: "passive" }); });
btn("Silenciar", () => { run++; core.emit({ type: "state", state: "muted", mic: "muted" }); });
for (const id of ["alfred", "donna", "jarbis"]) btn(id[0].toUpperCase() + id.slice(1), () => personagem(id));
btn("Claro/escuro", () => { theme = theme === "dark" ? "light" : "dark"; themeListeners.forEach((cb) => cb(theme)); });
document.body.append(panel);

void import("../ring/main").then(() => { if (params.get("autoplay") !== "0") setTimeout(() => void conversa(), 800); });
