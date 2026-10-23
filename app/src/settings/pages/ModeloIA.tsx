import { useCallback, useEffect, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, Dialog, Page, Row, Section, Switch } from "../ui";

/** Modelos de até 3 bilhões de parâmetros (1b, 3b, 0.5b...) erram demais com ferramentas. */
export const isSmallModel = (name: string): boolean => /(^|[:\-_ ])(0\.\d+|1|1\.5|2|3)b(\b|$)/i.test(name);

interface LocalModels { running: boolean; models: string[]; suggested: string; url: string; busy?: boolean }

export function ModeloIA() {
  const { eff, save, call, claudeModels, notify, subscribe } = useCore();
  const [pullName, setPullName] = useState("");
  const [pull, setPull] = useState<{ what: string; pct: number } | null>(null);
  const [key, setKey] = useState<{ stored: boolean; source: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  useEffect(() => void call<{ stored: boolean; source: string }>("api_key", {}, { quiet: true }).then(setKey), [call]);
  const model = String(eff["modelo.claude"] ?? "claude-sonnet-5-5");
  const known = claudeModels.includes(model);
  const local = eff["modelo.provedor"] === "local";
  const localModel = String(eff["modelo.local"] ?? "qwen3:8b");
  const ack = eff["modelo.local_acoes_ciente"] === true;
  const [ollama, setOllama] = useState<LocalModels | null>(null);
  const refresh = useCallback(async () => setOllama(await call<LocalModels>("local_models", {}, { quiet: true })), [call]);
  useEffect(() => { if (local) void refresh(); }, [local, refresh]);
  const installed = ollama?.models ?? [];
  useEffect(() => subscribe((e) => {
    if (e.type !== "model_pull") return;
    if (e.state === "progress") return setPull({ what: e.what, pct: e.total ? Math.round(((e.done ?? 0) / e.total) * 100) : 0 });
    setPull(null);
    if (e.state === "error") return notify("error", e.message ?? "Não consegui baixar o modelo.");
    notify("ok", `Modelo ${e.what} baixado.`);
    void save({ "modelo.local": e.what }); // já deixa selecionado
    void refresh();
  }), [subscribe, notify, save, refresh]);
  const startPull = async () => {
    const name = pullName.trim();
    if (name && (await call("local_models", { op: "pull", model: name }))) setPull({ what: name, pct: 0 });
  };

  const submit = async () => {
    const r = await call<{ stored: boolean; source: string }>("api_key", { op: "set", value });
    setValue("");
    if (r) {
      setKey(r);
      setEditing(false);
      notify("ok", "Chave guardada no cofre do sistema.");
    }
  };

  return (
    <Page title="Modelo de IA" subtitle="Escolha quem pensa por trás do personagem e veja para onde cada dado vai.">
      <Section title="Provedor" subtitle="Troque quando quiser; a memória e o personagem continuam os mesmos.">
        <div className="engines" role="radiogroup" aria-label="Provedor">
          <button type="button" role="radio" aria-checked={!local} className={`engine${local ? "" : " on"}`} onClick={() => void save({ "modelo.provedor": "claude" })}>
            <strong>Claude</strong><span className="muted small">Anthropic · Padrão. Melhor para pedidos com várias etapas e ferramentas.</span><Badge>Nuvem</Badge>
          </button>
          <button type="button" role="radio" aria-checked={local} className={`engine${local ? " on" : ""}`} onClick={() => void save({ "modelo.provedor": "local" })}>
            <strong>Local</strong><span className="muted small">Ollama · Nada sai da máquina. Mais limitado: por padrão só lê e responde.</span><Badge tone="ok">Neste computador</Badge>
          </button>
        </div>
        {!local && (
          <>
            <Row label="Modelo" htmlFor="model" hint="Teste o claude-haiku-5-5 nos pedidos simples: costuma ser mais rápido e barato.">
              <select id="model" value={model} onChange={(e) => save({ "modelo.claude": e.target.value })}>
                {!known && <option value={model}>{model}</option>}
                {claudeModels.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </Row>
            <Row label="Chave da API" hint={key?.source === "ambiente" ? "Vem do arquivo .env (só desenvolvimento). Guarde no cofre." : undefined}>
              <span className="inline">
                <Badge tone={key?.stored ? "ok" : "neutral"}>{key?.stored ? "Guardada no cofre do sistema" : key?.source === "ambiente" ? "No ambiente (.env)" : "Não definida"}</Badge>
                <Button onClick={() => setEditing(true)}>{key?.stored ? "Alterar" : "Definir"}</Button>
              </span>
            </Row>
          </>
        )}
        {local && (
          <Row label="Modelo local" htmlFor="local-model"
            hint={ollama?.running === false ? "O Ollama não está acessível. Abra o app dele e clique em Atualizar." : installed.length ? "Escolha um modelo que suporte ferramentas, de 7B para cima (llama3.1, qwen3, qwen2.5)." : "Nenhum modelo baixado ainda: baixe um abaixo."}>
            <span className="inline">
              <Badge tone={ollama?.running ? "ok" : "neutral"}>{ollama == null ? "Verificando…" : ollama.running ? "Ollama aberto" : "Ollama fechado"}</Badge>
              <select id="local-model" value={localModel} onChange={(e) => save({ "modelo.local": e.target.value })}>
                {!installed.includes(localModel) && <option value={localModel}>{localModel}{ollama?.running ? " (não baixado)" : ""}</option>}
                {installed.map((m) => <option key={m} value={m}>{m}{isSmallModel(m) ? " (fraco)" : ""}</option>)}
              </select>
              <Button onClick={() => void refresh()}>Atualizar</Button>
            </span>
          </Row>
        )}
        {local && isSmallModel(localModel) && (
          <p className="notice" role="note">O modelo <strong>{localModel}</strong> é pequeno e costuma responder mal e errar as ferramentas. Para o Fidus funcionar bem, use um de 7B ou 8B (por exemplo llama3.1:8b).</p>
        )}
        {local && ollama?.running && (
          <Row label="Baixar um modelo" htmlFor="pull-name" hint="Baixa pelo próprio Ollama, uma vez. Só vale a pena de 7B para cima (cerca de 5 GB e 8 GB de memória livre): os menores erram demais ao usar ferramentas.">
            <span className="inline">
              <input id="pull-name" list="pull-suggestions" value={pullName} placeholder="llama3.1:8b" onChange={(e) => setPullName(e.target.value)} />
              <datalist id="pull-suggestions">
                <option value="llama3.1:8b">Llama 3.1 · 8B (~4,7 GB)</option>
                <option value="qwen3:8b">Qwen 3 · 8B (~5,2 GB)</option>
                <option value="qwen2.5:7b">Qwen 2.5 · 7B (~4,7 GB)</option>
              </datalist>
              <Button disabled={!pullName.trim() || pull !== null || ollama.busy} onClick={() => void startPull()}>{pull ? "Baixando…" : "Baixar"}</Button>
            </span>
          </Row>
        )}
        {local && pull && <progress max={100} value={pull.pct} aria-label={`Baixando ${pull.what}`}>{pull.pct}%</progress>}
      </Section>

      <Section title="Ações com o modelo local" subtitle="Vale quando o provedor é Local. Por padrão o modelo local só lê (agenda, e-mails, arquivos, memória); criar, editar, apagar e enviar ficam bloqueados.">
        <div className="risk" role="note">
          <strong>Riscos de liberar ações</strong>
          <ul>
            <li>Modelos locais pequenos erram mais ao escolher e preencher ferramentas: podem propor apagar ou enviar a coisa errada.</li>
            <li>São mais fáceis de enganar por instruções escondidas em e-mails, mensagens e arquivos.</li>
            <li>O Fidus continua pedindo a sua confirmação antes de qualquer ação, mas você precisa conferir o que está confirmando.</li>
          </ul>
        </div>
        <Row label="Entendo os riscos acima">
          <label className="check">
            <input type="checkbox" checked={ack} onChange={(e) => save({ "modelo.local_acoes_ciente": e.target.checked })} />
            <span>Li e estou de acordo</span>
          </label>
        </Row>
        <Row label="Permitir ações com o modelo local" hint={ack ? "Desligue a qualquer momento." : "Marque que entende os riscos para poder ligar."}>
          <Switch label="Permitir ações com o modelo local" checked={eff["modelo.local_acoes"] === true && ack} disabled={!ack} onChange={(v) => save({ "modelo.local_acoes": v })} />
        </Row>
      </Section>

      <Section title="Para onde vão seus dados" subtitle="Só o necessário para responder sai do computador.">
        <Row label="Sua voz e a transcrição"><Badge tone="ok">Neste computador</Badge></Row>
        <Row label="Memória e histórico"><Badge tone="ok">Neste computador</Badge></Row>
        <Row label="Chaves e tokens das contas"><Badge tone="ok">Cofre do sistema</Badge></Row>
        <Row label="Seu pedido e trechos necessários">{local ? <Badge tone="ok">Ollama · Neste computador</Badge> : <Badge>Claude · Nuvem</Badge>}</Row>
      </Section>

      <Section title="Segurança das ações" subtitle="Valem para todos os personagens.">
        <Row label="Confirmar antes de enviar, apagar ou mover" hint="Sempre ligado: é uma regra do Fidus, fora do modelo.">
          <Switch label="Confirmar antes de enviar, apagar ou mover" checked disabled onChange={() => {}} />
        </Row>
        <Row label="Tratar e-mails e mensagens como dados" hint="Instruções escondidas num e-mail nunca viram ordens. Sempre ligado.">
          <Switch label="Tratar e-mails e mensagens como dados" checked disabled onChange={() => {}} />
        </Row>
        <Row label="Guardar histórico neste computador">
          <Switch label="Guardar histórico neste computador" checked={eff["privacidade.guardar_historico"] !== false} onChange={(v) => save({ "privacidade.guardar_historico": v })} />
        </Row>
        <Row label="Avisar quando o microfone estiver ativo" hint="O indicador no terminal e na bandeja continua sempre visível.">
          <Switch label="Avisar quando o microfone estiver ativo" checked={eff["privacidade.avisar_microfone"] !== false} onChange={(v) => save({ "privacidade.avisar_microfone": v })} />
        </Row>
      </Section>

      {editing && (
        <Dialog title="Chave da API da Anthropic" onClose={() => { setEditing(false); setValue(""); }}>
          <p className="muted">A chave é guardada no Gerenciador de Credenciais do Windows e nunca é mostrada de novo.</p>
          <div className="field">
            <label htmlFor="api-key" className="row-label">Chave (começa com sk-ant-)</label>
            <input id="api-key" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
          </div>
          <div className="dialog-actions">
            <Button onClick={() => { setEditing(false); setValue(""); }}>Cancelar</Button>
            <Button variant="primary" disabled={value.trim().length < 10} onClick={() => void submit()}>Guardar</Button>
          </div>
        </Dialog>
      )}
    </Page>
  );
}
