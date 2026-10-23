// API mínima exposta ao renderer. Sem Node, sem token, sem acesso direto ao núcleo.
import { contextBridge, ipcRenderer } from "electron";
import type { CommandName, CoreEvent, FidusApi, Reply, Snapshot } from "../src/shared/protocol";

const api: FidusApi = {
  onEvent(cb) {
    const handler = (_e: unknown, event: CoreEvent) => cb(event);
    ipcRenderer.on("fidus:event", handler);
    return () => ipcRenderer.removeListener("fidus:event", handler);
  },
  command: (name: CommandName, args = {}) => ipcRenderer.invoke("fidus:command", name, args) as Promise<Reply>,
  getSnapshot: () => ipcRenderer.invoke("fidus:snapshot") as Promise<Snapshot | null>,
  closeWindow: () => ipcRenderer.send("fidus:close-window"),
  getTheme: () => ipcRenderer.invoke("fidus:theme") as Promise<"light" | "dark">,
  onThemeChange(cb) {
    const handler = (_e: unknown, t: "light" | "dark") => cb(t);
    ipcRenderer.on("fidus:theme-changed", handler);
    return () => ipcRenderer.removeListener("fidus:theme-changed", handler);
  },
  pickFolder: () => ipcRenderer.invoke("fidus:pick-folder") as Promise<string | null>,
  pickSavePath: (suggestedName, ext) => ipcRenderer.invoke("fidus:pick-save-path", suggestedName, ext) as Promise<string | null>,
  saveTextFile: (suggestedName, content) => ipcRenderer.invoke("fidus:save-text-file", suggestedName, content) as Promise<boolean>,
  openPath: (kind) => ipcRenderer.invoke("fidus:open-path", kind) as Promise<boolean>,
  openMicSettings: () => ipcRenderer.invoke("fidus:open-mic-settings") as Promise<void>,
  micStatus: () => ipcRenderer.invoke("fidus:mic-status") as Promise<string>,
  restartCore: () => ipcRenderer.invoke("fidus:restart-core") as Promise<void>,
  copyText: (text) => ipcRenderer.invoke("fidus:copy-text", text) as Promise<void>,
  onNavigate(cb) {
    const handler = (_e: unknown, page: string) => cb(page);
    ipcRenderer.on("fidus:navigate", handler);
    return () => ipcRenderer.removeListener("fidus:navigate", handler);
  },
};

contextBridge.exposeInMainWorld("fidus", api);
