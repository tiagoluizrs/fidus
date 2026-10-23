import type { CharacterInfo, CoreEvent, MicState, ModelInfo, Snapshot, UiState, CoreStatus, CallsInfo } from "./protocol";

export interface Caption {
  text: string;
  final: boolean;
}
export interface AppModel {
  status: CoreStatus;
  message: string;
  state: UiState;
  mic: MicState;
  character: CharacterInfo | null;
  characters: CharacterInfo[];
  defaultCharacter: string;
  model: ModelInfo | null;
  calls: CallsInfo;
  user: Caption;
  assistant: Caption;
  confirm: { id: string; text: string } | null;
  error: string; // último erro do núcleo (modelo fora do ar, chave inválida...); some na próxima fala
}

export const initialModel: AppModel = {
  status: "starting",
  message: "",
  state: "idle",
  mic: "passive",
  character: null,
  characters: [],
  defaultCharacter: "alfred",
  model: null,
  calls: { enabled: true, until: null },
  user: { text: "", final: true },
  assistant: { text: "", final: true },
  confirm: null,
  error: "",
};

export function fromSnapshot(s: Snapshot): AppModel {
  return {
    ...initialModel,
    status: s.status,
    message: s.message,
    state: s.state,
    mic: s.mic,
    character: s.character,
    characters: s.characters,
    defaultCharacter: s.default_character,
    model: s.model,
    calls: s.calls,
  };
}

/** Aplica um evento do núcleo ao modelo. Função pura: o mesmo evento sempre dá o mesmo resultado. */
export function reduce(m: AppModel, e: CoreEvent): AppModel {
  switch (e.type) {
    case "ready":
      return fromSnapshot(e.snapshot);
    case "status":
      return { ...m, status: e.core, message: e.message };
    case "state":
      return { ...m, state: e.state, mic: e.mic };
    case "character":
      return { ...m, character: { id: e.id, name: e.name, call: e.call, ring: e.ring } };
    case "model":
      return { ...m, model: { provider: e.provider, name: e.name, where: e.where } };
    case "calls":
      return { ...m, calls: { enabled: e.enabled, until: e.until } };
    case "caption":
      if (e.role === "user") {
        // nova fala do usuário: começa uma troca nova, a resposta anterior some
        return { ...m, user: { text: e.text, final: e.final }, assistant: { text: "", final: true }, error: "" };
      }
      if (e.final) {
        return { ...m, assistant: { text: e.text || m.assistant.text, final: true } };
      }
      return { ...m, assistant: { text: (m.assistant.final ? "" : m.assistant.text) + e.text, final: false } };
    case "confirm":
      return { ...m, confirm: { id: e.id, text: e.text } };
    case "confirm_done":
      return m.confirm && m.confirm.id === e.id ? { ...m, confirm: null } : m;
    case "error":
      return { ...m, error: e.message };
    default:
      return m; // level, settings: tratados fora do modelo
  }
}

export function micLabel(mic: MicState): { text: string; tone: "ok" | "off" } {
  return mic === "muted" || mic === "off" ? { text: "Microfone silenciado", tone: "off" } : { text: "Microfone ativo", tone: "ok" };
}

export function modelLabel(character: CharacterInfo | null, model: ModelInfo | null): string {
  const provider = model?.provider === "claude" ? "Claude" : model?.provider === "local" ? "Local" : (model?.provider ?? "");
  return [character?.name, provider, model?.where].filter(Boolean).join(" · ");
}

export const STATE_LABEL: Record<UiState, string> = {
  idle: "",
  listening: "Ouvindo…",
  thinking: "Pensando…",
  speaking: "Falando…",
  muted: "Microfone silenciado",
};
