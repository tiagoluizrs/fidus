// Núcleo de mentira para testar as telas de Configurações: guarda estado na memória e responde como o real.
import type { CoreEvent, FidusApi, Reply, Snapshot } from "../src/shared/protocol";

type Obj = Record<string, any>;

// No Vitest vira vi.fn (dá para espiar chamadas); no navegador (npm run dev:web) é a própria função.
const vf: any = (globalThis as any).vi?.fn ?? ((f?: any) => f ?? (() => {}));

export function makeProfile(id = "alfred"): Obj {
  const item = (iid: string, text: string, origin = "padrao", enabled = true) => ({ id: iid, text, enabled, origin, contexts: [] });
  return {
    id, name: id[0].toUpperCase() + id.slice(1), call: `ei ${id}`, summary: "", ring: { dark: ["#FF6A3D", "#FF5C9E", "#3D8BFF"], light: ["#F2541F", "#E8307F", "#1F6BF2"] },
    is_default: id === "alfred", edited: false,
    personality: { base_style: "padrao", default_style: "padrao", extra: "", controls: { formalidade: { value: 90, default: 90 }, humor: { value: 20, default: 20 }, aspereza: { value: 5, default: 5 }, iniciativa: { value: 35, default: 35 }, detalhe: { value: 50, default: 50 } } },
    address: { mode: "fixed", fixed: "senhor", items: [item("t1", "senhor"), item("t2", "senhora")], deleted: [] },
    phrases: Object.fromEntries(["inicio", "concluir", "confirmar", "erro", "despedida"].map((m) => [m, { items: [item(`${m}1`, `Frase de ${m} um.`), item(`${m}2`, `Frase de ${m} dois.`)], deleted: [] as Obj[] }])),
    voice: { engine: "sapi", voice: "", pitch: 0, rate: 0, default: { engine: "sapi", voice: "", pitch: 0, rate: 0 } },
    variables: ["{tratamento}", "{nome}", "{sobrenome}", "{periodo}", "{hora}", "{dia}", "{saudacao}"],
  };
}

