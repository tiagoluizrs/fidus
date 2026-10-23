// Processo do núcleo Python (sidecar): inicia, lê a linha FIDUS_READY, reinicia se cair e encerra junto com o app.
import { EventEmitter } from "node:events";
import { spawn as nodeSpawn } from "node:child_process";
import type { ChildProcessWithoutNullStreams, SpawnOptions } from "node:child_process";
import { createInterface } from "node:readline";
import { parseReadyLine } from "./logic";
import type { ReadyInfo } from "./logic";

export interface CoreCommand {
  command: string;
  args: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}
type SpawnFn = (cmd: string, args: string[], opts: SpawnOptions) => ChildProcessWithoutNullStreams;

export class CoreProcess extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private stopping = false;
  private restarts = 0;
  ready: ReadyInfo | null = null;

  constructor(
    private cmd: CoreCommand,
    private spawnFn: SpawnFn = nodeSpawn as unknown as SpawnFn,
    private maxRestarts = 3,
    private restartDelayMs = 1500,
  ) {
    super();
  }

  start(): void {
    this.stopping = false;
    this.ready = null;
    const child = this.spawnFn(this.cmd.command, this.cmd.args, {
      cwd: this.cmd.cwd,
      env: { ...process.env, ...this.cmd.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
      stdio: ["pipe", "pipe", "pipe"], // stdin aberto: se o Electron morrer, o núcleo vê o fim e encerra
      windowsHide: true,
    });
    this.child = child;
    createInterface({ input: child.stdout }).on("line", (line) => {
      const info = parseReadyLine(line);
      if (info) {
        this.ready = info;
        this.restarts = 0;
        this.emit("ready", info);
      } else {
        this.emit("log", line);
      }
    });
    createInterface({ input: child.stderr }).on("line", (line) => this.emit("log", line));
    child.on("error", (err) => this.emit("error", err));
    child.on("exit", (code, signal) => {
      this.child = null;
      this.ready = null;
      this.emit("exit", code, signal);
      if (!this.stopping && this.restarts < this.maxRestarts) {
        this.restarts += 1;
        this.emit("restarting", this.restarts);
        setTimeout(() => !this.stopping && this.start(), this.restartDelayMs);
      } else if (!this.stopping) {
        this.emit("failed");
      }
    });
  }

  /** Encerra o núcleo. `graceful` roda antes (ex.: comando `quit`); depois de `waitMs` mata o processo. */
  async stop(graceful?: () => Promise<unknown>, waitMs = 3000): Promise<void> {
    this.stopping = true;
    const child = this.child;
    if (!child) return;
    const exited = new Promise<void>((resolve) => child.once("exit", () => resolve()));
    try {
      await graceful?.();
    } catch {
      /* segue para o encerramento forçado */
    }
    child.stdin.end();
    await Promise.race([exited, new Promise<void>((r) => setTimeout(r, waitMs))]);
    if (this.child) child.kill();
  }
}
