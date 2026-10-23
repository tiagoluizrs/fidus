import { ALLOWED_COMMANDS, RingLifecycle, applyEvent, buildTrayTemplate, isTrustedUrl, parseReadyLine, statusText } from "../electron/logic";
import type { Snapshot } from "../src/shared/protocol";

const snap = (over: Partial<Snapshot> = {}): Snapshot => ({
  status: "ready", message: "", state: "idle", mic: "passive",
  character: { id: "alfred", name: "Alfred", call: "ei Alfred", ring: { dark: [], light: [] } },
  default_character: "alfred",
  characters: ["alfred", "donna", "jarbis"].map((id) => ({ id, name: id[0].toUpperCase() + id.slice(1), call: `ei ${id}`, ring: { dark: [], light: [] } })),
  model: { provider: "claude", name: "m", where: "Nuvem" }, calls: { enabled: true, until: null }, muted: false, ...over,
});

describe("linha FIDUS_READY", () => {
  it("lê porta e token", () => {
    const t = "x".repeat(40);
    expect(parseReadyLine(`FIDUS_READY {"port": 51234, "token": "${t}", "protocol": 1}\n`)).toEqual({ port: 51234, token: t, protocol: 1 });
  });
  it("ignora logs, JSON ruim, porta inválida e token curto", () => {
    for (const l of ["Carregando o Whisper...", "FIDUS_READY {", 'FIDUS_READY {"port":0,"token":"' + "x".repeat(40) + '"}', 'FIDUS_READY {"port":5,"token":"curto"}', 'xFIDUS_READY {"port":5}']) {
      expect(parseReadyLine(l)).toBeNull();
    }
  });
});

describe("ciclo de vida da janela do anel", () => {
  const setup = (idle = 6000) => {
    vi.useFakeTimers();
    const log: string[] = [];
    const lc = new RingLifecycle(() => log.push("abre"), () => log.push("fecha"), idle);
    return { lc, log };
  };
  afterEach(() => vi.useRealTimers());

  it("em repouso não existe janela", () => {
    const { lc, log } = setup();
    lc.onState("idle");
    vi.advanceTimersByTime(60000);
    expect(log).toEqual([]);
    expect(lc.isOpen).toBe(false);
  });
  it("abre quando o Fidus é chamado e destrói depois de alguns segundos parado", () => {
    const { lc, log } = setup(6000);
    lc.onState("listening");
    lc.onState("thinking");
    lc.onState("speaking");
    expect(log).toEqual(["abre"]); // uma janela só
    lc.onState("idle");
    vi.advanceTimersByTime(5999);
    expect(log).toEqual(["abre"]);
    vi.advanceTimersByTime(2);
    expect(log).toEqual(["abre", "fecha"]);
  });
  it("atividade durante a espera cancela o fechamento", () => {
    const { lc, log } = setup(6000);
    lc.onState("listening");
    lc.onState("idle");
    vi.advanceTimersByTime(3000);
    lc.onState("listening"); // continuação da conversa
    vi.advanceTimersByTime(60000);
    expect(log).toEqual(["abre"]);
    expect(lc.isOpen).toBe(true);
  });
  it("Esc fecha na hora e só reabre numa interação nova", () => {
    const { lc, log } = setup();
    lc.onState("listening");
    lc.dismiss();
    expect(log).toEqual(["abre", "fecha"]);
    lc.onState("thinking"); // a mesma conversa continua: não reabre
    lc.onState("speaking");
    expect(log).toEqual(["abre", "fecha"]);
    lc.onState("idle");
    lc.onState("listening"); // chamado novo
    expect(log).toEqual(["abre", "fecha", "abre"]);
  });
  it("janela fechada por fora (Alt+F4) não reabre sozinha", () => {
    const { lc, log } = setup();
    lc.onState("listening");
    lc.onClosedExternally();
    lc.onState("thinking");
    expect(log).toEqual(["abre"]);
    expect(lc.isOpen).toBe(false);
  });
});

