import { Menu, Tray, nativeImage } from "electron";
import path from "node:path";
import { buildTrayTemplate } from "./logic";
import type { AppIcon } from "./logic";
import type { MenuItem, TrayHandlers } from "./logic";
import type { Snapshot } from "../src/shared/protocol";

export class AppTray {
  private tray: Tray | null = null;
  private last: Snapshot | null = null;
  private problem: string | null = null;
  private variant: AppIcon = "colorido";

  constructor(private assets: string, private handlers: TrayHandlers) {
    this.setVisible(true);
  }

  /** Troca a arte do ícone da bandeja (a que a pessoa escolheu em Configurações > Geral). */
  setIcon(variant: AppIcon): void {
    this.variant = variant;
    this.tray?.setImage(this.icon());
  }

  /** "Mostrar o ícone na bandeja": sem o ícone, o app só reabre pelo atalho do programa (segunda instância). */
  setVisible(visible: boolean): void {
    if (visible && !this.tray) {
      this.tray = new Tray(this.icon());
      this.tray.on("click", () => this.tray?.popUpContextMenu());
      this.update(this.last, this.problem);
    } else if (!visible && this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }

  private icon() {
    // tray-<arte>.png (32 px) e tray-<arte>@2x.png (64 px): o Electron escolhe o tamanho certo pela tela
    return nativeImage.createFromPath(path.join(this.assets, `tray-${this.variant}.png`));
  }

  update(snapshot: Snapshot | null, problem: string | null = this.problem): void {
    this.last = snapshot;
    this.problem = problem;
    if (!this.tray) return;
    const template = buildTrayTemplate(snapshot, this.handlers, Date.now(), problem) as MenuItem[];
    this.tray.setContextMenu(Menu.buildFromTemplate(template as Electron.MenuItemConstructorOptions[]));
    this.tray.setToolTip(template[0].label ?? "Fidus");
  }

  destroy(): void {
    this.tray?.destroy();
    this.tray = null;
  }
}
