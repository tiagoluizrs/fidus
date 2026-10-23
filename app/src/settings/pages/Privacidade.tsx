import { useCallback, useEffect, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, ConfirmDialog, Dialog, Page, Row, Section, Segmented, Switch } from "../ui";

interface LogEntry { ts: string; tool: string; risk: string; decision: string; args: Record<string, unknown>; result: string }
interface Priv { folders: string[]; log_actions: boolean; log_days: number; keep_history: boolean; data_dir: string }

const DECISION: Record<string, string> = {
  permitido: "Permitido", confirmado: "Você confirmou", negado: "Você negou", erro: "Erro", bloqueado: "Barrado", bloqueado_limite: "Limite de chamadas",
  ferramenta_desconhecida: "Ferramenta desconhecida",
};
const MIC: Record<string, string> = { granted: "Permitido", denied: "Bloqueado", restricted: "Restrito", "not-determined": "Ainda não pedido", unknown: "Não sei verificar" };

export function Privacidade() {
  const { eff, save, call, notify } = useCore();
  const [priv, setPriv] = useState<Priv | null>(null);
  const [mic, setMic] = useState("unknown");
  const [log, setLog] = useState<LogEntry[] | null>(null);
  const [confirm, setConfirm] = useState<null | "history" | "all" | "log">(null);

  const load = useCallback(async () => {
    const d = await call<Priv>("privacy", { op: "get" }, { quiet: true });
    if (d) setPriv(d);
  }, [call]);
  useEffect(() => { void load(); void window.fidus.micStatus().then(setMic); }, [load]);

  const folders = (eff["arquivos.pastas_liberadas"] as string[] | undefined) ?? priv?.folders ?? [];
  const addFolder = async () => {
    const p = await window.fidus.pickFolder();
    if (p && !folders.includes(p)) await save({ "arquivos.pastas_liberadas": [...folders, p] });
  };
  const exportData = async () => {
    const path = await window.fidus.pickSavePath("meus-dados-fidus.zip", "zip");
    if (!path) return;
    const r = await call<{ path: string; files: string[] }>("privacy", { op: "export", path });
    if (r) notify("ok", `Exportado em ${r.path}. Chaves e tokens não vão no arquivo.`);
  };
  const run = async (op: string, okText: string) => {
    const r = await call("privacy", { op, confirm: true });
    setConfirm(null);
    if (r) notify("ok", okText);
    void load();
  };

  return (
    <Page title="Privacidade" subtitle="Permissões, pastas liberadas e o que fica registrado.">
      <Section title="Permissões do sistema" subtitle="O que o computador já liberou para o Fidus.">
        <Row label="Microfone"><Badge tone={mic === "granted" ? "ok" : "neutral"}>{MIC[mic] ?? mic}</Badge></Row>
        <div className="actions"><Button onClick={() => void window.fidus.openMicSettings()}>Abrir ajustes do sistema</Button></div>
      </Section>

      <Section title="Pastas que ele pode acessar" subtitle="Fora delas, o Fidus não lê nem altera arquivos.">
        <ul className="folders">
          {folders.map((f) => (
            <li key={f}><span>{f}</span><Button aria-label={`Remover a pasta ${f}`} onClick={() => save({ "arquivos.pastas_liberadas": folders.filter((x) => x !== f) })}>Remover</Button></li>
          ))}
          {!folders.length && <li className="muted small">Nenhuma pasta liberada: a busca de arquivos fica desligada.</li>}
        </ul>
        <div className="actions"><Button onClick={() => void addFolder()}>+ Adicionar pasta</Button></div>
      </Section>

      <Section title="Log de ações" subtitle="Um registro local de tudo que ele executa.">
        <Row label="Registrar o que o Fidus executa">
          <Switch label="Registrar o que o Fidus executa" checked={eff["privacidade.registrar_acoes"] !== false} onChange={(v) => save({ "privacidade.registrar_acoes": v })} />
        </Row>
        <Row label="Guardar por">
          <Segmented label="Guardar o log por" value={Number(eff["privacidade.guardar_log_dias"] ?? 30)} onChange={(v) => save({ "privacidade.guardar_log_dias": v })}
            options={[{ value: 7, label: "7 dias" }, { value: 30, label: "30 dias" }, { value: 90, label: "90 dias" }, { value: 365, label: "1 ano" }]} />
        </Row>
        <div className="actions">
          <Button onClick={async () => { const r = await call<{ entries: LogEntry[] }>("privacy", { op: "log", limit: 100 }); if (r) setLog(r.entries); }}>Abrir log de ações</Button>
          <Button onClick={() => void window.fidus.openPath("log")}>Mostrar o arquivo</Button>
          <Button onClick={() => setConfirm("log")}>Apagar o log</Button>
        </div>
      </Section>

      <Section title="Seus dados" subtitle="Tudo fica neste computador. Ações sem volta pedem confirmação.">
        <Row label="Exportar meus dados" hint="Memória, personagens, configurações, log e histórico. Sem chaves nem tokens."><Button onClick={() => void exportData()}>Exportar</Button></Row>
        <Row label="Pasta de dados" hint={priv?.data_dir}><Button onClick={() => void window.fidus.openPath("data")}>Abrir pasta</Button></Row>
        <Row label="Apagar histórico de conversas"><Button variant="danger" onClick={() => setConfirm("history")}>Apagar</Button></Row>
        <Row label="Apagar tudo: memória, histórico e chaves"><Button variant="danger" onClick={() => setConfirm("all")}>Apagar tudo</Button></Row>
      </Section>

      {log && (
        <Dialog title="Log de ações" onClose={() => setLog(null)}>
          <div className="log" role="region" aria-label="Últimas ações" tabIndex={0}>
            <table>
              <thead><tr><th>Quando</th><th>Ferramenta</th><th>Risco</th><th>Resultado</th></tr></thead>
              <tbody>
                {log.map((e, i) => (
                  <tr key={i}><td>{new Date(e.ts).toLocaleString("pt-BR")}</td><td>{e.tool}</td><td>{e.risk}</td><td>{DECISION[e.decision] ?? e.decision}</td></tr>
                ))}
                {!log.length && <tr><td colSpan={4} className="muted">Nada registrado ainda.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="dialog-actions"><Button variant="primary" onClick={() => setLog(null)}>Fechar</Button></div>
        </Dialog>
      )}
      {confirm === "history" && <ConfirmDialog danger title="Apagar o histórico de conversas?" text="As conversas guardadas neste computador serão apagadas. A memória (lembranças) não muda. Não dá para desfazer." confirmLabel="Apagar histórico" onCancel={() => setConfirm(null)} onConfirm={() => void run("clear_history", "Histórico apagado.")} />}
      {confirm === "log" && <ConfirmDialog danger title="Apagar o log de ações?" text="O registro do que o Fidus executou será apagado. Não dá para desfazer." confirmLabel="Apagar log" onCancel={() => setConfirm(null)} onConfirm={() => void run("clear_log", "Log apagado.")} />}
      {confirm === "all" && <ConfirmDialog danger requireWord="APAGAR" title="Apagar tudo?" text="Memória, histórico, edições dos personagens, cache de voz, log e todas as chaves e tokens (inclusive a chave da API e as contas conectadas) serão apagados deste computador. Você terá de configurar tudo de novo. Não dá para desfazer." confirmLabel="Apagar tudo" onCancel={() => setConfirm(null)} onConfirm={() => void run("clear_all", "Tudo apagado. Defina a chave da API de novo em Modelo de IA.")} />}
    </Page>
  );
}
