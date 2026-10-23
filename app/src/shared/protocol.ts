// Espelho do protocolo do núcleo (docs/PROTOCOLO.md, versão 1). Mantenha igual a fidus/core/bridge/protocol.py.
export const PROTOCOL_VERSION = 1;

export type UiState = "idle" | "listening" | "thinking" | "speaking" | "muted";
export type MicState = "passive" | "recording" | "paused" | "muted" | "off";
export type CoreStatus = "starting" | "ready" | "error";

export interface RingColors {
  dark: string[];
  light: string[];
}
export interface CharacterInfo {
  id: string;
  name: string;
  call: string;
  ring: RingColors;
}
export interface ModelInfo {
  provider: string;
  name: string;
  where: string;
}
export interface CallsInfo {
  enabled: boolean;
  until: number | null;
}
export interface Snapshot {
  status: CoreStatus;
  message: string;
  state: UiState;
  mic: MicState;
  character: CharacterInfo;
  default_character: string;
  characters: CharacterInfo[];
  model: ModelInfo;
  calls: CallsInfo;
  muted: boolean;
}

export type CoreEvent =
  | { type: "ready"; protocol: number; snapshot: Snapshot }
  | { type: "status"; core: CoreStatus; message: string }
  | { type: "state"; state: UiState; mic: MicState }
  | { type: "level"; values: number[] }
  | { type: "caption"; role: "user" | "assistant"; text: string; final: boolean }
  | ({ type: "character" } & CharacterInfo)
  | { type: "confirm"; id: string; text: string }
  | { type: "confirm_done"; id: string }
  | ({ type: "model" } & ModelInfo)
  | { type: "calls"; enabled: boolean; until: number | null }
  | { type: "settings"; changed: string[] }
  | { type: "characters_changed"; id: string }
  | { type: "memory_changed" }
  | { type: "accounts"; service: string; status: "connected" | "disconnected" | "error"; message: string }
  | { type: "error"; message: string };

export const COMMANDS = [
  "get_state",
  "mute",
  "pause",
  "calls",
  "set_default_character",
  "confirm_reply",
  "get_settings",
  "set_settings",
  "ping",
  "quit",
  "characters",
  "memory",
  "accounts",
  "privacy",
  "about",
  "voices",
  "devices",
  "api_key",
  "local_models",
  "simulate",
] as const;
export type CommandName = (typeof COMMANDS)[number];

export interface Reply {
  type: "reply";
  id: string | null;
  ok: boolean;
  data?: Record<string, unknown>;
  error?: string;
}

/** API mínima que o preload expõe ao renderer. O renderer nunca vê o token nem fala com o núcleo diretamente. */
export interface FidusApi {
  onEvent(cb: (e: CoreEvent) => void): () => void;
  command(name: CommandName, args?: Record<string, unknown>): Promise<Reply>;
  getSnapshot(): Promise<Snapshot | null>;
  closeWindow(): void;
  getTheme(): Promise<"light" | "dark">;
  onThemeChange(cb: (t: "light" | "dark") => void): () => void;
  // --- só a janela de Configurações (o processo principal confere de quem veio o pedido) ---
  pickFolder(): Promise<string | null>;
  pickSavePath(suggestedName: string, ext: string): Promise<string | null>;
  saveTextFile(suggestedName: string, content: string): Promise<boolean>;
  openPath(kind: "data" | "log"): Promise<boolean>;
  openMicSettings(): Promise<void>;
  micStatus(): Promise<string>;
  restartCore(): Promise<void>;
  copyText(text: string): Promise<void>;
  onNavigate(cb: (page: string) => void): () => void;
}

declare global {
  interface Window {
    fidus: FidusApi;
  }
}
