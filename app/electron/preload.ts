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
};

contextBridge.exposeInMainWorld("fidus", api);
