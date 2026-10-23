import { Menu, Tray, nativeImage, nativeTheme } from "electron";
import path from "node:path";
import { buildTrayTemplate } from "./logic";
import type { MenuItem, TrayHandlers } from "./logic";
import type { Snapshot } from "../src/shared/protocol";

export class AppTray {
  private tray: Tray | null = null;
  private last: Snapshot | null = null;

  constructor(private assets: string, private handlers: TrayHandlers) {
    nativeTheme.on("updated", () => this.tray?.setImage(this.icon()));
    this.setVisible(true);
  }

  /** "Mostrar o ícone na bandeja": sem o ícone, o app só reabre pelo atalho do programa (segunda instância). */
  setVisible(visible: boolean): void {
    if (visible && !this.tray) {
      this.tray = new Tray(this.icon());
      this.tray.on("click", () => this.tray?.popUpContextMenu());
      this.update(this.last);
    } else if (!visible && this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }

  private icon() {
    // ícone monocromático: branco em barra escura, preto em barra clara (a barra do Windows segue o tema do sistema)
    const file = nativeTheme.shouldUseDarkColors ? "tray-dark.png" : "tray-light.png";
    return nativeImage.createFromPath(path.join(this.assets, file));
  }

  update(snapshot: Snapshot | null): void {
    this.last = snapshot;
    if (!this.tray) return;
    const template = buildTrayTemplate(snapshot, this.handlers) as MenuItem[];
    this.tray.setContextMenu(Menu.buildFromTemplate(template as Electron.MenuItemConstructorOptions[]));
    this.tray.setToolTip(template[0].label ?? "Fidus");
  }

  destroy(): void {
    this.tray?.destroy();
    this.tray = null;
  }
}
