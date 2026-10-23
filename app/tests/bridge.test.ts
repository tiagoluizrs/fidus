// @vitest-environment node
import { spawnSync } from "node:child_process";
import path from "node:path";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { WebSocketServer } from "ws";
import type { AddressInfo } from "node:net";
import { BridgeClient } from "../electron/bridge";
import { CoreProcess } from "../electron/core";
import type { CoreEvent, Snapshot } from "../src/shared/protocol";

const TOKEN = "t".repeat(43);
const snap = { status: "ready", state: "idle" } as unknown as Snapshot;

/** Núcleo de mentira que segue o protocolo (docs/PROTOCOLO.md): auth, ready, cmd/reply e eventos. */
async function fakeCore(opts: { silent?: boolean } = {}) {
  const wss = new WebSocketServer({ host: "127.0.0.1", port: 0, verifyClient: (i: { origin: string }) => !i.origin });
  const seen: any[] = [];
  wss.on("connection", (ws) => {
    let authed = false;
    ws.on("message", (raw) => {
      const m = JSON.parse(raw.toString());
      if (!authed) {
        if (m.type === "auth" && m.token === TOKEN) {
          authed = true;
          ws.send(JSON.stringify({ type: "ready", protocol: 1, snapshot: snap }));
        } else ws.close(4401, "não autorizado");
        return;
      }
      seen.push(m);
      if (opts.silent) return;
      if (m.name === "mute") ws.send(JSON.stringify({ type: "state", state: "muted", mic: "muted" })); // evento antes da resposta
      ws.send(JSON.stringify({ type: "reply", id: m.id, ok: m.name !== "falha", data: { echo: m.args }, error: m.name === "falha" ? "deu ruim" : undefined }));
    });
  });
  await new Promise<void>((r) => wss.once("listening", () => r()));
  return { wss, seen, port: () => (wss.address() as AddressInfo).port };
}

describe("cliente do núcleo (processo principal)", () => {
  it("autentica, recebe o snapshot e responde aos comandos pelo id", async () => {
    const core = await fakeCore();
    const c = new BridgeClient();
    expect(await c.connect(core.port(), TOKEN)).toEqual(snap);
    const [a, b] = await Promise.all([c.request("ping"), c.request("mute", { value: true })]);
    expect(a).toMatchObject({ ok: true });
    expect(b).toMatchObject({ ok: true, data: { echo: { value: true } } });
    expect(core.seen.map((m) => m.name)).toEqual(["ping", "mute"]);
    expect(core.seen.every((m) => m.type === "cmd" && typeof m.id === "string")).toBe(true);
    c.close();
    core.wss.close();
  });

  it("eventos do núcleo chegam ao listener", async () => {
    const core = await fakeCore();
    const c = new BridgeClient();
    const events: CoreEvent[] = [];
    c.on("event", (e) => events.push(e));
    await c.connect(core.port(), TOKEN);
    await c.request("mute", { value: true });
    expect(events).toEqual([{ type: "state", state: "muted", mic: "muted" }]);
    c.close();
    core.wss.close();
  });

  it("token errado é recusado e nada é executado", async () => {
    const core = await fakeCore();
    const c = new BridgeClient();
    await expect(c.connect(core.port(), "errado")).rejects.toThrow(/token recusado/);
    expect(core.seen).toEqual([]);
    expect((await c.request("ping")).ok).toBe(false); // sem conexão: resposta de erro, sem exceção
    core.wss.close();
  });

  it("erro do núcleo vira resposta ok:false; sem resposta vence o tempo limite", async () => {
    const core = await fakeCore();
    const c = new BridgeClient({ requestTimeoutMs: 150 });
    await c.connect(core.port(), TOKEN);
    expect(await c.request("falha")).toMatchObject({ ok: false, error: "deu ruim" });
    core.wss.close();
    const quiet = await fakeCore({ silent: true });
    const c2 = new BridgeClient({ requestTimeoutMs: 150 });
    await c2.connect(quiet.port(), TOKEN);
    expect(await c2.request("ping")).toMatchObject({ ok: false, error: expect.stringContaining("não respondeu") });
    c.close();
    c2.close();
    quiet.wss.close();
  });

  it("queda da conexão resolve os pedidos pendentes e avisa", async () => {
    const quiet = await fakeCore({ silent: true });
    const c = new BridgeClient({ requestTimeoutMs: 5000 });
    await c.connect(quiet.port(), TOKEN);
    const dropped = new Promise((r) => c.once("disconnected", r));
    const pending = c.request("ping");
    await new Promise((r) => setTimeout(r, 50));
    quiet.wss.clients.forEach((s) => s.terminate());
    expect(await pending).toMatchObject({ ok: false, error: expect.stringContaining("perdida") });
    await dropped;
    expect(c.connected).toBe(false);
    quiet.wss.close();
  });
});

// ---------------------------------------------------------------- contra o NÚCLEO SIMULADO de verdade (Python)

const root = path.resolve(__dirname, "..", "..");
const hasUv = spawnSync("uv", ["--version"]).status === 0;

