// @vitest-environment node
import { EventEmitter } from "node:events";
import path from "node:path";
import { PassThrough } from "node:stream";
import { CoreProcess } from "../electron/core";
import { resolveCoreCommand } from "../electron/paths";

function fakeChild() {
  const child: any = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.stdin = { end: vi.fn() };
  child.kill = vi.fn(() => child.emit("exit", null, "SIGTERM"));
  return child;
}

describe("processo do núcleo", () => {
  it("lê a linha de pronto e repassa o resto como log", async () => {
    const child = fakeChild();
    const proc = new CoreProcess({ command: "x", args: [] }, () => child, 0);
    const ready = vi.fn();
    const logs: string[] = [];
    proc.on("ready", ready);
    proc.on("log", (l) => logs.push(l));
    proc.start();
    child.stdout.write("Carregando o Whisper\n");
    child.stdout.write(`FIDUS_READY {"port":4242,"token":"${"a".repeat(30)}","protocol":1}\n`);
    child.stderr.write("aviso\n");
    await new Promise((r) => setTimeout(r, 20));
    expect(ready).toHaveBeenCalledWith({ port: 4242, token: "a".repeat(30), protocol: 1 });
    expect(logs).toEqual(["Carregando o Whisper", "aviso"]);
    expect(logs.join()).not.toContain("a".repeat(30)); // o token não vai para o log
  });

  it("reinicia sozinho se cair, até o limite, e depois avisa a falha", async () => {
    const children: any[] = [];
    const spawn = () => {
      const c = fakeChild();
      children.push(c);
      return c;
    };
    const proc = new CoreProcess({ command: "x", args: [] }, spawn, 2, 5);
    const events: string[] = [];
    proc.on("restarting", (n) => events.push(`reinicia ${n}`));
    proc.on("failed", () => events.push("falhou"));
    proc.start();
    for (let i = 0; i < 3; i++) {
      children[i].emit("exit", 1, null);
      await new Promise((r) => setTimeout(r, 30));
    }
    expect(events).toEqual(["reinicia 1", "reinicia 2", "falhou"]);
    expect(children).toHaveLength(3);
  });

  it("stop pede o encerramento educado, fecha o stdin e mata se não sair", async () => {
    const child = fakeChild();
    child.kill = vi.fn(() => child.emit("exit", null, "SIGKILL"));
    const proc = new CoreProcess({ command: "x", args: [] }, () => child, 3);
    proc.start();
    const graceful = vi.fn(async () => {});
    await proc.stop(graceful, 20);
    expect(graceful).toHaveBeenCalled();
    expect(child.stdin.end).toHaveBeenCalled(); // o núcleo vê o fim do stdin e encerra sozinho
    expect(child.kill).toHaveBeenCalled(); // não saiu a tempo: encerrado à força
    child.emit("exit", 0, null);
    await new Promise((r) => setTimeout(r, 20));
    expect(proc.listenerCount("restarting")).toBe(0); // e NÃO reiniciou
  });

  it("o núcleo é iniciado sem janela de console e com stdin aberto", () => {
    const spawn = vi.fn(() => fakeChild());
    new CoreProcess({ command: "uv", args: ["run"], cwd: "/x", env: { A: "1" } }, spawn as never).start();
    const opts = (spawn.mock.calls[0] as any)[2];
    expect(opts).toMatchObject({ windowsHide: true, cwd: "/x", stdio: ["pipe", "pipe", "pipe"] });
    expect(opts.env).toMatchObject({ A: "1", PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" });
  });
});

describe("como iniciar o núcleo", () => {
  const base = { isPackaged: false, resourcesPath: "/res", appPath: "/proj/app", argv: ["electron", "."], env: {} as NodeJS.ProcessEnv };

  it("desenvolvimento: uv run fidus daemon na raiz do projeto", () => {
    const c = resolveCoreCommand(base);
    expect(c).toMatchObject({ command: "uv", args: ["run", "fidus", "daemon", "--stdin-watch"], cwd: path.resolve("/proj") });
  });
  it("empacotado: o executável em resources/core", () => {
    expect(resolveCoreCommand({ ...base, isPackaged: true, platform: "win32" })).toMatchObject({ command: path.join("/res", "core", "fidus-core.exe"), args: ["daemon", "--stdin-watch"] });
    expect(resolveCoreCommand({ ...base, isPackaged: true, platform: "linux" }).command).toBe(path.join("/res", "core", "fidus-core"));
  });
  it("--simulado e FIDUS_CORE_CMD", () => {
    expect(resolveCoreCommand({ ...base, argv: [...base.argv, "--simulado"] }).args).toContain("--simulado");
    expect(resolveCoreCommand({ ...base, env: { FIDUS_SIMULATED: "1" } }).args).toContain("--simulado");
    const c = resolveCoreCommand({ ...base, env: { FIDUS_CORE_CMD: '["python","-m","fidus"]' } });
    expect(c.command).toBe("python");
    expect(c.args).toEqual(["-m", "fidus", "daemon", "--stdin-watch"]);
  });
});
