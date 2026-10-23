import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useCore } from "../core";
import { Badge, Button, Dialog, Row, Section, Slider } from "../ui";

type Mutate = (op: string, args?: Record<string, unknown>) => Promise<boolean>;
export interface VoiceProfile {
  id: string;
  name: string;
  voice: { engine: string; voice: string; pitch: number; rate: number; description?: string; effect?: string; timbre?: number; edge?: number; pronunciations?: string };
}
type View = "sapi" | "piper" | "kokoro" | "descricao" | "propria";
const ENGINES = ["sapi", "piper", "kokoro", "descricao", "propria"];

interface PiperStatus { supported: boolean; installed: boolean; download_mb: number; busy: boolean; voices: { id: string; label: string; size_mb: number; installed: boolean }[] }
interface CloudStatus { has_key: boolean; stored: boolean; has_sample: boolean; previews?: { id: string }[] }

const READ_TEXT = "Olá, eu sou o seu assistente. Hoje o dia está calmo e eu vou ajudar com a agenda, os e-mails e os lembretes. Se precisar de algo, é só chamar.";

export function VoiceTab({ p, mutate }: { p: VoiceProfile; mutate: Mutate }) {
  const { call, notify } = useCore();
  const v = p.voice;
  const [view, setView] = useState<View>((ENGINES.includes(v.engine) ? v.engine : "sapi") as View);
  useEffect(() => setView((ENGINES.includes(v.engine) ? v.engine : "sapi") as View), [v.engine, p.id]);
  const cloud = view === "descricao" || view === "propria";

  return (
    <>
      <Section title="Motor de voz">
        <div className="engines" role="radiogroup" aria-label="Motor de voz">
          <EngineCard on={view === "sapi"} title="Voz do sistema" text="Já vem no computador. Qualidade varia." tag="Local" onPick={() => { setView("sapi"); void mutate("set_voice", { engine: "sapi", voice: "" }); }} />
          <EngineCard on={view === "piper"} title="Piper" text="Vozes neurais que rodam no computador." tag="Local" onPick={() => { setView("piper"); if (v.engine !== "piper") void mutate("set_voice", { engine: "piper", voice: "" }); }} />
          <EngineCard on={view === "kokoro"} title="Kokoro" text="Voz neural local com opção feminina em português." tag="Local" onPick={() => { setView("kokoro"); if (v.engine !== "kokoro") void mutate("set_voice", { engine: "kokoro", voice: "pf_dora" }); }} />
          <EngineCard on={view === "descricao"} title="Voz por descrição" text="Você descreve o tom e o sotaque e o serviço cria uma voz original." tag="Nuvem" cloud onPick={() => setView("descricao")} />
          <EngineCard on={view === "propria"} title="Sua própria voz" text="Grave sua voz, com o seu consentimento, para usar neste personagem." tag="Nuvem" cloud onPick={() => setView("propria")} />
        </div>
        {view === "sapi" && <SystemVoice voice={v.voice} mutate={mutate} />}
        {view === "piper" && <PiperPanel voice={v.engine === "piper" ? v.voice : ""} mutate={mutate} />}
        {view === "kokoro" && <KokoroPanel voice={v.engine === "kokoro" ? v.voice : ""} mutate={mutate} />}
        {cloud && <CloudPanel kind={view as "descricao" | "propria"} p={p} />}
      </Section>
      <Section title="Tom e velocidade">
        <Slider label="Tom" value={v.pitch} min={-10} max={10} left="Mais grave" right="Mais agudo" onChange={(n) => mutate("set_voice", { pitch: n })} />
        <Slider label="Velocidade" value={v.rate} min={-10} max={10} left="Mais devagar" right="Mais rápido" onChange={(n) => mutate("set_voice", { rate: n })} />
        {(view === "piper" || view === "kokoro") && (
          <>
            <Slider label="Timbre" value={v.timbre ?? 0} min={-10} max={10} left="Mais fechada" right="Mais aberta" onChange={(n) => mutate("set_voice", { timbre: n })} />
            <Slider label="Ponta" value={v.edge ?? 0} min={-10} max={10} left="Mais macia" right="Mais pontuda" onChange={(n) => mutate("set_voice", { edge: n })} />
          </>
        )}
        {(view === "piper" || view === "kokoro") && (
          <Row label="Pronúncia" htmlFor="pronunciations" hint="Como a voz deve ler certas palavras, só na fala. Formato: palavra=como ler; outra=como ler. Ex.: Alfred=Al fred (use “Aal fred” para alongar o “Al”).">
            <input id="pronunciations" type="text" defaultValue={v.pronunciations ?? ""} key={`${p.id}:${v.pronunciations ?? ""}`} onBlur={(e) => { if (e.target.value !== (v.pronunciations ?? "")) void mutate("set_voice", { pronunciations: e.target.value }); }} />
          </Row>
        )}
        {(view === "piper" || view === "kokoro") && (
          <Row label="Voz robótica" hint="Deixa a voz metálica e sintética, como um assistente de IA. Vale para Piper e Kokoro.">
            <label className="check"><input type="checkbox" checked={v.effect === "robo"} onChange={(e) => void mutate("set_voice", { effect: e.target.checked ? "robo" : "" })} /><span>Usar efeito de robô</span></label>
          </Row>
        )}
        {cloud && <p className="muted small">Tom e velocidade valem para as vozes locais. Nas vozes da nuvem, quem manda é o serviço.</p>}
        <p className="muted small">O Fidus não clona vozes de atores nem de outras pessoas. Voz própria só com gravação e consentimento de quem fala.</p>
        <div className="actions">
          <Button onClick={async () => {
            const r = await call<{ spoken: boolean; reason?: string }>("characters", { op: "preview", id: p.id });
            if (r) notify("info", r.spoken ? "Falando uma amostra…" : (r.reason ?? "Sem voz disponível."));
          }}>Ouvir amostra</Button>
          <Button onClick={() => mutate("reset_voice")}>Restaurar voz padrão</Button>
        </div>
      </Section>
      <footer className="tab-foot"><span className="muted small">Salvo automaticamente</span></footer>
    </>
  );
}

