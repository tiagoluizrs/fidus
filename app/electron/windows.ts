import { BrowserWindow, nativeTheme } from "electron";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { lockDown, webPreferences } from "./security";

export class Windows {
  ring: BrowserWindow | null = null;
  settings: BrowserWindow | null = null;
  private closingRing = false;
  onRingClosedExternally: () => void = () => {};

  constructor(private rendererDir: string, private preload: string) {}

  get rendererUrl(): string {
    return pathToFileURL(this.rendererDir).href + "/";
  }

  private bg(): string {
    return nativeTheme.shouldUseDarkColors ? "#000000" : "#FFFFFF";
  }

  openRing(): void {
    if (this.ring) return;
    const win = new BrowserWindow({
      fullscreen: true, frame: false, show: false, skipTaskbar: true, alwaysOnTop: true, autoHideMenuBar: true,
      backgroundColor: this.bg(), title: "Fidus", webPreferences: webPreferences(this.preload),
    });
    this.ring = win;
    lockDown(win);
    win.setAlwaysOnTop(true, "screen-saver");
    win.once("ready-to-show", () => win.showInactive()); // aparece sem roubar o foco de quem está digitando
    win.on("closed", () => {
      this.ring = null;
      if (!this.closingRing) this.onRingClosedExternally();
      this.closingRing = false;
    });
    void win.loadURL(this.rendererUrl + "ring.html");
    console.log("[fidus] janela do anel criada");
    const shots = process.env.FIDUS_SCREENSHOT_DIR; // só para desenvolvimento: salva uma imagem da janela
    if (shots) {
      win.webContents.once("did-finish-load", () =>
        setTimeout(async () => {
          if (win.isDestroyed()) return;
          const img = await win.webContents.capturePage();
          const { writeFileSync } = await import("node:fs");
          writeFileSync(path.join(shots, `ring-${Date.now()}.png`), img.toPNG());
        }, Number(process.env.FIDUS_SCREENSHOT_DELAY_MS) || 3500),
      );
    }
  }

  closeRing(): void {
    if (!this.ring) return;
    this.closingRing = true;
    this.ring.destroy(); // destruída de verdade: o processo do Chromium dessa janela some
    this.ring = null;
    console.log("[fidus] janela do anel destruída");
  }

  openSettings(page?: string): void {
    if (this.settings) {
      if (this.settings.isMinimized()) this.settings.restore();
      this.settings.focus();
      if (page) this.settings.webContents.send("fidus:navigate", page);
      return;
    }
    const win = new BrowserWindow({
      width: 1100, height: 760, minWidth: 900, minHeight: 600, show: false, autoHideMenuBar: true,
      backgroundColor: this.bg(), title: "Fidus · Configurações", webPreferences: webPreferences(this.preload),
    });
    this.settings = win;
    lockDown(win);
    win.once("ready-to-show", () => win.show());
    win.on("closed", () => (this.settings = null));
    void win.loadURL(this.rendererUrl + "settings.html" + (page ? `#${encodeURIComponent(page)}` : ""));
  }

  /** Envia um evento a todas as janelas abertas. O nível de áudio só interessa ao anel. */
  broadcast(channel: string, payload: unknown, ringOnly = false): void {
    const targets = ringOnly ? [this.ring] : [this.ring, this.settings];
    for (const w of targets) if (w && !w.isDestroyed()) w.webContents.send(channel, payload);
  }

  isTrusted(url: string): boolean {
    return url.startsWith(this.rendererUrl) && !url.slice(this.rendererUrl.length).includes("..");
  }

  fromSender(wc: Electron.WebContents): "ring" | "settings" | null {
    if (this.ring && this.ring.webContents === wc) return "ring";
    if (this.settings && this.settings.webContents === wc) return "settings";
    return null;
  }
}

export function resolveDirs(appPath: string) {
  return {
    renderer: path.join(appPath, "dist", "renderer"),
    preload: path.join(appPath, "dist-electron", "preload.js"),
    assets: path.join(appPath, "assets"),
  };
}
