// Servidor de TESTE no navegador: liga as páginas reais (anel e configurações) ao núcleo REAL, sem Electron.
// Só para desenvolvimento (Docker: `docker compose run --rm --service-ports web`). Não entra no app instalado.
// Faz o papel do processo principal: guarda o token do núcleo e só repassa comandos da lista permitida.
import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { BridgeClient } from "./bridge";
import { CoreProcess } from "./core";
import { ALLOWED_COMMANDS, applyEvent } from "./logic";
import { cookieKey, hostAllowed, prepareHtml } from "./webguard";
import type { CoreEvent, Snapshot } from "../src/shared/protocol";

const PORT = Number(process.env.FIDUS_WEB_PORT) || 5174;
const ROOT = path.resolve(__dirname, "..");
const RENDERER = path.join(ROOT, "dist", "renderer");
const KEY = randomBytes(24).toString("base64url");
const MIME: Record<string, string> = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml" };

let snapshot: Snapshot | null = null;
const bridge = new BridgeClient();
const clients = new Set<ServerResponse>();

function send(res: ServerResponse, code: number, body: string | Buffer, type = "application/json; charset=utf-8", extra: Record<string, string> = {}) {
  res.writeHead(code, { "Content-Type": type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...extra });
  res.end(body);
}

async function readBody(req: IncomingMessage): Promise<string> {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const c of req) {
    size += (c as Buffer).length;
    if (size > 1 << 20) throw new Error("pedido grande demais");
    chunks.push(c as Buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
}

const server = createServer(async (req, res) => {
  try {
    if (!hostAllowed(req.headers.host)) return send(res, 403, "host não permitido", "text/plain");
    const url = new URL(req.url ?? "/", "http://localhost");
    // 1ª visita: ?k=CHAVE grava um cookie e limpa o endereço. Sem o cookie, nada (a chave aparece só no terminal).
    if (url.searchParams.get("k") === KEY) {
      return send(res, 302, "", "text/plain", { Location: url.pathname, "Set-Cookie": `fidus_key=${KEY}; HttpOnly; SameSite=Strict; Path=/` });
    }
    if (cookieKey(req.headers.cookie) !== KEY) return send(res, 401, "Abra o endereço completo que aparece no terminal (com ?k=...).", "text/plain");

    if (url.pathname === "/api/snapshot") return send(res, 200, JSON.stringify(snapshot));
    if (url.pathname === "/api/events") {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store", Connection: "keep-alive" });
      res.write(": ok\n\n");
      clients.add(res);
      req.on("close", () => clients.delete(res));
      return;
    }
    if (url.pathname === "/api/command" && req.method === "POST") {
      const { name, args } = JSON.parse(await readBody(req)) as { name: string; args?: Record<string, unknown> };
      if (!ALLOWED_COMMANDS.has(name)) return send(res, 200, JSON.stringify({ type: "reply", id: null, ok: false, error: `Comando não permitido: ${name}` }));
      return send(res, 200, JSON.stringify(await bridge.request(name, args ?? {})));
    }
    if (url.pathname === "/shim.js") return send(res, 200, readFileSync(path.join(ROOT, "scripts", "web-shim.js")), "text/javascript");
    if (url.pathname === "/" || url.pathname === "/index.html") return send(res, 200, readFileSync(path.join(ROOT, "scripts", "web-index.html")), MIME[".html"]);

    const file = path.normalize(path.join(RENDERER, url.pathname));
    if (!file.startsWith(RENDERER + path.sep) || !existsSync(file)) return send(res, 404, "não encontrado", "text/plain");
    const ext = path.extname(file);
    const data = readFileSync(file);
    return send(res, 200, ext === ".html" ? prepareHtml(data.toString("utf8")) : data, MIME[ext] ?? "application/octet-stream");
  } catch (e) {
    send(res, 500, JSON.stringify({ type: "reply", id: null, ok: false, error: String(e) }));
  }
});

// Um comentário a cada 15 s mantém a conexão de eventos viva (proxies do Docker/navegador fecham conexões paradas).
setInterval(() => { for (const c of clients) c.write(": ping

"); }, 15000).unref();

function broadcast(e: CoreEvent) {
  const line = `data: ${JSON.stringify(e)}\n\n`;
  for (const c of clients) c.write(line);
}

// ---- núcleo real, sem áudio ----
const core = new CoreProcess(
  process.env.FIDUS_CORE_CMD
    ? (() => { const p = JSON.parse(process.env.FIDUS_CORE_CMD!) as string[]; return { command: p[0], args: [...p.slice(1), "daemon", "--stdin-watch", "--headless"], cwd: path.resolve(ROOT, "..") }; })()
    : { command: "uv", args: ["run", "--frozen", "fidus", "daemon", "--stdin-watch", "--headless"], cwd: path.resolve(ROOT, "..") },
);
core.on("log", (l: string) => console.log(`[núcleo] ${l}`));
core.on("ready", async (info) => {
  snapshot = await bridge.connect(info.port, info.token);
  broadcast({ type: "ready", protocol: info.protocol, snapshot });
  console.log(`[fidus] núcleo real conectado (sem áudio). Modelo: ${snapshot.model.name}`);
});
bridge.on("event", (e: CoreEvent) => {
  snapshot = applyEvent(snapshot, e);
  broadcast(e);
});
core.on("failed", () => console.error("[fidus] o núcleo não iniciou. Veja as mensagens acima."));
core.start();

process.on("SIGINT", () => void core.stop(() => bridge.request("quit")).finally(() => process.exit(0)));
process.on("SIGTERM", () => void core.stop(() => bridge.request("quit")).finally(() => process.exit(0)));

if (require.main === module) {
  server.listen(PORT, process.env.FIDUS_WEB_BIND || "127.0.0.1", () => {
    console.log(`\n  Fidus (teste no navegador, núcleo real)\n  Abra:  http://127.0.0.1:${PORT}/?k=${KEY}\n`);
  });
}
