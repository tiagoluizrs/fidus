import { useEffect, useRef, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, Page, Row, Section, Segmented, Slider, Switch } from "../ui";

interface Device {
  index: number;
  name: string;
  default: boolean;
}

/** Medidor do nível do microfone: o núcleo manda o nível (~37/s) enquanto esta janela está aberta. */
function Meter() {
  const { subscribe } = useCore();
  const bar = useRef<HTMLDivElement>(null);
  const [testing, setTesting] = useState(false);
  const peak = useRef(0);
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== "level" || !bar.current) return;
        const v = Math.max(...e.values, 0);
        peak.current = Math.max(v, peak.current * 0.97);
        bar.current.style.width = `${Math.round(peak.current * 100)}%`;
      }),
    [subscribe],
  );
  useEffect(() => {
    if (!testing) return;
    const t = setTimeout(() => setTesting(false), 6000);
    return () => clearTimeout(t);
  }, [testing]);
  return (
    <div className="meter-row">
      <div className="meter" role="meter" aria-label="Nível de entrada" aria-valuemin={0} aria-valuemax={100}><div ref={bar} className="meter-bar" /></div>
      <Button onClick={() => setTesting(true)} aria-pressed={testing}>{testing ? "Fale agora…" : "Testar"}</Button>
    </div>
  );
}

export function Voz() {
  const { eff, save, call, characters, calls, setCalls, restartNeeded, notify } = useCore();
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(() => {
    void call<{ devices: Device[] }>("devices", {}, { quiet: true }).then((d) => d && setDevices(d.devices));
  }, [call]);
  const s = (k: string) => eff[k] as never;
  const rate = Number(s("voz.velocidade_voz") ?? 0);
  const defaultId = characters.find((c) => c.is_default)?.id ?? "alfred";
  const mic = String(s("voz.microfone") ?? "");

  return (
    <Page title="Voz" subtitle="Palavra de ativação, microfone e resposta falada.">
      <Section title="Chamados" subtitle="Como os personagens percebem que você os chamou.">
        <Row label="Escutar chamados">
          <Switch label="Escutar chamados" checked={calls.enabled} onChange={(v) => void setCalls(v)} />
        </Row>
        <div className="chips-row">{characters.map((c) => <span key={c.id} className="chip">{c.call}</span>)}</div>
        <Row label="Como perceber o chamado" hint="Por fala: o Fidus ouve, entende com o Whisper no seu computador e só age se a frase começar com o nome (“ei Alfred…”). Não precisa treinar nada, mas usa mais processador. Por modelo: usa as palavras de ativação treinadas (docs/WAKEWORDS.md), mais leve. Automático usa os modelos se existirem e, senão, a fala.">
          <Segmented label="Como perceber o chamado" value={String(s("chamados.modo") ?? "auto")} onChange={(v) => save({ "chamados.modo": v })}
            options={[{ value: "auto", label: "Automático" }, { value: "voz", label: "Por fala" }, { value: "modelo", label: "Por modelo" }]} />
        </Row>
        {restartNeeded.includes("chamados.modo") && <p className="notice">A nova forma de perceber o chamado vale depois de reiniciar o Fidus.</p>}
        <Slider label="Sensibilidade" value={Number(s("chamados.sensibilidade") ?? 60)} left="Menos falsos alarmes" right="Acorda mais fácil"
          onChange={(v) => save({ "chamados.sensibilidade": v })} />
        <Row label="Aceitar também o atalho (segurar e falar)">
          <Switch label="Aceitar também o atalho" checked={s("voz.atalho_ativo") !== false} onChange={(v) => save({ "voz.atalho_ativo": v })} />
        </Row>
      </Section>

      <Section title="Microfone" subtitle="Escolha e teste o que ele ouve.">
        <Row label="Entrada" htmlFor="mic-select" hint={devices.length ? undefined : "A lista de microfones aparece com o núcleo real em execução."}>
          <select id="mic-select" value={mic} onChange={(e) => save({ "voz.microfone": e.target.value })}>
            <option value="">Padrão do sistema</option>
            {devices.map((d) => <option key={d.index} value={String(d.index)}>{d.name}{d.default ? " (padrão)" : ""}</option>)}
          </select>
        </Row>
        {restartNeeded.includes("voz.microfone") && <p className="notice">O novo microfone vale depois de reiniciar o Fidus.</p>}
        <Row label="Nível de entrada"><Meter /></Row>
        <Row label="Encerrar depois de" hint="Quanto esperar você começar a falar depois do chamado.">
          <Segmented label="Encerrar depois de" value={Math.round(Number(s("chamados.esperar_fala_s") ?? 5))}
            onChange={(v) => save({ "chamados.esperar_fala_s": v })}
            options={[{ value: 3, label: "3 s" }, { value: 5, label: "5 s" }, { value: 8, label: "8 s" }]} />
        </Row>
      </Section>

      <Section title="Resposta falada" subtitle="A voz do personagem ativo.">
        <Row label="Responder em voz alta">
          <Switch label="Responder em voz alta" checked={s("voz.responder_em_voz") !== false} onChange={(v) => save({ "voz.responder_em_voz": v })} />
        </Row>
        <Row label="Voz" hint="Cada personagem tem a própria voz: ajuste em Personagem > Voz.">
          <Badge>Do personagem padrão</Badge>
        </Row>
        <Slider label="Velocidade" value={Math.round((rate + 10) * 5)} left="Mais devagar" right="Mais rápido" format={(v) => `${Math.round(v / 5) - 10}`}
          onChange={(v) => save({ "voz.velocidade_voz": Math.round(v / 5) - 10 })} />
        <div className="actions">
          <Button onClick={async () => {
            const r = await call<{ spoken: boolean; reason?: string }>("characters", { op: "preview", id: defaultId });
            if (r && !r.spoken) notify("info", r.reason ?? "Sem voz disponível.");
          }}>Ouvir amostra</Button>
        </div>
      </Section>

      <Section title="Transcrição" subtitle="Como a sua fala vira texto.">
        <Row label="Onde acontece"><Badge tone="ok">Neste computador</Badge></Row>
        <Row label="Modelo" htmlFor="whisper" hint="Modelos maiores entendem melhor, mas pedem mais memória e demoram mais.">
          <select id="whisper" value={String(s("voz.modelo_whisper") ?? "small")} onChange={(e) => save({ "voz.modelo_whisper": e.target.value })}>
            <option value="base">Básico (mais leve)</option>
            <option value="small">Pequeno (rápido)</option>
            <option value="medium">Médio (mais preciso)</option>
          </select>
        </Row>
        {restartNeeded.includes("voz.modelo_whisper") && <p className="notice">O novo modelo vale depois de reiniciar o Fidus. Na primeira vez ele é baixado.</p>}
        <Row label="Idioma da fala"><select aria-label="Idioma da fala" disabled value="pt-BR"><option>Português (Brasil)</option></select></Row>
      </Section>
    </Page>
  );
}