describe("menu da bandeja", () => {
  const calls: unknown[] = [];
  const handlers = { command: (n: string, a?: object) => calls.push([n, a]), openSettings: (p?: string) => calls.push(["settings", p]), quit: () => calls.push(["quit"]) };
  const labels = (t: ReturnType<typeof buildTrayTemplate>) => t.filter((i) => i.type !== "separator").map((i) => i.label);

  it("tem tudo o que foi pedido, na ordem", () => {
    const t = buildTrayTemplate(snap(), handlers);
    expect(labels(t)).toEqual([
      "Fidus · Escutando: Alfred, Donna, Jarbis", "Personagem padrão", "Alfred", "Donna", "Jarbis",
      "Escutar chamados", "Silenciar microfone", "Abrir Configurações", "Histórico de ações", "Pausar por 1 hora", "Sair do Fidus",
    ]);
  });
  it("personagem padrão é um rádio marcado e os cliques chamam o núcleo", () => {
    const t = buildTrayTemplate(snap({ default_character: "donna" }), handlers);
    const donna = t.find((i) => i.label === "Donna")!;
    expect(donna).toMatchObject({ type: "radio", checked: true });
    expect(t.find((i) => i.label === "Alfred")!.checked).toBe(false);
    calls.length = 0;
    t.find((i) => i.label === "Jarbis")!.click!();
    t.find((i) => i.label === "Escutar chamados")!.click!();
    t.find((i) => i.label === "Silenciar microfone")!.click!();
    t.find((i) => i.label === "Pausar por 1 hora")!.click!();
    t.find((i) => i.label === "Abrir Configurações")!.click!();
    t.find((i) => i.label === "Histórico de ações")!.click!();
    t.find((i) => i.label === "Sair do Fidus")!.click!();
    expect(calls).toEqual([
      ["set_default_character", { id: "jarbis" }], ["calls", { value: false }], ["mute", { value: true }], ["pause", { minutes: 60 }],
      ["settings", undefined], ["settings", "privacidade"], ["quit"],
    ]);
  });
  it("mostra o estado: silenciado, pausado até uma hora e erro; pausa vira 'Retomar'", () => {
    expect(statusText(snap({ muted: true }))).toBe("Microfone silenciado");
    const until = new Date(2026, 9, 23, 15, 30).getTime() / 1000;
    const now = new Date(2026, 9, 23, 14, 30).getTime();
    const paused = snap({ calls: { enabled: false, until } });
    expect(statusText(paused, now)).toBe("Chamados pausados até 15:30");
    const t = buildTrayTemplate(paused, handlers, now);
    expect(t.find((i) => i.label === "Retomar chamados")).toBeTruthy();
    expect(t.find((i) => i.label === "Escutar chamados")!.checked).toBe(false);
    expect(statusText(snap({ status: "error", message: "sem microfone" }))).toBe("Erro: sem microfone");
    expect(statusText(null)).toBe("Iniciando…");
  });
  it("antes de o núcleo ficar pronto, os controles ficam desabilitados", () => {
    const t = buildTrayTemplate(null, handlers);
    expect(t.find((i) => i.label === "Silenciar microfone")!.enabled).toBe(false);
    expect(t.find((i) => i.label === "Abrir Configurações")!.enabled).not.toBe(false);
  });
});

describe("acompanhar eventos para a bandeja", () => {
  it("aplica estado, calls, personagem e status", () => {
    let s: Snapshot | null = snap();
    s = applyEvent(s, { type: "state", state: "muted", mic: "muted" });
    expect(s).toMatchObject({ state: "muted", muted: true });
    s = applyEvent(s, { type: "calls", enabled: false, until: 5 });
    expect(s!.calls).toEqual({ enabled: false, until: 5 });
    s = applyEvent(s, { type: "status", core: "error", message: "x" });
    expect(s).toMatchObject({ status: "error", message: "x" });
    expect(applyEvent(null, { type: "state", state: "idle", mic: "passive" })).toBeNull();
  });
});

describe("regras de confiança", () => {
  it("só páginas do próprio app são confiáveis", () => {
    const base = "file:///opt/fidus/dist/renderer/";
    expect(isTrustedUrl(base + "ring.html", base)).toBe(true);
    for (const u of ["https://evil.example/ring.html", "file:///tmp/outro.html", base + "../../x.html", "about:blank"]) expect(isTrustedUrl(u, base)).toBe(false);
  });
  it("a página não pode mandar `quit` ao núcleo", () => {
    expect(ALLOWED_COMMANDS.has("quit")).toBe(false);
    expect(ALLOWED_COMMANDS.has("mute")).toBe(true);
    expect([...ALLOWED_COMMANDS].some((c) => /exec|shell|eval/.test(c))).toBe(false);
  });
});
