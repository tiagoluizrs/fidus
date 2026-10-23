import { useCallback, useEffect, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, Dialog, Page, Row, Section, Switch } from "../ui";

interface Service {
  id: string; kind: "email" | "chat" | "calendar"; name: string; coming_soon?: boolean; connected?: boolean;
  write?: boolean; write_label?: string; channels?: string[];
}
interface Status { google_credentials: boolean; services: Service[] }

const GROUPS: { kind: Service["kind"]; title: string; subtitle: string }[] = [
  { kind: "email", title: "E-mail", subtitle: "Ler, buscar e preparar rascunhos." },
  { kind: "chat", title: "Chat", subtitle: "Ler e responder mensagens." },
  { kind: "calendar", title: "Agenda", subtitle: "Consultar e organizar eventos." },
];
const ABOUT: Record<string, string> = {
  gmail: "Pode ler, buscar e criar rascunhos (nunca envia sozinho).",
  slack: "Pode ler os canais que você permitir e responder, com a sua confirmação antes de enviar.",
  agenda: "Pode ler eventos e criar ou alterar, com a sua confirmação.",
};

export function Contas() {
  const { call, subscribe, notify } = useCore();
  const [st, setSt] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [perm, setPerm] = useState<Service | null>(null);
  const [slack, setSlack] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);

  const load = useCallback(async () => {
    const d = await call<Status>("accounts", { op: "list" }, { quiet: true });
    if (d) setSt(d);
  }, [call]);
  useEffect(() => void load(), [load]);
  useEffect(() => subscribe((e) => {
    if (e.type === "open_url") {
      if (e.url.startsWith("https://accounts.google.com/")) setAuthUrl(e.url); // só o endereço de login do Google vira link
      return;
    }
    if (e.type !== "accounts") return;
    setBusy(null);
    setAuthUrl(null);
    if (e.status === "error") notify("error", e.message || "Não consegui conectar.");
    else notify("ok", e.status === "connected" ? "Conta conectada." : "Conta desconectada.");
    void load();
  }), [subscribe, load, notify]);

  const connect = async (s: Service, write = false) => {
    if (s.id === "slack") return setSlack(true);
    setBusy(s.id);
    const r = await call("accounts", { op: "connect", service: s.id, write });
    if (!r) setBusy(null);
    else notify("info", "Autorize no navegador (ou no link que vai aparecer aqui).");
  };

  const sendCredentials = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 20000) return notify("error", "Esse arquivo é grande demais para ser o credentials.json.");
    const r = await call<Status>("accounts", { op: "google_credentials", json: await file.text() });
    if (r) { setSt(r); notify("ok", "Credenciais do Google guardadas."); }
  };

  return (
    <Page title="Contas" subtitle="Conecte os serviços que o Fidus pode usar. Os personagens compartilham as mesmas contas.">
      {st && (
        <Section title="Credenciais do Google" subtitle="Necessárias para Gmail e Agenda. É o arquivo que o Google Cloud deixa baixar (tipo “App para computador”).">
          <Row label="credentials.json" hint={st.google_credentials ? "Guardado na pasta de dados do Fidus." : "Passo a passo em docs/INTEGRACOES.md (passo 1)."}>
            <span className="inline">
              <Badge tone={st.google_credentials ? "ok" : "neutral"}>{st.google_credentials ? "Enviado" : "Falta enviar"}</Badge>
              <label className="btn secondary file-btn">
                {st.google_credentials ? "Trocar arquivo" : "Enviar arquivo"}
                <input type="file" accept=".json,application/json" className="sr-only" aria-label="Enviar o credentials.json" onChange={(e) => { void sendCredentials(e.target.files?.[0]); e.target.value = ""; }} />
              </label>
              {st.google_credentials && <Button onClick={async () => { const r = await call<Status>("accounts", { op: "google_credentials_remove" }); if (r) setSt(r); }}>Remover</Button>}
            </span>
          </Row>
        </Section>
      )}
      {authUrl && (
        <p className="notice" role="note">Para autorizar o Google, <a href={authUrl} target="_blank" rel="noreferrer">abra a página de autorização</a>, entre na sua conta e volte aqui.</p>
      )}
      {GROUPS.map((g) => (
        <Section key={g.kind} title={g.title} subtitle={g.subtitle}>
          {st?.services.filter((s) => s.kind === g.kind).map((s) => (
            <div key={s.id} className="account" aria-label={s.name}>
              <div className="account-text">
                <strong>{s.name}</strong>
                {s.coming_soon ? (
                  <span className="muted small">Chega em uma próxima versão.</span>
                ) : (
                  <span className="muted small">{s.connected ? `Conectado · ${ABOUT[s.id]}` : s.id !== "slack" && !st?.google_credentials ? "Envie o credentials.json do Google (acima) para conectar." : "Não conectado."}</span>
                )}
              </div>
              <div className="account-actions">
                {s.coming_soon && <Badge tone="soon">Em breve</Badge>}
                {!s.coming_soon && s.connected && <Button onClick={() => setPerm(s)}>Permissões</Button>}
                {!s.coming_soon && s.connected && <Button onClick={async () => { await call("accounts", { op: "disconnect", service: s.id }); await load(); }}>Desconectar</Button>}
                {!s.coming_soon && !s.connected && <Button variant="primary" disabled={busy === s.id || (s.id !== "slack" && !st?.google_credentials)} title={s.id !== "slack" && !st?.google_credentials ? "Envie o credentials.json em “Credenciais do Google”, acima." : undefined} onClick={() => void connect(s)}>{busy === s.id ? "Aguardando…" : "Conectar"}</Button>}
              </div>
            </div>
          ))}
        </Section>
      ))}
      <p className="muted small">O Fidus pede só as permissões necessárias. Enviar, apagar ou mover algo sempre pede a sua confirmação, e as chaves ficam no cofre do sistema.</p>

      {perm && <PermissionsDialog s={perm} onClose={() => { setPerm(null); void load(); }} connect={connect} />}
      {slack && <SlackDialog onClose={() => { setSlack(false); void load(); }} />}
    </Page>
  );
}

