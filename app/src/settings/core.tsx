// Conexão da janela de Configurações com o núcleo: chamadas, valores em vigor e avisos.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CommandName, CoreEvent, Reply } from "../shared/protocol";

export type Eff = Record<string, unknown>;
export interface SettingsData {
  settings: Record<string, unknown>;
  effective: Eff;
  schema: string[];
  claude_models: string[];
  restart_required: string[];
}
export interface Toast {
  id: number;
  kind: "ok" | "error" | "info";
  text: string;
}

export interface CoreApi {
  /** Chama um comando. Erros viram aviso na tela e `null`. */
  call: <T = any>(name: CommandName, args?: Record<string, unknown>, opts?: { quiet?: boolean }) => Promise<T | null>;
  /** Valor em vigor de uma configuração. */
  eff: Eff;
  /** Grava uma ou mais configurações (valida no núcleo) e atualiza a tela na hora. */
  save: (patch: Record<string, unknown>) => Promise<boolean>;
  loaded: boolean;
  claudeModels: string[];
  restartNeeded: string[];
  clearRestart: () => void;
  toasts: Toast[];
  notify: (kind: Toast["kind"], text: string) => void;
  /** Eventos do núcleo (para telas que reagem, como o medidor do microfone). */
  subscribe: (cb: (e: CoreEvent) => void) => () => void;
  characters: { id: string; name: string; call: string; is_default: boolean }[];
  reloadCharacters: () => void;
  /** "Escutar chamados" (liga/desliga a escuta por palavra de ativação). */
  calls: { enabled: boolean; until: number | null };
  setCalls: (enabled: boolean) => Promise<void>;
}

const Ctx = createContext<CoreApi | null>(null);
export const useCore = (): CoreApi => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCore fora do CoreProvider");
  return c;
};

export function CoreProvider({ children }: { children: ReactNode }) {
  const [eff, setEff] = useState<Eff>({});
  const [loaded, setLoaded] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [restart, setRestart] = useState<string[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [chars, setChars] = useState<CoreApi["characters"]>([]);
  const [calls, setCallsState] = useState<{ enabled: boolean; until: number | null }>({ enabled: true, until: null });
  const subs = useRef(new Set<(e: CoreEvent) => void>());
  const nextId = useRef(1);

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);

  const call = useCallback<CoreApi["call"]>(
    async (name, args = {}, opts) => {
      let r: Reply;
      try {
        r = await window.fidus.command(name, args);
      } catch (e) {
        r = { type: "reply", id: null, ok: false, error: String(e) };
      }
      if (!r.ok) {
        if (!opts?.quiet) notify("error", r.error ?? "Não deu certo.");
        return null;
      }
      return (r.data ?? {}) as never;
    },
    [notify],
  );

  const reloadSettings = useCallback(async () => {
    const d = await call<SettingsData>("get_settings", {}, { quiet: true });
    if (d) {
      setEff(d.effective);
      setModels(d.claude_models);
      setLoaded(true);
    }
  }, [call]);

  const reloadCharacters = useCallback(async () => {
    const d = await call<{ characters: CoreApi["characters"] }>("characters", { op: "list" }, { quiet: true });
    if (d) setChars(d.characters);
  }, [call]);

  const save = useCallback<CoreApi["save"]>(
    async (patch) => {
      const before = eff;
      setEff((e) => ({ ...e, ...patch })); // otimista: a tela muda na hora
      const r = await call<{ restart_required: string[] }>("set_settings", { patch });
      if (!r) {
        setEff(before);
        return false;
      }
      if (r.restart_required.length) setRestart((x) => [...new Set([...x, ...r.restart_required])]);
      return true;
    },
    [call, eff],
  );

  const setCalls = useCallback(
    async (enabled: boolean) => {
      const r = await call("calls", { value: enabled });
      if (r) setCallsState({ enabled, until: null });
    },
    [call],
  );

  useEffect(() => {
    void reloadSettings();
    void reloadCharacters();
    void window.fidus.getSnapshot().then((s) => s && setCallsState(s.calls));
    return window.fidus.onEvent((e) => {
      if (e.type === "ready") {
        void reloadSettings();
        void reloadCharacters();
        setCallsState(e.snapshot.calls);
      }
      if (e.type === "calls") setCallsState({ enabled: e.enabled, until: e.until });
      if (e.type === "characters_changed") void reloadCharacters();
      subs.current.forEach((cb) => cb(e));
    });
  }, [reloadSettings, reloadCharacters]);

  const value = useMemo<CoreApi>(
    () => ({
      call, eff, save, loaded, claudeModels: models, restartNeeded: restart, clearRestart: () => setRestart([]), toasts, notify,
      subscribe: (cb) => {
        subs.current.add(cb);
        return () => subs.current.delete(cb);
      },
      characters: chars, reloadCharacters: () => void reloadCharacters(), calls, setCalls,
    }),
    [call, eff, save, loaded, models, restart, toasts, notify, chars, reloadCharacters, calls, setCalls],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