export function installFakeCore(init: { effective?: Obj; services?: Obj[]; micStatus?: string; ollamaRunning?: boolean } = {}) {
  const calls: [string, Obj][] = [];
  const profiles: Record<string, Obj> = { alfred: makeProfile("alfred"), donna: makeProfile("donna"), jarbis: makeProfile("jarbis") };
  const deletedStash: Record<string, Obj[]> = {};
  const effective: Obj = {
    "app.tema": "sistema", "app.iniciar_com_windows": false, "app.icone_bandeja": true, "app.icone": "colorido", "chamados.modo": "auto", "app.janela_inatividade_s": 6,
    "chamados.sensibilidade": 60, "chamados.esperar_fala_s": 5, "chamados.som_ao_ouvir": false, "voz.atalho": "ctrl+alt+space",
    "voz.atalho_ativo": true, "voz.microfone": "", "voz.modelo_whisper": "small", "voz.velocidade_voz": 0, "voz.responder_em_voz": true,
    "usuario.nome": "", "usuario.sobrenome": "", "memoria.aprender": true, "memoria.perguntar_antes_de_guardar": false,
    "privacidade.registrar_acoes": true, "privacidade.guardar_log_dias": 30, "privacidade.guardar_historico": true,
    "privacidade.avisar_microfone": true, "modelo.provedor": "claude", "modelo.claude": "claude-sonnet-5-5", "modelo.gemini": "gemini-2.5-flash", "modelo.local": "qwen3:8b", "modelo.local_acoes": false, "modelo.local_acoes_ciente": false, "arquivos.pastas_liberadas": [], ...init.effective,
  };
  const kokoro: Obj = { supported: true, installed: false, download_mb: 116, busy: false, voices: [{ id: "pf_dora", label: "Dora (feminina)", installed: false }, { id: "pm_alex", label: "Alex (masculina)", installed: false }] };
  const piper: Obj = { supported: true, installed: false, download_mb: 22, busy: false, voices: [
    { id: "pt_BR-faber-medium", label: "Faber", size_mb: 63, installed: false }, { id: "pt_BR-cadu-medium", label: "Cadu", size_mb: 63, installed: false }] };
  const pulled: string[] = [];
  const cloud: Obj = { has_key: false, stored: false, has_sample: false };
  const memory: Obj[] = [];
  const log: Obj[] = [{ ts: "2026-10-23T12:00:00+00:00", tool: "abrir_app", risk: "escrita", decision: "confirmado", args: {}, result: "" }];
  let nextMem = 1;
  let calls_state = { enabled: true, until: null as number | null };
  let key = { stored: true, source: "cofre" };
  let gkey = { stored: false, source: "nenhuma" };
  let googleCredentials = true;
  let services: Obj[] = init.services ?? [
    { id: "gmail", kind: "email", name: "Gmail", connected: true, write: false, write_label: "criar rascunhos" },
    { id: "outlook", kind: "email", name: "Outlook", coming_soon: true },
    { id: "slack", kind: "chat", name: "Slack", connected: false, write: false, write_label: "responder mensagens", channels: [] },
    { id: "teams", kind: "chat", name: "Teams", coming_soon: true },
    { id: "agenda", kind: "calendar", name: "Google Agenda", connected: false, write: false, write_label: "criar e alterar eventos" },
    { id: "msagenda", kind: "calendar", name: "Microsoft Agenda", coming_soon: true },
  ];
  let listener: (e: CoreEvent) => void = () => {};
  const fail = (error: string): Reply => ({ type: "reply", id: null, ok: false, error });
  const ok = (data: Obj = {}): Reply => ({ type: "reply", id: "1", ok: true, data });

  const chars = () => Object.values(profiles).map((p) => ({ id: p.id, name: p.name, call: p.call, summary: "", ring: p.ring, is_default: p.is_default, edited: p.edited }));

  function characters(a: Obj): Reply {
    if (a.op === "list") return ok({ characters: chars() });
    const p = profiles[a.id];
    if (!p) return fail("Personagem 'x' não existe.");
    const L = (name: string) => (name === "tratamentos" ? p.address : p.phrases[name]);
    switch (a.op) {
      case "get": return ok(p);
      case "set_control": { const c = p.personality.controls[a.control]; c.value = a.value; p.edited = true; break; }
      case "reset_control": { const c = p.personality.controls[a.control]; c.value = c.default; break; }
      case "set_style": p.personality.base_style = a.style; p.edited = true; break;
      case "set_extra": p.personality.extra = a.text; break;
      case "reset_personality": Object.values(p.personality.controls).forEach((c: any) => (c.value = c.default)); p.personality.base_style = "padrao"; p.personality.extra = ""; break;
      case "set_address_mode": p.address.mode = a.mode; if (a.fixed !== undefined) p.address.fixed = a.fixed; break;
      case "item_edit": { const it = L(a.list).items.find((i: Obj) => i.id === a.item); it.text = a.text; it.origin = "editada"; break; }
      case "item_enable": L(a.list).items.find((i: Obj) => i.id === a.item).enabled = a.enabled; break;
      case "item_delete": { const l = L(a.list); const it = l.items.find((i: Obj) => i.id === a.item); l.items = l.items.filter((i: Obj) => i !== it); if (it.origin === "padrao") l.deleted.push({ id: it.id, text: it.text }); break; }
      case "item_add": L(a.list).items.push({ id: `u_${Math.random().toString(16).slice(2, 8)}`, text: a.text, enabled: true, origin: "usuario", contexts: [] }); break;
      case "restore_deleted": { const l = L(a.list); l.deleted.forEach((d: Obj) => l.items.push({ ...d, enabled: true, origin: "padrao", contexts: [] })); l.deleted = []; break; }
      case "reset_list": { const l = L(a.list); l.items = l.items.filter((i: Obj) => i.origin !== "usuario").map((i: Obj) => ({ ...i, enabled: true, origin: "padrao" })); l.deleted.forEach((d: Obj) => l.items.push({ ...d, enabled: true, origin: "padrao", contexts: [] })); l.deleted = []; break; }
      case "set_voice": Object.assign(p.voice, a); delete p.voice.op; delete p.voice.id; break;
      case "reset_voice": Object.assign(p.voice, p.voice.default); break;
      case "preview": return ok({ spoken: false, reason: "A voz só está disponível com o núcleo real." });
      default: return fail(`Operação desconhecida: ${a.op}`);
    }
    return ok(p);
  }

  function handle(name: string, a: Obj): Reply {
    switch (name) {
      case "get_settings": return ok({ settings: {}, effective, schema: Object.keys(effective), claude_models: ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"], gemini_models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"], restart_required: [] });
      case "set_settings": {
        for (const [k, v] of Object.entries<any>(a.patch)) {
          if (k === "voz.velocidade_voz" && (v < -10 || v > 10)) return fail("voz.velocidade_voz: valor fora do intervalo -10 a 10");
          effective[k] = v;
        }
        if (a.patch["modelo.local_acoes_ciente"] === false && !("modelo.local_acoes" in a.patch)) effective["modelo.local_acoes"] = false;
        if (effective["modelo.local_acoes"] && !effective["modelo.local_acoes_ciente"]) { effective["modelo.local_acoes"] = false; return fail("Para liberar ações com o modelo local, marque que você entende os riscos."); }
        const need = Object.keys(a.patch).filter((k) => ["voz.modelo_whisper", "voz.microfone", "voz.atalho"].includes(k));
        return ok({ saved: Object.keys(a.patch), restart_required: need });
      }
      case "local_models":
        if (a.op === "pull") { pulled.push(a.model); return ok({ started: true }); }
        return ok({ running: init.ollamaRunning !== false, models: ["qwen3:8b", "llama3.1:8b", ...pulled], suggested: "qwen3:8b", url: "http://127.0.0.1:11434", busy: false });
      case "calls": calls_state = { enabled: a.value, until: null }; return ok({ enabled: a.value });
      case "set_default_character": Object.values(profiles).forEach((p) => (p.is_default = p.id === a.id)); return ok({ default_character: a.id });
      case "characters": return characters(a);
      case "kokoro": {
        if (a.op === "install") kokoro.installed = true;
        return ok(a.op === "install" ? { started: true } : { ...kokoro, voices: kokoro.voices.map((x: Obj) => ({ ...x, installed: kokoro.installed })) });
      }
      case "piper": {
        if (a.op === "install") piper.installed = true;
        if (a.op === "download_voice") piper.voices.find((x: Obj) => x.id === a.voice).installed = true;
        if (a.op === "remove_voice") piper.voices.find((x: Obj) => x.id === a.voice).installed = false;
        return ok(a.op === "status" || a.op === undefined || a.op === "remove_voice" ? { ...piper, voices: piper.voices.map((x: Obj) => ({ ...x })) } : { started: true }); // cópia: o React ignora o mesmo objeto
      }
      case "voice_cloud": {
        if (a.op === "set_key") { if (String(a.value).length < 20) return fail("Isso não parece uma chave de API do serviço de voz."); cloud.has_key = cloud.stored = true; }
        if (a.op === "clear_key") cloud.has_key = cloud.stored = false;
        if (a.op === "design_preview") return ok({ ...cloud, previews: [{ id: "g1" }, { id: "g2" }] });
        if (a.op === "save_preview") { const p = profiles[a.id]; Object.assign(p.voice, { engine: "descricao", voice: "voz123", description: a.description }); }
        if (a.op === "clone") { if (a.consent !== true) return fail("Marque que você consente em gravar e usar a sua voz."); profiles[a.id].voice.engine = "propria"; profiles[a.id].voice.voice = "clone1"; }
        if (a.op === "delete_voice") Object.assign(profiles[a.id].voice, { engine: "sapi", voice: "", description: "" });
        return ok({ ...cloud });
      }
      case "voices": return ok({ engine: "sapi", voices: ["Microsoft Maria", "Microsoft Daniel"] });
      case "devices": return ok({ devices: [{ index: 1, name: "Microfone (Realtek)", default: true }, { index: 4, name: "Headset USB", default: false }] });
      case "api_key":
        if (a.provider === "gemini" && a.op === "models") return ok({ models: ["gemini-3.6-flash", "gemini-2.5-pro"], best: "gemini-3.6-flash" });
        if (a.provider === "gemini") { if (a.op === "set") gkey = { stored: true, source: "cofre" }; return ok(gkey); }
        if (a.op === "set") { if (!String(a.value).startsWith("sk-ant-")) return fail("Isso não parece uma chave da Anthropic (começa com sk-ant-)."); key = { stored: true, source: "cofre" }; }
        return ok(key);
      case "memory": {
        if (a.op === "list") { const q = String(a.query ?? "").toLowerCase(); return ok({ entries: memory.filter((m) => !q || m.text.toLowerCase().includes(q)), sections: ["perfil", "rotinas", "contatos"], tags: ["geral", "pessoal", "trabalho"], learn: true, ask_before_saving: false }); }
        if (a.op === "add") { const e = { id: `m${nextMem++}`, section: a.section || "perfil", text: a.text, tag: a.tag || null, ts: "2026-10-20", source: "usuario" }; memory.push(e); return ok({ entry: e }); }
        if (a.op === "edit") { const e = memory.find((m) => m.id === a.id)!; if (a.text !== undefined) e.text = a.text; if (a.tag !== undefined) e.tag = a.tag || null; return ok({ entry: e }); }
        if (a.op === "delete") { if (a.confirm !== true) return fail("Ação sem volta: precisa de confirmação explícita (confirm: true)."); memory.splice(memory.findIndex((m) => m.id === a.id), 1); return ok({}); }
        if (a.op === "delete_all") { if (a.confirm !== true) return fail("Ação sem volta: precisa de confirmação explícita (confirm: true)."); memory.length = 0; return ok({ deleted: {} }); }
        if (a.op === "export") return ok({ markdown: "# Memória do Fidus\n", filename: "memoria-fidus.md" });
        return fail("op");
      }
      case "accounts": {
        if (a.op === "list") return ok({ google_credentials: googleCredentials, services });
        if (a.op === "google_credentials") { if (!String(a.json).includes("installed")) return fail("O arquivo não tem os campos esperados."); googleCredentials = true; return ok({ google_credentials: true, services }); }
        if (a.op === "google_credentials_remove") { googleCredentials = false; return ok({ google_credentials: false, services }); }
        const s = services.find((x) => x.id === a.service)!;
        if (a.op === "connect") { if (a.service === "slack") { if (!a.token) return fail("Cole o token de usuário do Slack (xoxp-...)."); s.connected = true; s.write = a.write === true; return ok({ google_credentials: true, services }); } return ok({ started: true }); }
        if (a.op === "disconnect") { s.connected = false; return ok({ google_credentials: true, services }); }
        if (a.op === "channel_add") { s.channels.push(a.name); return ok({ google_credentials: true, services }); }
        if (a.op === "channel_remove") { s.channels = s.channels.filter((c: string) => c !== a.name); return ok({ google_credentials: true, services }); }
        return fail("op");
      }
      case "privacy": {
        if (a.op === "get") return ok({ folders: effective["arquivos.pastas_liberadas"], log_actions: true, log_days: 30, keep_history: true, data_dir: "C:\\Users\\voce\\.fidus", log_path: "C:\\Users\\voce\\.fidus\\actions.log" });
        if (a.op === "log") return ok({ entries: log });
        if (["clear_history", "clear_log", "clear_all"].includes(a.op)) return a.confirm === true ? ok({}) : fail("Ação sem volta: precisa de confirmação explícita (confirm: true).");
        if (a.op === "export") return ok({ path: a.path, files: [] });
        return fail("op");
      }
      case "about": return ok(a.op === "diagnostics" ? { diagnostics: "version: 0.1.0" } : { version: "0.1.0", python: "3.12", platform: "Windows", model: "claude-sonnet-5-5", data_dir: "C:\\Users\\voce\\.fidus", whisper: "small" });
      default: return fail(`comando sem implementação no teste: ${name}`);
    }
  }

  const snapshot = { status: "ready", message: "", state: "idle", mic: "passive", character: chars()[0], default_character: "alfred", characters: [], model: { provider: "claude", name: "x", where: "Nuvem" }, calls: calls_state, muted: false } as unknown as Snapshot;
  const api = {
    command: vf(async (name: string, args: Obj = {}) => { calls.push([name, args]); return handle(name, args); }),
    getSnapshot: vf(async () => snapshot),
    getTheme: vf(async () => "light" as const),
    onThemeChange: vf(() => () => {}),
    onEvent: vf((cb: (e: CoreEvent) => void) => { listener = cb; return () => {}; }),
    onNavigate: vf(() => () => {}),
    closeWindow: vf(),
    pickFolder: vf(async () => "C:\\Projetos" as string | null),
    pickSavePath: vf(async () => "C:\\saida\\meus-dados.zip" as string | null),
    saveTextFile: vf(async () => true),
    openPath: vf(async () => true),
    openMicSettings: vf(async () => {}),
    micStatus: vf(async () => init.micStatus ?? "granted"),
    restartCore: vf(async () => {}),
    copyText: vf(async () => {}),
  };
  window.fidus = api as unknown as FidusApi;
  return { api, calls, profiles, effective, memory, piper, cloud, emit: (e: CoreEvent) => listener(e), deletedStash, services: () => services, setServices: (s: Obj[]) => (services = s) };
}

/** Comandos recebidos com determinado nome (e, opcionalmente, operação). */
export const sent = (calls: [string, Obj][], name: string, op?: string) => calls.filter(([n, a]) => n === name && (op === undefined || a.op === op));