function PermissionsDialog({ s, onClose, connect }: { s: Service; onClose: () => void; connect: (s: Service, write?: boolean) => Promise<void> }) {
  const { call } = useCore();
  const [channel, setChannel] = useState("");
  const [chans, setChans] = useState(s.channels ?? []);
  const [write, setWrite] = useState(!!s.write);
  const toggle = async (v: boolean) => {
    if (s.id === "slack") {
      // reconectar com a escrita liberada pede o token de novo; aqui só mostramos o estado atual
      setWrite(v);
      return;
    }
    setWrite(v);
    await connect(s, v); // o Google pede o consentimento de novo, com o escopo certo
  };
  const editChannel = async (op: "channel_add" | "channel_remove", name: string) => {
    const r = await call<Status>("accounts", { op, service: "slack", name });
    if (r) setChans(r.services.find((x) => x.id === "slack")?.channels ?? []);
    setChannel("");
  };
  return (
    <Dialog title={`Permissões: ${s.name}`} onClose={onClose}>
      <p className="muted">Leitura é o padrão. A escrita é liberada por serviço e sempre pede a sua confirmação antes de agir.</p>
      {s.id !== "slack" && (
        <Row label={`Permitir ${s.write_label}`} hint={s.id === "gmail" ? "O Google não oferece permissão só de rascunho: ela também permitiria enviar. O Fidus nunca envia." : "Ao mudar, o Google pede o consentimento de novo."}>
          <Switch label={`Permitir ${s.write_label}`} checked={write} onChange={(v) => void toggle(v)} />
        </Row>
      )}
      {s.id === "slack" && (
        <>
          <p className="muted small">Para liberar ou desligar respostas, reconecte o Slack marcando a opção na tela de conexão.</p>
          <h3 className="small">Canais que o Fidus pode ler</h3>
          <ul className="chan-list">
            {chans.map((c) => <li key={c}>{c} <Button aria-label={`Remover ${c}`} onClick={() => void editChannel("channel_remove", c)}>Remover</Button></li>)}
            {!chans.length && <li className="muted small">Nenhum canal permitido ainda.</li>}
          </ul>
          <form className="add-row" onSubmit={(e) => { e.preventDefault(); if (channel.trim()) void editChannel("channel_add", channel); }}>
            <label htmlFor="chan" className="sr-only">Nome do canal</label>
            <input id="chan" value={channel} onChange={(e) => setChannel(e.target.value)} placeholder="Nome do canal ou da pessoa" />
            <Button type="submit" disabled={!channel.trim()}>Adicionar</Button>
          </form>
        </>
      )}
      <div className="dialog-actions"><Button variant="primary" onClick={onClose}>Fechar</Button></div>
    </Dialog>
  );
}

function SlackDialog({ onClose }: { onClose: () => void }) {
  const { call, notify } = useCore();
  const [token, setToken] = useState("");
  const [write, setWrite] = useState(false);
  const [working, setWorking] = useState(false);
  const submit = async () => {
    setWorking(true);
    const r = await call("accounts", { op: "connect", service: "slack", token, write });
    setWorking(false);
    setToken("");
    if (r) {
      notify("ok", "Slack conectado. Escolha os canais em Permissões.");
      onClose();
    }
  };
  return (
    <Dialog title="Conectar o Slack" onClose={onClose}>
      <p className="muted">Cole o <strong>User OAuth Token</strong> (começa com <code>xoxp-</code>) do seu app do Slack. O passo a passo está em <code>docs/INTEGRACOES.md</code>.</p>
      <div className="field">
        <label htmlFor="slack-token" className="row-label">Token do Slack</label>
        <input id="slack-token" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
      </div>
      <Row label="Permitir responder mensagens" hint="As respostas saem como se fossem suas, e o Fidus sempre pergunta antes de enviar.">
        <Switch label="Permitir responder mensagens" checked={write} onChange={setWrite} />
      </Row>
      <div className="dialog-actions">
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="primary" disabled={token.trim().length < 10 || working} onClick={() => void submit()}>{working ? "Verificando…" : "Conectar"}</Button>
      </div>
    </Dialog>
  );
}
