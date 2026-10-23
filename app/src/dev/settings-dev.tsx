// Prévia das Configurações no NAVEGADOR, sem Electron e sem núcleo: usa o núcleo de mentira dos testes.
// Só para ver e clicar na interface durante o desenvolvimento (npm run dev:web). Não entra no app instalado.
import { installFakeCore } from "../../tests/fakeCore";
import type { Theme } from "../shared/theme";
import { persistFake } from "./persist";

const params = new URLSearchParams(location.search);
let theme: Theme = params.get("theme") === "dark" ? "dark" : "light";
const listeners = new Set<(t: Theme) => void>();

const core = installFakeCore({ ollamaRunning: params.get("ollama") !== "off" });
persistFake(core);
if (!params.get("theme")) theme = core.effective["app.tema"] === "escuro" ? "dark" : core.effective["app.tema"] === "claro" ? "light" : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
Object.assign(window.fidus, {
  getTheme: async () => theme,
  onThemeChange: (cb: (t: Theme) => void) => { listeners.add(cb); return () => listeners.delete(cb); },
  onNavigate: (cb: (p: string) => void) => { const on = () => cb(location.hash.slice(1)); window.addEventListener("hashchange", on); return () => window.removeEventListener("hashchange", on); },
});

// No app real o Electron aplica o seletor "Tema" das Configurações; aqui fazemos o mesmo.
const setTheme = (t: Theme) => { theme = t; listeners.forEach((cb) => cb(t)); };
const original = window.fidus.command;
window.fidus.command = async (name, args) => {
  const reply = await original(name, args);
  const tema = (args as { patch?: Record<string, unknown> } | undefined)?.patch?.["app.tema"];
  if (name === "set_settings" && reply.ok && tema) setTheme(tema === "claro" ? "light" : tema === "escuro" ? "dark" : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  return reply;
};

const bar = document.createElement("button");
bar.textContent = "Alternar claro/escuro";
bar.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:99;padding:8px 12px;border-radius:10px;border:1px solid #888;background:#fff;color:#111;cursor:pointer";
bar.onclick = () => setTheme(theme === "dark" ? "light" : "dark");
document.body.append(bar);

void import("../settings/main");
