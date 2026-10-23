// Lógica do processo principal sem depender do Electron (para testar sem abrir janelas).
import type { Snapshot, UiState } from "../src/shared/protocol";

export interface ReadyInfo {
  port: number;
  token: string;
  protocol: number;
}

/** O núcleo anuncia `FIDUS_READY {"port":...,"token":...}` na saída padrão. Só o Electron, processo pai, lê isto. */
export function parseReadyLine(line: string): ReadyInfo | null {
  const m = /^FIDUS_READY (\{.*\})\s*$/.exec(line.trim());
  if (!m) return null;
  try {
    const o = JSON.parse(m[1]);
    if (Number.isInteger(o.port) && o.port > 0 && o.port < 65536 && typeof o.token === "string" && o.token.length >= 16) {
      return { port: o.port, token: o.token, protocol: Number(o.protocol) || 1 };
    }
  } catch {
    /* linha malformada: ignorada */
  }
  return null;
}

// ---------------------------------------------------------------- janela do anel

export interface Timers {
  set(fn: () => void, ms: number): unknown;
  clear(handle: unknown): void;
}
const realTimers: Timers = { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h as NodeJS.Timeout) };

/**
 * Ciclo de vida da janela do anel. Em repouso não existe janela nenhuma (o Chromium não ocupa memória).
 * Abre quando o Fidus deixa de estar parado; fecha depois de `idleMs` parado. Esc fecha na hora e a janela só
 * volta a abrir numa interação nova (depois de voltar a "idle").
 */
export class RingLifecycle {
  private handle: unknown = null;
  private dismissed = false;
  isOpen = false;

  constructor(
    private open: () => void,
    private close: () => void,
    private idleMs = 6000,
    private timers: Timers = realTimers,
  ) {}

  onState(state: UiState): void {
    if (state === "idle") {
      this.dismissed = false;
      if (this.isOpen && this.handle === null) {
        this.handle = this.timers.set(() => this.closeNow(), this.idleMs);
      }
      return;
    }
    this.cancel();
    if (!this.isOpen && !this.dismissed) {
      this.isOpen = true;
      this.open();
    }
  }

  /** O usuário apertou Esc. */
  dismiss(): void {
    this.dismissed = true;
    this.closeNow();
  }

  /** A janela foi fechada por fora (ex.: Alt+F4). */
  onClosedExternally(): void {
    this.cancel();
    this.isOpen = false;
    this.dismissed = true;
  }

  setIdleMs(ms: number): void {
    this.idleMs = ms;
  }

  private closeNow(): void {
    this.cancel();
    if (this.isOpen) {
      this.isOpen = false;
      this.close();
    }
  }

  private cancel(): void {
    if (this.handle !== null) {
      this.timers.clear(this.handle);
      this.handle = null;
    }
  }
}

// ---------------------------------------------------------------- menu da bandeja

export interface MenuItem {
  label?: string;
  type?: "normal" | "separator" | "checkbox" | "radio";
  checked?: boolean;
  enabled?: boolean;
  click?: () => void;
}
export interface TrayHandlers {
  command(name: string, args?: Record<string, unknown>): void;
  openSettings(page?: string): void;
  quit(): void;
}

