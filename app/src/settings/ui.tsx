// Peças de interface das Configurações: só elementos reais (botão, campo, rótulo), com foco visível.
import { forwardRef, useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";

export function Page({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="page">
      <header className="page-head">
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </header>
      {children}
    </div>
  );
}

export function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="card" aria-labelledby={id}>
      <div className="card-head">
        <h2 id={id}>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

export function Row({ label, hint, children, htmlFor }: { label: string; hint?: string; children?: ReactNode; htmlFor?: string }) {
  return (
    <div className="row">
      <div className="row-text">
        <label htmlFor={htmlFor} className="row-label">{label}</label>
        {hint && <span className="muted small">{hint}</span>}
      </div>
      <div className="row-control">{children}</div>
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`switch${checked ? " on" : ""}`} onClick={() => onChange(!checked)}>
      <span className="knob" />
    </button>
  );
}

export interface Option<T extends string | number> {
  value: T;
  label: string;
  disabled?: boolean;
}
export function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: Option<T>[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={o.value === value} disabled={o.disabled} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Slider({ label, value, min = 0, max = 100, left, right, onChange, onRestore, restoreLabel, format }: {
  label: string; value: number; min?: number; max?: number; left?: string; right?: string;
  onChange: (v: number) => void; onRestore?: () => void; restoreLabel?: string; format?: (v: number) => string;
}) {
  const [local, setLocal] = useState(value);
  const dragging = useRef(false);
  useEffect(() => {
    if (!dragging.current) setLocal(value);
  }, [value]);
  const id = useId();
  return (
    <div className="slider">
      <div className="slider-top">
        <label htmlFor={id} className="row-label">{label}</label>
        {onRestore && <button type="button" className="link" onClick={onRestore}>{restoreLabel ?? "Restaurar"}</button>}
        <span className="muted small value">{format ? format(local) : local}</span>
      </div>
      <div className="slider-body">
        {left && <span className="muted small">{left}</span>}
        <input id={id} type="range" min={min} max={max} value={local}
          onPointerDown={() => (dragging.current = true)}
          onChange={(e) => setLocal(Number(e.target.value))}
          onPointerUp={() => { dragging.current = false; onChange(local); }}
          onKeyUp={() => onChange(local)}
          onBlur={() => { if (local !== value) onChange(local); }} />
        {right && <span className="muted small">{right}</span>}
      </div>
    </div>
  );
}

export const Button = forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }>(
  function Button({ children, variant = "secondary", className, ...p }, ref) {
    return <button type="button" ref={ref} {...p} className={`btn ${variant}${className ? " " + className : ""}`}>{children}</button>;
  },
);

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "soon" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function TextField({ label, value, onCommit, placeholder, type = "text", multiline, maxLength }: {
  label: string; value: string; onCommit: (v: string) => void; placeholder?: string; type?: string; multiline?: boolean; maxLength?: number;
}) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const id = useId();
  const common = { id, value: v, placeholder, maxLength, onChange: (e: React.ChangeEvent<any>) => setV(e.target.value), onBlur: () => v !== value && onCommit(v) };
  return (
    <div className="field">
      <label htmlFor={id} className="row-label">{label}</label>
      {multiline ? <textarea rows={3} {...common} /> : <input type={type} {...common} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />}
    </div>
  );
}

/** Diálogo de confirmação acessível. O foco começa em "Cancelar" (o lado seguro). Esc cancela. */
export function ConfirmDialog({ title, text, confirmLabel, requireWord, danger, onConfirm, onCancel }: {
  title: string; text: string; confirmLabel: string; requireWord?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  const [typed, setTyped] = useState("");
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onCancel]);
  const ok = !requireWord || typed.trim().toUpperCase() === requireWord.toUpperCase();
  return (
    <div className="overlay">
      <div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="dlg-t" aria-describedby="dlg-d">
        <h2 id="dlg-t">{title}</h2>
        <p id="dlg-d" className="muted">{text}</p>
        {requireWord && (
          <div className="field">
            <label htmlFor="dlg-w" className="small">Para confirmar, digite <strong>{requireWord}</strong></label>
            <input id="dlg-w" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
          </div>
        )}
        <div className="dialog-actions">
          <Button ref={cancel} onClick={onCancel}>Cancelar</Button>
          <Button variant={danger ? "danger" : "primary"} disabled={!ok} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}

export function Dialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title">
        <h2 id="dlg-title">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Toasts({ items }: { items: { id: number; kind: string; text: string }[] }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
      ))}
    </div>
  );
}
