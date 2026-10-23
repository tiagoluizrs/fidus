import { useEffect, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, Dialog, Page, Row, Section, Switch } from "../ui";

export function ModeloIA() {
  const { eff, save, call, claudeModels, notify } = useCore();
  const [key, setKey] = useState<{ stored: boolean; source: string } | null>(null);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  useEffect(() => void call<{ stored: boolean; source: string }>("api_key", {}, { quiet: true }).then(setKey), [call]);
  const model = String(eff["modelo.claude"] ?? "claude-sonnet-5-5");
  const known = claudeModels.includes(model);

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
          <button type="button" role="radio" aria-checked className="engine on"><strong>Claude</strong><span className="muted small">Anthropic · Padrão. Melhor para pedidos com várias etapas e ferramentas.</span><Badge>Nuvem</Badge></button>
          <button type="button" role="radio" aria-checked={false} className="engine" disabled><strong>Local</strong><span className="muted small">Ollama · Nada sai da máquina. Mais limitado; indicado para comandos simples.</span><Badge tone="soon">Em breve</Badge></button>
        </div>
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
      </Section>

      <Section title="Para onde vão seus dados" subtitle="Só o necessário para responder sai do computador.">
        <Row label="Sua voz e a transcrição"><Badge tone="ok">Neste computador</Badge></Row>
        <Row label="Memória e histórico"><Badge tone="ok">Neste computador</Badge></Row>
        <Row label="Chaves e tokens das contas"><Badge tone="ok">Cofre do sistema</Badge></Row>
        <Row label="Seu pedido e trechos necessários"><Badge>Claude · Nuvem</Badge></Row>
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