export function statusText(s: Snapshot | null, now = Date.now()): string {
  if (!s) return "Iniciando…";
  if (s.status === "starting") return "Iniciando…";
  if (s.status === "error") return s.message ? `Erro: ${s.message}` : "Erro no núcleo";
  if (s.muted || s.state === "muted") return "Microfone silenciado";
  if (!s.calls.enabled) {
    if (s.calls.until) {
      const d = new Date(s.calls.until * 1000);
      if (d.getTime() > now) return `Chamados pausados até ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    }
    return "Chamados desligados";
  }
  const names = s.characters.map((c) => c.name).join(", ");
  return names ? `Escutando: ${names}` : "Escutando chamados";
}

export function buildTrayTemplate(s: Snapshot | null, h: TrayHandlers, now = Date.now()): MenuItem[] {
  const ready = s?.status === "ready";
  const paused = !!s && !s.calls.enabled && !!s.calls.until && s.calls.until * 1000 > now;
  const items: MenuItem[] = [
    { label: `Fidus · ${statusText(s, now)}`, enabled: false },
    { type: "separator" },
    { label: "Personagem padrão", enabled: false },
    ...(s?.characters ?? []).map<MenuItem>((c) => ({
      label: c.name,
      type: "radio",
      checked: c.id === s?.default_character,
      enabled: ready,
      click: () => h.command("set_default_character", { id: c.id }),
    })),
    { type: "separator" },
    { label: "Escutar chamados", type: "checkbox", checked: !!s?.calls.enabled, enabled: ready, click: () => h.command("calls", { value: !s?.calls.enabled }) },
    { label: "Silenciar microfone", type: "checkbox", checked: !!s?.muted, enabled: ready, click: () => h.command("mute", { value: !s?.muted }) },
    { type: "separator" },
    { label: "Abrir Configurações", click: () => h.openSettings() },
    { label: "Histórico de ações", click: () => h.openSettings("privacidade") },
    paused
      ? { label: "Retomar chamados", enabled: ready, click: () => h.command("pause", { minutes: 0 }) }
      : { label: "Pausar por 1 hora", enabled: ready, click: () => h.command("pause", { minutes: 60 }) },
    { type: "separator" },
    { label: "Sair do Fidus", click: () => h.quit() },
  ];
  return items;
}

// ---------------------------------------------------------------- segurança

/** Só páginas do próprio app (arquivos do pacote) podem falar com o processo principal. */
export function isTrustedUrl(url: string, rendererDirUrl: string): boolean {
  return url.startsWith(rendererDirUrl) && !url.slice(rendererDirUrl.length).includes("..");
}

/** Comandos que a interface pode mandar ao núcleo (o resto é recusado antes de chegar lá). */
export const ALLOWED_COMMANDS = new Set([
  "get_state", "mute", "pause", "calls", "set_default_character", "confirm_reply", "get_settings", "set_settings", "ping", "simulate",
  "characters", "memory", "accounts", "privacy", "about", "voices", "devices", "api_key", "local_models", "piper", "kokoro", "voice_cloud", "ask", "ask_audio", "browser_mic",
]);

/** Comandos que só a janela de Configurações pode mandar (o anel só precisa de confirmar, silenciar e afins). */
export const SETTINGS_ONLY_COMMANDS = new Set(["set_settings", "characters", "memory", "accounts", "privacy", "about", "voices", "devices", "api_key", "local_models", "piper", "kokoro", "voice_cloud", "get_settings"]);
// "quit" não está aqui: só a bandeja encerra o núcleo, não uma página.

// ---------------------------------------------------------------- snapshot acompanhando os eventos

import type { CoreEvent } from "../src/shared/protocol";

/** Mantém uma cópia do estado do núcleo (para o menu da bandeja) aplicando os eventos que chegam. */
export function applyEvent(s: Snapshot | null, e: CoreEvent): Snapshot | null {
  if (e.type === "ready") return e.snapshot;
  if (!s) return s;
  switch (e.type) {
    case "status":
      return { ...s, status: e.core, message: e.message };
    case "state":
      return { ...s, state: e.state, mic: e.mic, muted: e.state === "muted" };
    case "character":
      return { ...s, character: { id: e.id, name: e.name, call: e.call, ring: e.ring } };
    case "calls":
      return { ...s, calls: { enabled: e.enabled, until: e.until } };
    case "model":
      return { ...s, model: { provider: e.provider, name: e.name, where: e.where } };
    default:
      return s;
  }
}

// ---------------------------------------------------------------- opções do app vindas das configurações

export interface AppPlan {
  themeSource: "system" | "light" | "dark";
  openAtLogin: boolean;
  trayVisible: boolean;
  idleMs: number;
  icon: AppIcon;
}

export type AppIcon = "escuro" | "claro" | "colorido";
export const APP_ICONS: AppIcon[] = ["escuro", "claro", "colorido"];

/** Converte os valores em vigor (`effective` do núcleo) no que o Electron aplica na hora. */
export function planAppSettings(eff: Record<string, unknown>): AppPlan {
  const tema = eff["app.tema"];
  const idle = Number(eff["app.janela_inatividade_s"]);
  return {
    themeSource: tema === "claro" ? "light" : tema === "escuro" ? "dark" : "system",
    openAtLogin: eff["app.iniciar_com_windows"] === true,
    trayVisible: eff["app.icone_bandeja"] !== false,
    idleMs: Number.isFinite(idle) && idle >= 3 && idle <= 60 ? idle * 1000 : 6000,
    icon: APP_ICONS.includes(eff["app.icone"] as AppIcon) ? (eff["app.icone"] as AppIcon) : "colorido",
  };
}

/** Só estes endereços podem ser abertos fora do app (ajustes do Windows para o microfone). */
export const MIC_SETTINGS_URL = "ms-settings:privacy-microphone";

/** Nome de arquivo seguro sugerido ao usuário (sem pastas nem caracteres proibidos). */
export function safeFileName(name: string, fallback = "fidus"): string {
  const cleaned = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").replace(/^\.+/, "").slice(0, 80);
  return cleaned || fallback;
}
