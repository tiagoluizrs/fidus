// Regras de segurança das janelas: sem navegação, sem janelas novas, sem permissões, sem conteúdo remoto.
import type { BrowserWindow, Session, WebContents } from "electron";

export function hardenSession(session: Session): void {
  session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false)); // nada de microfone/câmera no renderer
  session.setPermissionCheckHandler(() => false);
  session.webRequest.onBeforeRequest((details, callback) => {
    // só arquivos do app e dados embutidos; qualquer pedido de rede é cancelado
    const ok = details.url.startsWith("file://") || details.url.startsWith("data:") || details.url.startsWith("devtools:");
    callback({ cancel: !ok });
  });
}

export function hardenContents(wc: WebContents): void {
  wc.on("will-navigate", (e) => e.preventDefault());
  wc.on("will-redirect", (e) => e.preventDefault());
  wc.on("will-attach-webview", (e) => e.preventDefault());
  wc.setWindowOpenHandler(() => ({ action: "deny" }));
}

/** Opções de webPreferences iguais para todas as janelas. */
export function webPreferences(preload: string) {
  return {
    preload,
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    webviewTag: false,
    spellcheck: false,
    devTools: !!process.env.FIDUS_DEVTOOLS,
  } as const;
}

export function lockDown(win: BrowserWindow): void {
  hardenContents(win.webContents);
}
