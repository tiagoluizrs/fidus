// Cliente do WebSocket do núcleo. Roda no processo principal: o token nunca chega ao renderer.
import { EventEmitter } from "node:events";
import WebSocket from "ws";
import type { CoreEvent, Reply, Snapshot } from "../src/shared/protocol";

export interface BridgeOptions {
  connectTimeoutMs?: number;
  requestTimeoutMs?: number;
}

export class BridgeClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<string, { resolve: (r: Reply) => void; timer: NodeJS.Timeout }>();
  snapshot: Snapshot | null = null;

  constructor(private opts: BridgeOptions = {}) {
    super();
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** Conecta, autentica e espera o `ready`. Rejeita se o token for recusado. */
  connect(port: number, token: string): Promise<Snapshot> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}/`, { maxPayload: 1 << 20 });
      this.ws = ws;
      let settled = false;
      const fail = (err: Error) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(err);
        }
      };
      const timer = setTimeout(() => {
        fail(new Error("tempo esgotado ao conectar no núcleo"));
        ws.terminate();
      }, this.opts.connectTimeoutMs ?? 8000);
      ws.on("open", () => ws.send(JSON.stringify({ type: "auth", token })));
      ws.on("message", (data) => {
        let msg: any;
        try {
          msg = JSON.parse(data.toString());
        } catch {
          return;
        }
        if (msg.type === "ready" && !settled) {
          settled = true;
          clearTimeout(timer);
          this.snapshot = msg.snapshot;
          this.emit("connected", msg.snapshot);
          resolve(msg.snapshot);
          return;
        }
        if (msg.type === "reply") {
          const p = this.pending.get(String(msg.id));
          if (p) {
            clearTimeout(p.timer);
            this.pending.delete(String(msg.id));
            p.resolve(msg as Reply);
          }
          return;
        }
        this.emit("event", msg as CoreEvent);
      });
      ws.on("close", (code) => {
        fail(new Error(code === 4401 ? "token recusado pelo núcleo" : `conexão encerrada (${code})`));
        for (const [id, p] of this.pending) {
          clearTimeout(p.timer);
          p.resolve({ type: "reply", id, ok: false, error: "conexão com o núcleo perdida" });
        }
        this.pending.clear();
        this.ws = null;
        this.emit("disconnected", code);
      });
      ws.on("error", (e) => fail(e as Error));
    });
  }

  /** Manda um comando e espera a resposta. Nunca rejeita: erros viram `{ok:false}`. */
  request(name: string, args: Record<string, unknown> = {}): Promise<Reply> {
    if (!this.connected) return Promise.resolve({ type: "reply", id: null, ok: false, error: "núcleo não conectado" });
    const id = String(this.nextId++);
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve({ type: "reply", id, ok: false, error: "o núcleo não respondeu a tempo" });
      }, this.opts.requestTimeoutMs ?? 10000);
      this.pending.set(id, { resolve, timer });
      this.ws!.send(JSON.stringify({ type: "cmd", id, name, args }));
    });
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }
}
