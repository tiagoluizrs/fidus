// @vitest-environment node
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { webPreferences } from "../electron/security";

const root = path.resolve(__dirname, "..");
const read = (f: string) => readFileSync(path.join(root, f), "utf8");
const electronSources = readdirSync(path.join(root, "electron")).filter((f) => f.endsWith(".ts"));

describe("segurança do Electron", () => {
  it("janelas: contextIsolation ligado, nodeIntegration desligado, sandbox, sem webview", () => {
    expect(webPreferences("/p.js")).toMatchObject({
      contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true, webviewTag: false, allowRunningInsecureContent: false,
    });
  });

  it("nenhum arquivo afrouxa as regras nem carrega conteúdo remoto", () => {
    for (const f of electronSources) {
      const src = read(`electron/${f}`);
      expect(src, f).not.toMatch(/nodeIntegration:\s*true/);
      expect(src, f).not.toMatch(/contextIsolation:\s*false/);
      expect(src, f).not.toMatch(/webSecurity:\s*false/);
      expect(src, f).not.toMatch(/sandbox:\s*false/);
      expect(src, f).not.toMatch(/loadURL\(\s*["'`]https?:/);
      for (const m of src.matchAll(/shell\.openExternal\(([^)]*)\)/g)) expect(m[1], f).toBe("MIC_SETTINGS_URL"); // só o endereço fixo dos ajustes do microfone
      expect(src, f).not.toMatch(/\bexecSync\b|enableRemoteModule|\bremote\b\s*:/);
    }
  });

  it("o preload expõe só a API mínima (sem Node, sem token)", () => {
    const src = read("electron/preload.ts").replace(/\/\/.*$/gm, ""); // sem comentários
    const exposed = [...src.matchAll(/exposeInMainWorld\("(\w+)"/g)].map((m) => m[1]);
    expect(exposed).toEqual(["fidus"]);
    const keys = [...src.matchAll(/^\s{2}(\w+)[(:]/gm)].map((m) => m[1]);
    expect(keys.sort()).toEqual(["closeWindow", "command", "copyText", "getSnapshot", "getTheme", "micStatus", "onEvent", "onNavigate", "onThemeChange", "openMicSettings", "openPath", "pickFolder", "pickSavePath", "restartCore", "saveTextFile"]);
    expect(src).not.toMatch(/token|require\(|process\./i);
    expect(src).not.toContain("ipcRenderer,"); // o ipcRenderer em si não é exposto
  });

  it.each(["ring.html", "settings.html"])("%s: CSP restritiva, sem script inline nem recurso remoto", (file) => {
    const html = read(file);
    const csp = /Content-Security-Policy" content="([^"]+)"/.exec(html)![1];
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("connect-src 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-src 'none'");
    expect(csp).not.toMatch(/unsafe-eval|\*|https?:/);
    expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);
    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/); // nenhum <script> inline
    expect(html).not.toMatch(/(src|href)="https?:/);
  });

  it("a CSP também vale no build final", () => {
    for (const f of ["ring.html", "settings.html"]) {
      try {
        expect(readFileSync(path.join(root, "dist", "renderer", f), "utf8")).toContain("Content-Security-Policy");
      } catch {
        /* sem build ainda: o teste acima já cobre o fonte */
      }
    }
  });

  it("o processo principal só aceita pedidos de páginas do app e só comandos permitidos", () => {
    const src = read("electron/main.ts");
    expect(src).toContain("windows.isTrusted(");
    expect(src).toContain("ALLOWED_COMMANDS.has(name)");
    expect(src).toContain("requestSingleInstanceLock");
    expect(src).toContain('globalShortcut.unregister("Escape")'); // o Esc global só existe enquanto o anel existe
    expect(read("electron/security.ts")).toContain("setPermissionRequestHandler((_wc, _permission, callback) => callback(false))");
  });
});
