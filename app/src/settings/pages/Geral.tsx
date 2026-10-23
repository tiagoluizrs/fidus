import { useEffect, useState } from "react";
import { useCore } from "../core";
import { humanize, comboFromEvent } from "../hotkey";
import { Badge, Button, Page, Row, Section, Segmented, Switch, TextField } from "../ui";

export function HotkeyField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [capturing, setCapturing] = useState(false);
  useEffect(() => {
    if (!capturing) return;
    const down = (e: KeyboardEvent) => {
      e.preventDefault();
      if (e.key === "Escape") return setCapturing(false);
      const combo = comboFromEvent(e);
      if (combo) {
        setCapturing(false);
        onChange(combo);
      }
    };
    window.addEventListener("keydown", down);
    return () => window.removeEventListener("keydown", down);
  }, [capturing, onChange]);
  return (
    <div className="hotkey">
      <kbd aria-label={`Atalho atual: ${humanize(value)}`}>{capturing ? "Aperte o novo atalho…" : humanize(value)}</kbd>
      <Button onClick={() => setCapturing((c) => !c)}>{capturing ? "Cancelar" : "Alterar"}</Button>
    </div>
  );
}

export function Geral() {
  const { eff, save, characters, calls, setCalls, restartNeeded } = useCore();
  const s = (k: string) => eff[k] as never;
  return (
    <Page title="Geral" subtitle="Tema, idioma e como o Fidus abre e é chamado.">
      <Section title="Aparência" subtitle="O padrão acompanha o tema do seu sistema.">
        <Row label="Tema">
          <Segmented label="Tema" value={s("app.tema") ?? "sistema"} onChange={(v) => save({ "app.tema": v })}
            options={[{ value: "sistema", label: "Sistema" }, { value: "claro", label: "Claro" }, { value: "escuro", label: "Escuro" }]} />
        </Row>
        <Row label="Idioma" hint="Outros idiomas chegam em uma próxima versão.">
          <select aria-label="Idioma" value="pt-BR" disabled><option>Português (Brasil)</option></select>
        </Row>
      </Section>

      <Section title="Chamar um personagem" subtitle="Cada um atende pelo próprio nome.">
        <Row label="Escutar chamados" hint="Escuta local: nada é enviado antes de você chamar.">
          <Switch label="Escutar chamados" checked={calls.enabled} onChange={(v) => void setCalls(v)} />
        </Row>
        <div className="chips-row" aria-label="Chamados">
          {characters.map((c) => <span key={c.id} className="chip">{c.call}{c.is_default && <Badge tone="ok">Padrão</Badge>}</span>)}
        </div>
        <Row label="Atalho de teclado" hint="Chama o personagem padrão: segure para falar, solte para enviar.">
          <HotkeyField value={s("voz.atalho") ?? "ctrl+alt+space"} onChange={(v) => save({ "voz.atalho": v })} />
        </Row>
        {restartNeeded.includes("voz.atalho") && <p className="notice">O novo atalho vale depois de reiniciar o Fidus.</p>}
      </Section>

      <Section title="Sistema" subtitle="Como o Fidus convive com o seu computador.">
        <Row label="Iniciar junto com o sistema">
          <Switch label="Iniciar junto com o sistema" checked={s("app.iniciar_com_windows") === true} onChange={(v) => save({ "app.iniciar_com_windows": v })} />
        </Row>
        <Row label="Mostrar o ícone na bandeja" hint="Sem o ícone, abra o Fidus de novo pelo menu Iniciar para voltar aqui.">
          <Switch label="Mostrar o ícone na bandeja" checked={s("app.icone_bandeja") !== false} onChange={(v) => save({ "app.icone_bandeja": v })} />
        </Row>
        <Row label="Fechar janelas mantém o Fidus rodando" hint="Sempre assim: para encerrar, use Sair do Fidus na bandeja.">
          <Switch label="Fechar janelas mantém o Fidus rodando" checked disabled onChange={() => {}} />
        </Row>
        <Row label="Tocar um som ao ser chamado">
          <Switch label="Tocar um som ao ser chamado" checked={s("chamados.som_ao_ouvir") === true} onChange={(v) => save({ "chamados.som_ao_ouvir": v })} />
        </Row>
        <Row label="Fechar o anel depois de" hint="Tempo parado até a janela do anel sumir.">
          <Segmented label="Fechar o anel depois de" value={s("app.janela_inatividade_s") ?? 6}
            onChange={(v) => save({ "app.janela_inatividade_s": v })}
            options={[{ value: 3, label: "3 s" }, { value: 6, label: "6 s" }, { value: 15, label: "15 s" }, { value: 30, label: "30 s" }]} />
        </Row>
      </Section>

      <Section title="Você" subtitle="Usado nas falas dos personagens (ex.: “Pois não, senhor Lima”).">
        <NameFields />
      </Section>
    </Page>
  );
}

function NameFields() {
  const { eff, save } = useCore();
  return (
    <div className="two-cols">
      <NameField label="Nome" value={String(eff["usuario.nome"] ?? "")} onCommit={(v) => save({ "usuario.nome": v })} />
      <NameField label="Sobrenome" value={String(eff["usuario.sobrenome"] ?? "")} onCommit={(v) => save({ "usuario.sobrenome": v })} />
      <div className="field gender">
        <span className="row-label" id="gender-label">Como você prefere ser tratado</span>
        <Segmented label="Como você prefere ser tratado" value={String(eff["usuario.genero"] ?? "")} onChange={(v) => save({ "usuario.genero": v })}
          options={[{ value: "homem", label: "Homem" }, { value: "mulher", label: "Mulher" }, { value: "neutro", label: "Prefiro não informar" }]} />
        <span className="muted small">{eff["usuario.genero"] ? "Define “senhor” ou “senhora” nas falas; você pode editá-las em Personagem." : "Escolha para o Fidus usar o tratamento certo. Sem escolha, ele mantém o padrão do personagem."}</span>
      </div>
    </div>
  );
}
const NameField = (p: { label: string; value: string; onCommit: (v: string) => void }) => <TextField {...p} maxLength={60} />;