function SystemVoice({ voice, mutate }: { voice: string; mutate: Mutate }) {
  const { call } = useCore();
  const [voices, setVoices] = useState<string[]>([]);
  useEffect(() => void call<{ voices: string[] }>("voices", {}, { quiet: true }).then((d) => d && setVoices(d.voices)), [call]);
  return (
    <Row label="Voz" htmlFor="voice-select" hint={voices.length ? undefined : "A lista de vozes aparece com o núcleo real em execução."}>
      <select id="voice-select" value={voice} onChange={(e) => mutate("set_voice", { voice: e.target.value })}>
        <option value="">Português (Brasil) ou a padrão do sistema</option>
        {voices.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
    </Row>
  );
}

// ---------------------------------------------------------------- Piper

function PiperPanel({ voice, mutate }: { voice: string; mutate: Mutate }) {
  const { call, subscribe, notify } = useCore();
  const [st, setSt] = useState<PiperStatus | null>(null);
  const [progress, setProgress] = useState<{ what: string; pct: number } | null>(null);
  const load = useCallback(async () => setSt(await call<PiperStatus>("piper", {}, { quiet: true })), [call]);
  useEffect(() => void load(), [load]);
  useEffect(() => subscribe((e) => {
    if (e.type !== "voice_setup") return;
    if (e.state === "progress") setProgress({ what: e.what, pct: e.total ? Math.round(((e.done ?? 0) / e.total) * 100) : 0 });
    else {
      setProgress(null);
      if (e.state === "error") notify("error", e.message ?? "Falha ao baixar.");
      void load();
    }
  }), [subscribe, load, notify]);

  if (!st) return <p className="muted small">Verificando o Piper…</p>;
  if (!st.supported) return <p className="muted small">O instalador do Piper é só para Windows.</p>;
  const busy = st.busy || progress !== null;
  const bar = (what: string) => progress?.what === what ? <progress max={100} value={progress.pct} aria-label={`Baixando ${what}`}>{progress.pct}%</progress> : null;

  return (
    <div className="piper">
      <Row label="Programa do Piper" hint={st.installed ? "Instalado." : `Baixa ${st.download_mb} MB do GitHub, uma vez. Nada é enviado: só baixa.`}>
        <span className="inline">
          <Badge tone={st.installed ? "ok" : "neutral"}>{st.installed ? "Instalado" : "Não instalado"}</Badge>
          {!st.installed && <Button disabled={busy} onClick={() => void call("piper", { op: "install" }).then(load)}>Instalar o Piper</Button>}
        </span>
      </Row>
      {bar("piper")}
      <ul className="voices" aria-label="Vozes do Piper">
        {st.voices.map((x) => (
          <li key={x.id}>
            <label className="check">
              <input type="radio" name="piper-voice" disabled={!x.installed} checked={voice === x.id} onChange={() => void mutate("set_voice", { engine: "piper", voice: x.id })} />
              <span>{x.label} <span className="muted small">· português do Brasil · masculina · {x.size_mb} MB</span></span>
            </label>
            {x.installed
              ? <Button aria-label={`Remover a voz ${x.label}`} disabled={busy} onClick={() => void call("piper", { op: "remove_voice", voice: x.id }).then(load)}>Remover</Button>
              : <Button aria-label={`Baixar a voz ${x.label}`} disabled={busy} onClick={() => void call("piper", { op: "download_voice", voice: x.id }).then(load)}>Baixar</Button>}
            {bar(x.id)}
          </li>
        ))}
      </ul>
      {st.installed && !st.voices.some((x) => x.installed) && <p className="muted small">Baixe pelo menos uma voz para usar o Piper.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- Kokoro

interface KokoroStatus { supported: boolean; installed: boolean; download_mb: number; busy: boolean; voices: { id: string; label: string; installed: boolean }[] }

function KokoroPanel({ voice, mutate }: { voice: string; mutate: Mutate }) {
  const { call, subscribe, notify } = useCore();
  const [st, setSt] = useState<KokoroStatus | null>(null);
  const [pct, setPct] = useState<number | null>(null);
  const load = useCallback(async () => setSt(await call<KokoroStatus>("kokoro", {}, { quiet: true })), [call]);
  useEffect(() => void load(), [load]);
  useEffect(() => subscribe((e) => {
    if (e.type !== "voice_setup" || e.what !== "kokoro") return;
    if (e.state === "progress") setPct(e.total ? Math.round(((e.done ?? 0) / e.total) * 100) : 0);
    else {
      setPct(null);
      if (e.state === "error") notify("error", e.message ?? "Falha ao baixar.");
      void load();
    }
  }), [subscribe, load, notify]);

  if (!st) return <p className="muted small">Verificando o Kokoro…</p>;
  if (!st.supported) return <p className="muted small">O Kokoro não está disponível nesta versão do Fidus.</p>;
  const busy = st.busy || pct !== null;
  return (
    <div className="piper">
      <Row label="Modelo do Kokoro" hint={st.installed ? "Instalado." : `Baixa cerca de ${st.download_mb} MB do GitHub, uma vez. Nada é enviado: só baixa.`}>
        <span className="inline">
          <Badge tone={st.installed ? "ok" : "neutral"}>{st.installed ? "Instalado" : "Não instalado"}</Badge>
          {!st.installed && <Button disabled={busy} onClick={() => void call("kokoro", { op: "install" }).then(load)}>Instalar o Kokoro</Button>}
          {st.installed && <Button aria-label="Remover o Kokoro" disabled={busy} onClick={() => void call("kokoro", { op: "remove" }).then(load)}>Remover</Button>}
        </span>
      </Row>
      {pct !== null && <progress max={100} value={pct} aria-label="Baixando o Kokoro">{pct}%</progress>}
      <ul className="voices" aria-label="Vozes do Kokoro">
        {st.voices.map((x) => (
          <li key={x.id}>
            <label className="check">
              <input type="radio" name="kokoro-voice" disabled={!x.installed} checked={voice === x.id} onChange={() => void mutate("set_voice", { engine: "kokoro", voice: x.id })} />
              <span>{x.label} <span className="muted small">· português do Brasil</span></span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- nuvem (ElevenLabs)

function CloudPanel({ kind, p }: { kind: "descricao" | "propria"; p: VoiceProfile }) {
  const { call, notify } = useCore();
  const [st, setSt] = useState<CloudStatus | null>(null);
  const [keyDialog, setKeyDialog] = useState(false);
  const [key, setKey] = useState("");
  const refresh = useCallback(async () => { const d = await call<CloudStatus>("voice_cloud", {}, { quiet: true }); if (d) setSt(d); }, [call]);
  useEffect(() => void refresh(), [refresh]);
  const mine = p.voice.engine === kind && !!p.voice.voice;

  const saveKey = async () => {
    const r = await call<CloudStatus>("voice_cloud", { op: "set_key", value: key });
    setKey("");
    if (r) { setSt(r); setKeyDialog(false); notify("ok", "Chave guardada no cofre do sistema."); }
  };
  const removeVoice = async () => {
    if (await call("voice_cloud", { op: "delete_voice", id: p.id })) notify("ok", "Voz apagada do serviço e do personagem.");
  };

  return (
    <div className="cloud">
      <div className="risk" role="note">
        <strong>Esta opção usa a internet</strong>
        <p className="small">Cada frase que o {p.name} fala é enviada ao serviço de voz (ElevenLabs), na <em>sua</em> conta. {kind === "propria" ? "A sua gravação também é enviada para criar a voz. " : ""}A cota e o custo são seus; há plano grátis (crie a conta em elevenlabs.io). Prefere tudo no computador? Use Piper ou a voz do sistema.</p>
      </div>
      <Row label="Chave de API do serviço de voz" hint="Fica no cofre do Windows e nunca é mostrada de novo.">
        <span className="inline">
          <Badge tone={st?.has_key ? "ok" : "neutral"}>{st?.has_key ? "Guardada no cofre do sistema" : "Não definida"}</Badge>
          <Button onClick={() => setKeyDialog(true)}>{st?.has_key ? "Alterar" : "Definir"}</Button>
          {st?.stored && <Button onClick={() => void call("voice_cloud", { op: "clear_key" }).then(refresh)}>Remover</Button>}
        </span>
      </Row>
      {mine && (
        <Row label="Voz criada" hint="Está na sua conta do serviço. Apagar remove de lá também.">
          <span className="inline"><Badge tone="ok">Em uso</Badge><Button variant="danger" onClick={() => void removeVoice()}>Apagar esta voz do serviço</Button></span>
        </Row>
      )}
      {kind === "descricao" ? <DesignVoice p={p} disabled={!st?.has_key} onChanged={refresh} /> : <OwnVoice p={p} disabled={!st?.has_key} status={st} onChanged={refresh} />}
      {keyDialog && (
        <Dialog title="Chave de API do serviço de voz" onClose={() => { setKeyDialog(false); setKey(""); }}>
          <p className="muted">Cole a chave da sua conta no ElevenLabs. Ela vai direto para o cofre do Windows.</p>
          <div className="field">
            <label htmlFor="voice-key" className="row-label">Chave de API</label>
            <input id="voice-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
          </div>
          <div className="dialog-actions">
            <Button onClick={() => { setKeyDialog(false); setKey(""); }}>Cancelar</Button>
            <Button variant="primary" disabled={key.trim().length < 20} onClick={() => void saveKey()}>Guardar</Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function DesignVoice({ p, disabled, onChanged }: { p: VoiceProfile; disabled: boolean; onChanged: () => void }) {
  const { call, notify } = useCore();
  const [text, setText] = useState(p.voice.description || "");
  const [previews, setPreviews] = useState<{ id: string }[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setText(p.voice.description || ""); setPreviews([]); }, [p.id, p.voice.description]);
  const generate = async () => {
    setBusy(true);
    const r = await call<CloudStatus>("voice_cloud", { op: "design_preview", description: text });
    setBusy(false);
    if (r?.previews) setPreviews(r.previews);
  };
  return (
    <div className="field">
      <label htmlFor="voice-desc" className="row-label">Descreva a voz do {p.name}</label>
      <div className="inline">
        <textarea id="voice-desc" rows={3} value={text} maxLength={1000} placeholder="Masculina, grave e calma. Elegante, de sotaque britânico, ritmo pausado." onChange={(e) => setText(e.target.value)} />
        <Button variant="primary" disabled={disabled || busy || text.trim().length < 20} onClick={() => void generate()}>{busy ? "Gerando…" : "Gerar prévia"}</Button>
      </div>
      {disabled && <p className="muted small">Defina a chave de API acima para gerar prévias.</p>}
      {previews.length > 0 && (
        <ul className="voices" aria-label="Prévias">
          {previews.map((pr, i) => (
            <li key={pr.id}>
              <span>Prévia {i + 1}</span>
              <Button aria-label={`Ouvir a prévia ${i + 1}`} onClick={() => void call("voice_cloud", { op: "play_preview", preview: pr.id })}>Ouvir</Button>
              <Button variant="primary" aria-label={`Usar a prévia ${i + 1}`} onClick={async () => {
                if (await call("voice_cloud", { op: "save_preview", id: p.id, preview: pr.id, description: text })) { setPreviews([]); notify("ok", `Voz criada para o ${p.name}.`); onChanged(); }
              }}>Usar esta voz</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OwnVoice({ p, disabled, status, onChanged }: { p: VoiceProfile; disabled: boolean; status: CloudStatus | null; onChanged: () => void }) {
  const { call, subscribe, notify } = useCore();
  const [consent, setConsent] = useState(false);
  const [rec, setRec] = useState<{ elapsed: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => subscribe((e) => {
    if (e.type !== "voice_record") return;
    if (e.state === "recording") setRec({ elapsed: e.elapsed, total: e.total });
    else { setRec(null); onChanged(); }
  }), [subscribe, onChanged]);
  const record = async () => { if (await call("voice_cloud", { op: "record_sample", seconds: 30 })) setRec({ elapsed: 0, total: 30 }); };
  const create = async () => {
    setBusy(true);
    const ok = await call("voice_cloud", { op: "clone", id: p.id, consent });
    setBusy(false);
    if (ok) { notify("ok", `Sua voz foi criada para o ${p.name}.`); setConsent(false); onChanged(); }
  };
  return (
    <div className="field">
      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>Eu consinto em gravar a minha voz e enviá-la ao serviço de voz para criar uma voz só para este personagem. Só a minha voz, nunca a de outra pessoa.</span>
      </label>
      <p className="muted small">Leia em voz alta, num lugar silencioso, por cerca de 30 segundos: “{READ_TEXT}”</p>
      <div className="actions">
        <Button disabled={disabled || !consent || rec !== null} onClick={() => void record()}>{rec ? "Gravando…" : status?.has_sample ? "Gravar de novo" : "Gravar 30 s"}</Button>
        <Button variant="primary" disabled={disabled || !consent || !status?.has_sample || busy} onClick={() => void create()}>{busy ? "Criando…" : "Criar minha voz"}</Button>
      </div>
      {rec && <progress max={rec.total} value={rec.elapsed} aria-label="Progresso da gravação">{rec.elapsed}s</progress>}
      {status?.has_sample && !rec && <p className="muted small">Gravação pronta. Ela fica só na memória e é apagada depois de enviada.</p>}
      {disabled && <p className="muted small">Defina a chave de API acima para continuar.</p>}
    </div>
  );
}

function EngineCard({ title, text, tag, on, cloud, onPick }: { title: string; text: string; tag: string; on?: boolean; cloud?: boolean; onPick?: () => void }) {
  return (
    <button type="button" role="radio" aria-checked={!!on} className={`engine${on ? " on" : ""}`} onClick={onPick}>
      <strong>{title}</strong><span className="muted small">{text}</span><Badge tone={cloud ? "neutral" : "ok"}>{tag}</Badge>
    </button>
  );
}

export type { ReactNode };
