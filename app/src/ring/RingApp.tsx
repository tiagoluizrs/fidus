import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { CoreEvent } from "../shared/protocol";
import { STATE_LABEL, initialModel, micLabel, modelLabel, reduce } from "../shared/model";
import { applyTheme } from "../shared/theme";
import type { Theme } from "../shared/theme";
import { RingCanvas } from "./RingCanvas";

const FALLBACK = { dark: ["#FF6A3D", "#FF5C9E", "#3D8BFF"], light: ["#F2541F", "#E8307F", "#1F6BF2"] };

function usePrefersReducedMotion(): boolean {
  const [v, setV] = useState(() => (typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)").matches : false));
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const q = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setV(q.matches);
    q.addEventListener?.("change", on);
    return () => q.removeEventListener?.("change", on);
  }, []);
  return v;
}

export function RingApp() {
  const [model, dispatch] = useReducer(reduce, initialModel);
  const [theme, setTheme] = useState<Theme>("dark");
  const levelRef = useRef(0);
  const reduced = usePrefersReducedMotion();

  // tema: segue o Windows ao vivo (o processo principal avisa)
  useEffect(() => {
    let alive = true;
    window.fidus.getTheme().then((t) => alive && setTheme(t));
    const off = window.fidus.onThemeChange(setTheme);
    return () => {
      alive = false;
      off();
    };
  }, []);
  useEffect(() => applyTheme(theme), [theme]);

  // eventos do núcleo
  useEffect(() => {
    let alive = true;
    window.fidus.getSnapshot().then((s) => s && alive && dispatch({ type: "ready", protocol: 1, snapshot: s }));
    const off = window.fidus.onEvent((e: CoreEvent) => {
      if (e.type === "level") levelRef.current = Math.max(...e.values, 0); // fora do React: ~37 por segundo
      else dispatch(e);
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  const answer = useCallback((value: boolean) => {
    if (model.confirm) void window.fidus.command("confirm_reply", { id: model.confirm.id, answer: value });
  }, [model.confirm]);

  // Esc fecha a janela; com uma confirmação aberta, S e N respondem
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        window.fidus.closeWindow();
      } else if (model.confirm && (ev.key === "s" || ev.key === "S")) {
        answer(true);
      } else if (model.confirm && (ev.key === "n" || ev.key === "N")) {
        answer(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [model.confirm, answer]);

  const mic = micLabel(model.mic);
  const colors = (model.character?.ring ?? FALLBACK)[theme];
  const stateText = STATE_LABEL[model.state];

  return (
    <div className="ring-screen">
      <header className="ring-top">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <defs>
              <linearGradient id="brand-g" x1="11" y1="0" x2="11" y2="22" gradientUnits="userSpaceOnUse">
                {colors.map((c, i) => (
                  <stop key={i} offset={i / Math.max(1, colors.length - 1)} stopColor={c} />
                ))}
              </linearGradient>
            </defs>
            <circle cx="11" cy="11" r="8.5" fill="none" stroke="url(#brand-g)" strokeWidth="2" />
          </svg>
          <span>Fidus</span>
        </div>
        <div className="chips">
          <div className="chip" role="status" aria-label={mic.text}>
            <span className={`dot ${mic.tone}`} aria-hidden="true" />
            <span>{mic.text}</span>
          </div>
          <div className="chip secondary">{modelLabel(model.character, model.model)}</div>
        </div>
      </header>

      <main className="ring-center">
        <RingCanvas state={model.state} colors={colors} theme={theme} levelRef={levelRef} reducedMotion={reduced} />
        <div className="state-label" aria-live="polite">{stateText}</div>
      </main>

      <section className="captions" aria-label="Legendas" aria-live="polite">
        {model.user.text && <p className="caption user">{model.user.text}</p>}
        {model.assistant.text && <p className="caption assistant">{model.assistant.text}</p>}
      </section>

      <footer className="hint">
        <kbd>Esc</kbd>
        <span>para fechar</span>
      </footer>

      {model.confirm && (
        <div className="confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-text">
          <h2 id="confirm-title">Confirmar ação</h2>
          <p id="confirm-text">{model.confirm.text}</p>
          <div className="confirm-actions">
            <button type="button" className="btn primary" onClick={() => answer(true)}>Sim (S)</button>
            <button type="button" className="btn" onClick={() => answer(false)} autoFocus>Não (N)</button>
          </div>
        </div>
      )}
    </div>
  );
}
