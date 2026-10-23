import { useEffect, useState } from "react";
import { applyTheme } from "../shared/theme";
import type { Theme } from "../shared/theme";
import { CoreProvider, useCore } from "./core";
import { Geral } from "./pages/Geral";
import { ModeloIA } from "./pages/ModeloIA";
import { Contas } from "./pages/Contas";
import { Memoria } from "./pages/Memoria";
import { Personagem } from "./pages/Personagem";
import { Privacidade } from "./pages/Privacidade";
import { Sobre } from "./pages/Sobre";
import { Voz } from "./pages/Voz";
import { Toasts } from "./ui";

export const PAGES = [
  { id: "geral", label: "Geral", icon: "M4 6h10M20 6h0M4 12h4M14 12h6M4 18h12M20 18h0", Page: Geral },
  { id: "voz", label: "Voz", icon: "M9 3h6v11a3 3 0 0 1-6 0zM5 11a7 7 0 0 0 14 0M12 18v3", Page: Voz },
  { id: "personagem", label: "Personagem", icon: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21c0-4 4-6 8-6s8 2 8 6", Page: Personagem },
  { id: "modelo", label: "Modelo de IA", icon: "M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z", Page: ModeloIA },
  { id: "contas", label: "Contas", icon: "M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4", Page: Contas },
  { id: "privacidade", label: "Privacidade", icon: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z", Page: Privacidade },
  { id: "memoria", label: "Memória", icon: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6", Page: Memoria },
  { id: "sobre", label: "Sobre", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h0", Page: Sobre },
] as const;

const fromHash = () => {
  const h = decodeURIComponent(location.hash.replace(/^#/, ""));
  return PAGES.some((p) => p.id === h) ? h : "geral";
};

function Shell() {
  const [page, setPage] = useState<string>(fromHash());
  const { toasts } = useCore();
  useEffect(() => window.fidus.onNavigate((p) => PAGES.some((x) => x.id === p) && setPage(p)), []);
  useEffect(() => {
    const on = () => setPage(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const Current = PAGES.find((p) => p.id === page)!.Page;
  return (
    <div className="settings">
      <aside className="sidebar">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <defs><linearGradient id="s-g" x1="11" y1="0" x2="11" y2="22" gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#FF6A3D" /><stop offset="0.5" stopColor="#FF5C9E" /><stop offset="1" stopColor="#3D8BFF" /></linearGradient></defs>
            <circle cx="11" cy="11" r="8.5" fill="none" stroke="url(#s-g)" strokeWidth="2" />
          </svg>
          <span>Fidus</span>
        </div>
        <nav aria-label="Configurações">
          {PAGES.map((p) => (
            <a key={p.id} href={`#${p.id}`} aria-current={p.id === page ? "page" : undefined} className={p.id === page ? "on" : ""} onClick={(e) => { e.preventDefault(); setPage(p.id); }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={p.icon} /></svg>
              {p.label}
            </a>
          ))}
        </nav>
        <p className="muted small side-note">Memória e histórico ficam guardados só neste computador.</p>
      </aside>
      <main className="content" id="conteudo" tabIndex={-1}><Current /></main>
      <Toasts items={toasts} />
    </div>
  );
}

export function SettingsApp() {
  const [theme, setTheme] = useState<Theme>("dark");
  useEffect(() => {
    let alive = true;
    void window.fidus.getTheme().then((t) => alive && setTheme(t));
    const off = window.fidus.onThemeChange(setTheme);
    return () => { alive = false; off(); };
  }, []);
  useEffect(() => applyTheme(theme), [theme]);
  return (
    <CoreProvider>
      <Shell />
    </CoreProvider>
  );
}
