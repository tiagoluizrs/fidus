import { useEffect, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, Dialog, Page, Row, Section, Switch } from "../ui";

interface About { version: string; python: string; platform: string; model: string; data_dir: string; whisper: string }

export function Sobre() {
  const { call, notify, restartNeeded, clearRestart } = useCore();
  const [info, setInfo] = useState<About | null>(null);
  const [licenses, setLicenses] = useState(false);
  useEffect(() => void call<About>("about", {}, { quiet: true }).then(setInfo), [call]);

  const copy = async () => {
    const d = await call<{ diagnostics: string }>("about", { op: "diagnostics" });
    if (d) {
      await window.fidus.copyText(d.diagnostics);
      notify("ok", "Informações copiadas. Não incluem conversas, memória nem chaves.");
    }
  };

  return (
    <Page title="Sobre" subtitle="Versão, atualizações e onde ficam os seus dados.">
      <div className="card about-hero">
        <svg width="84" height="84" viewBox="0 0 84 84" aria-hidden="true">
          <defs><linearGradient id="sobre-g" x1="42" y1="4" x2="42" y2="80" gradientUnits="userSpaceOnUse"><stop offset="0" stopColor="#FF6A3D" /><stop offset="0.35" stopColor="#FF5C9E" /><stop offset="0.7" stopColor="#B38CFF" /><stop offset="1" stopColor="#3D8BFF" /></linearGradient></defs>
          <circle cx="42" cy="42" r="34" fill="none" stroke="url(#sobre-g)" strokeWidth="3" />
          <circle cx="42" cy="42" r="24" fill="none" stroke="url(#sobre-g)" strokeWidth="1.4" opacity="0.5" />
        </svg>
        <div>
          <strong className="big">Fidus</strong>
          <p className="muted">Seu conselheiro de IA</p>
          <p className="muted small">Versão {info?.version ?? "…"}</p>
        </div>
        <div className="actions">
          <Button variant="primary" disabled title="Em breve">Verificar atualizações</Button>
          <Button onClick={() => setLicenses(true)}>Ver licenças</Button>
        </div>
      </div>

      <div className="three-cols">
        <Section title="Atualizações" subtitle="Mantenha o Fidus em dia.">
          <Row label="Atualizar automaticamente" hint="Chega junto com o instalador."><Switch label="Atualizar automaticamente" checked={false} disabled onChange={() => {}} /></Row>
          <Row label="Avisar quando houver novidades"><Badge tone="soon">Em breve</Badge></Row>
        </Section>
        <Section title="Dados locais" subtitle="Onde ficam a memória, o histórico e o log.">
          <code className="path">{info?.data_dir ?? "…"}</code>
          <div className="actions"><Button onClick={() => void window.fidus.openPath("data")}>Abrir pasta</Button></div>
        </Section>
        <Section title="Diagnóstico" subtitle="Para pedir ajuda quando algo não funciona.">
          <p className="muted small">As informações copiadas não incluem suas conversas, a memória nem suas chaves.</p>
          <div className="actions"><Button onClick={() => void copy()}>Copiar informações</Button></div>
        </Section>
      </div>

      {restartNeeded.length > 0 && (
        <Section title="Reiniciar o núcleo" subtitle="Algumas mudanças só valem depois de reiniciar.">
          <div className="actions">
            <Button variant="primary" onClick={async () => { await window.fidus.restartCore(); clearRestart(); notify("info", "Reiniciando o Fidus…"); }}>Reiniciar agora</Button>
          </div>
        </Section>
      )}

      {licenses && (
        <Dialog title="Licenças" onClose={() => setLicenses(false)}>
          <p className="muted small">O Fidus usa software livre. Principais componentes: faster-whisper e Whisper (MIT), openWakeWord (Apache 2.0; modelos prontos CC BY-NC-SA 4.0, só uso não comercial), Silero VAD (MIT), Electron e React (MIT), Chromium (BSD e outras), SQLCipher (BSD). A lista completa acompanha o instalador.</p>
          <div className="dialog-actions"><Button variant="primary" onClick={() => setLicenses(false)}>Fechar</Button></div>
        </Dialog>
      )}
    </Page>
  );
}
