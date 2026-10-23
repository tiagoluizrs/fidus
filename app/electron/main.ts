import { app, globalShortcut, ipcMain, Menu, nativeTheme, session } from "electron";
import { BridgeClient } from "./bridge";
import { CoreProcess } from "./core";
import { ALLOWED_COMMANDS, RingLifecycle, applyEvent } from "./logic";
import { resolveCoreCommand } from "./paths";
import { hardenContents, hardenSession } from "./security";
import { AppTray } from "./tray";
import { Windows, resolveDirs } from "./windows";
import type { CoreEvent, Snapshot } from "../src/shared/protocol";

const IDLE_CLOSE_MS = Number(process.env.FIDUS_RING_IDLE_MS) || 6000; // janela some depois de alguns segundos parado

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  let snapshot: Snapshot | null = null;
  const bridge = new BridgeClient();
  const dirs = resolveDirs(app.getAppPath());
  const windows = new Windows(dirs.renderer, dirs.preload);
  const lifecycle = new RingLifecycle(
    () => {
      windows.openRing();
      // a janela abre sem roubar o foco, então o Esc precisa valer mesmo sem ela focada: só enquanto o anel existe
      globalShortcut.register("Escape", () => lifecycle.dismiss());
    },
    () => {
      globalShortcut.unregister("Escape");
      windows.closeRing();
    },
    IDLE_CLOSE_MS,
  );
  windows.onRingClosedExternally = () => lifecycle.onClosedExternally();
  let tray: AppTray | null = null;
  let core: CoreProcess | null = null;
  let quitting = false;

  const refreshTray = () => tray?.update(snapshot);
  const command = (name: string, args: Record<string, unknown> = {}) => bridge.request(name, args);

  app.on("second-instance", () => windows.openSettings());
  app.on("will-quit", () => globalShortcut.unregisterAll());
  app.on("window-all-closed", () => {
    /* o Fidus continua na bandeja sem nenhuma janela */
  });
  app.on("web-contents-created", (_e, wc) => hardenContents(wc));

  app.on("before-quit", (e) => {
    if (quitting) return;
    quitting = true;
    e.preventDefault();
    void (async () => {
      lifecycle.dismiss();
      await core?.stop(() => command("quit"));
      bridge.close();
      tray?.destroy();
      app.exit(0);
    })();
  });

  void app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    if (process.env.FIDUS_THEME === "light" || process.env.FIDUS_THEME === "dark") nativeTheme.themeSource = process.env.FIDUS_THEME;
    hardenSession(session.defaultSession);

    tray = new AppTray(dirs.assets, {
      command: (name, args) => void command(name, args),
      openSettings: (page) => windows.openSettings(page),
      quit: () => app.quit(),
    });

    // ---- ponte com a interface (renderers): API mínima, só comandos permitidos e só de páginas do app ----
    ipcMain.handle("fidus:command", (e, name: string, args: Record<string, unknown>) => {
      if (!windows.isTrusted(e.senderFrame?.url ?? "") || !ALLOWED_COMMANDS.has(name)) {
        return { type: "reply", id: null, ok: false, error: "comando não permitido" };
      }
      return command(name, args && typeof args === "object" ? args : {});
    });
    ipcMain.handle("fidus:snapshot", (e) => (windows.isTrusted(e.senderFrame?.url ?? "") ? snapshot : null));
    ipcMain.handle("fidus:theme", () => (nativeTheme.shouldUseDarkColors ? "dark" : "light"));
    ipcMain.on("fidus:close-window", (e) => {
      if (windows.fromSender(e.sender) === "ring") lifecycle.dismiss();
      else if (windows.fromSender(e.sender) === "settings") windows.settings?.close();
    });
    nativeTheme.on("updated", () => windows.broadcast("fidus:theme-changed", nativeTheme.shouldUseDarkColors ? "dark" : "light"));

    // ---- eventos do núcleo ----
    bridge.on("event", (event: CoreEvent) => {
      snapshot = applyEvent(snapshot, event);
      if (event.type === "state") lifecycle.onState(event.state);
      if (event.type === "confirm") lifecycle.onState("listening"); // uma confirmação sempre precisa ser vista
      windows.broadcast("fidus:event", event, event.type === "level");
      if (event.type !== "level") refreshTray();
    });
    bridge.on("disconnected", () => {
      if (snapshot && !quitting) snapshot = { ...snapshot, status: "starting", message: "Reconectando ao núcleo…" };
      refreshTray();
    });

    // ---- núcleo (sidecar) ----
    core = new CoreProcess(
      resolveCoreCommand({ isPackaged: app.isPackaged, resourcesPath: process.resourcesPath, appPath: app.getAppPath(), argv: process.argv, env: process.env }),
    );
    core.on("log", (line: string) => console.log(`[núcleo] ${line}`));
    core.on("ready", async (info) => {
      try {
        snapshot = await bridge.connect(info.port, info.token);
        console.log(`[fidus] conectado ao núcleo (protocolo ${info.protocol}), estado: ${snapshot.status}`);
        windows.broadcast("fidus:event", { type: "ready", protocol: info.protocol, snapshot });
        if (process.env.FIDUS_AUTOPLAY === "1") setTimeout(() => void command("simulate"), 800); // desenvolvimento: encena uma conversa
      } catch (err) {
        console.error("[fidus] não consegui conectar ao núcleo:", err);
      }
      refreshTray();
    });
    core.on("restarting", (n: number) => {
      snapshot = snapshot && { ...snapshot, status: "starting", message: `Reiniciando o núcleo (${n})…` };
      refreshTray();
    });
    core.on("failed", () => {
      snapshot = snapshot && { ...snapshot, status: "error", message: "O núcleo parou de responder" };
      refreshTray();
    });
    core.on("error", (err: Error) => console.error("[fidus] falha ao iniciar o núcleo:", err.message));
    core.start();
  });
}