describe.skipIf(!hasUv)("protocolo contra o núcleo simulado (Python)", () => {
  it("sobe o núcleo, anuncia porta e token, encena uma conversa e encerra com `quit`", async () => {
    const proc = new CoreProcess({ command: "uv", args: ["run", "fidus", "daemon", "--stdin-watch", "--simulado"], cwd: root, env: { FIDUS_HOME: path.join(root, ".tmp-sim-home") } }, undefined, 0);
    const info = await new Promise<{ port: number; token: string }>((resolve, reject) => {
      proc.once("ready", resolve);
      proc.once("exit", () => reject(new Error("núcleo saiu")));
      proc.start();
    });
    const c = new BridgeClient();
    const snapshot = await c.connect(info.port, info.token);
    expect(snapshot.character.id).toBe("alfred");
    expect(snapshot.characters.map((x) => x.id).sort()).toEqual(["alfred", "donna", "jarbis"]);
    expect(snapshot.model).toMatchObject({ provider: "claude", where: "Nuvem" });

    const events: CoreEvent[] = [];
    c.on("event", (e) => events.push(e));
    const done = new Promise<void>((resolve) =>
      c.on("event", (e: CoreEvent) => e.type === "state" && e.state === "idle" && events.some((x) => x.type === "caption") && resolve()),
    );
    expect(await c.request("simulate")).toMatchObject({ ok: true });
    await done;
    expect(events.filter((e) => e.type === "state").map((e: any) => e.state)).toEqual(["listening", "thinking", "speaking", "idle"]);
    expect(events.filter((e) => e.type === "level").length).toBeGreaterThan(10);
    expect(events.filter((e: any) => e.type === "level").every((e: any) => e.values.length === 3 && e.values.every((v: number) => v >= 0 && v <= 1))).toBe(true);
    const text = events.filter((e: any) => e.type === "caption" && e.role === "assistant").map((e: any) => e.text).join("").trim();
    expect(text).toBe("Bom dia. Você tem duas reuniões; a primeira é às 9h.");

    expect(await c.request("mute", { value: "sim" })).toMatchObject({ ok: false }); // validação do núcleo
    expect(await c.request("set_settings", { patch: { "api.chave": "x" } })).toMatchObject({ ok: false });
    expect(await c.request("quit")).toMatchObject({ ok: true });
    await new Promise((r) => proc.once("exit", r));
    c.close();
  }, 60000);

  it("um cliente sem o token não consegue nada", async () => {
    const proc = new CoreProcess({ command: "uv", args: ["run", "fidus", "daemon", "--stdin-watch", "--simulado"], cwd: root, env: { FIDUS_HOME: path.join(root, ".tmp-sim-home") } }, undefined, 0);
    const info = await new Promise<{ port: number; token: string }>((resolve) => {
      proc.once("ready", resolve);
      proc.start();
    });
    await expect(new BridgeClient().connect(info.port, "x".repeat(43))).rejects.toThrow(/token recusado/);
    const c = new BridgeClient();
    await c.connect(info.port, info.token);
    await proc.stop(() => c.request("quit"), 5000);
    c.close();
  }, 60000);

  it("operações das telas de Configurações funcionam de ponta a ponta (personagens, memória, privacidade)", async () => {
    const home = mkdtempSync(path.join(tmpdir(), "fidus-5b-"));
    const proc = new CoreProcess({ command: "uv", args: ["run", "fidus", "daemon", "--stdin-watch", "--simulado"], cwd: root, env: { FIDUS_HOME: home } }, undefined, 0);
    const info = await new Promise<{ port: number; token: string }>((resolve) => {
      proc.once("ready", resolve);
      proc.start();
    });
    const c = new BridgeClient();
    await c.connect(info.port, info.token);
    const ok = async (name: string, args: Record<string, unknown> = {}) => {
      const r: any = await c.request(name, args);
      expect(r.ok, `${name}: ${r.error}`).toBe(true);
      return r.data;
    };

    const got = await ok("characters", { op: "get", id: "donna" });
    expect(got.id).toBe("donna");
    const edited = await ok("characters", { op: "set_control", id: "donna", control: "humor", value: 77 });
    expect(edited.personality.controls.humor.value).toBe(77);
    const added = await ok("characters", { op: "item_add", id: "donna", list: "concluir", text: "Feito, {tratamento}." });
    expect(JSON.stringify(added.phrases.concluir)).toContain("Feito, {tratamento}.");

    const m = await ok("memory", { op: "add", text: "Prefere café sem açúcar", section: "perfil" });
    const listed = await ok("memory", { op: "list", query: "café" });
    expect(listed.entries.map((e: any) => e.id)).toContain(m.entry.id);
    expect(await c.request("memory", { op: "delete", id: m.entry.id })).toMatchObject({ ok: false }); // sem confirm:true, nada some
    await ok("memory", { op: "delete", id: m.entry.id, confirm: true });
    expect((await ok("memory", { op: "list" })).entries).toEqual([]);

    const saved = await ok("set_settings", { patch: { "chamados.sensibilidade": 70 } });
    expect(saved.saved).toContain("chamados.sensibilidade");
    expect((await ok("get_settings")).effective["chamados.sensibilidade"]).toBe(70);
    expect(await c.request("set_settings", { patch: { "voz.velocidade_voz": 99 } })).toMatchObject({ ok: false });
    expect(await c.request("privacy", { op: "clear_all" })).toMatchObject({ ok: false });
    expect(await c.request("api_key", { op: "set", value: "nao-e-chave" })).toMatchObject({ ok: false });

    await proc.stop(() => c.request("quit"), 5000);
    c.close();
    rmSync(home, { recursive: true, force: true });
  }, 90000);
});
