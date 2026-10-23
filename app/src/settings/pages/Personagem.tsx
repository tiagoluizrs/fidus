import { useCallback, useEffect, useState } from "react";
import { useCore } from "../core";
import { VoiceTab } from "./VoiceTab";
import { Badge, Button, ConfirmDialog, Page, Section, Segmented, Slider, Switch, TextField } from "../ui";

interface Item { id: string; text: string; enabled: boolean; origin: "padrao" | "editada" | "usuario"; contexts: string[] }
interface ListData { items: Item[]; deleted: { id: string; text: string }[] }
export interface Profile {
  id: string; name: string; call: string; summary: string; ring: { dark: string[]; light: string[] };
  is_default: boolean; edited: boolean;
  personality: { base_style: string; default_style: string; controls: Record<string, { value: number; default: number }>; extra: string };
  address: { mode: "random" | "fixed" | "context"; fixed: string; items: Item[]; deleted: { id: string; text: string }[] };
  phrases: Record<string, ListData>;
  voice: { engine: string; voice: string; pitch: number; rate: number; description?: string; default: { engine: string; voice: string; pitch: number; rate: number } };
  variables: string[];
}

const STYLES = [
  { value: "padrao", label: "Padrão" }, { value: "mais_seco", label: "Mais seco" }, { value: "mais_engracado", label: "Mais engraçado" },
  { value: "mais_aspero", label: "Mais áspero" }, { value: "personalizado", label: "Personalizado" },
];
const CONTROLS: { key: string; label: string; left: string; right: string }[] = [
  { key: "formalidade", label: "Formalidade", left: "Casual", right: "Formal" },
  { key: "humor", label: "Humor", left: "Sério", right: "Engraçado" },
  { key: "aspereza", label: "Aspereza", left: "Gentil", right: "Áspero" },
  { key: "iniciativa", label: "Iniciativa", left: "Só se pedir", right: "Antecipa" },
  { key: "detalhe", label: "Detalhe", left: "Direto", right: "Detalhista" },
];
const MOMENTS = [
  { value: "inicio", label: "Início" }, { value: "concluir", label: "Concluir" }, { value: "confirmar", label: "Confirmar" },
  { value: "erro", label: "Erro" }, { value: "despedida", label: "Despedida" },
];
const TABS = ["Personalidade", "Frases", "Voz"] as const;

export function Personagem() {
  const { characters, call, reloadCharacters, subscribe } = useCore();
  const [selected, setSelected] = useState("alfred");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Personalidade");

  const load = useCallback(async (id: string) => {
    const p = await call<Profile>("characters", { op: "get", id }, { quiet: true });
    if (p) setProfile(p);
  }, [call]);
  useEffect(() => void load(selected), [selected, load]);
  useEffect(() => subscribe((e) => e.type === "characters_changed" && void load(selected)), [subscribe, load, selected]);

  /** Faz uma alteração no personagem; o núcleo devolve o perfil já atualizado. */
  const mutate = useCallback(async (op: string, args: Record<string, unknown> = {}) => {
    const p = await call<Profile>("characters", { op, id: selected, ...args });
    if (p) setProfile(p);
    return !!p;
  }, [call, selected]);

  const setDefault = async (id: string) => {
    if (await call("set_default_character", { id })) reloadCharacters();
  };

  return (
    <Page title="Personagem" subtitle="Cada um atende pelo próprio nome. O padrão responde ao atalho.">
      <div className="char-list" role="radiogroup" aria-label="Personagens">
        {characters.map((c) => (
          <button key={c.id} type="button" role="radio" aria-checked={c.id === selected} className={`char${c.id === selected ? " on" : ""}`} onClick={() => setSelected(c.id)}>
            <strong>{c.name}</strong>
            <span className="muted small">{c.call}</span>
            {c.is_default && <Badge tone="ok">Padrão</Badge>}
          </button>
        ))}
        <button type="button" className="char" disabled aria-label="Novo personagem (em breve)">
          <strong>Novo personagem</strong><Badge tone="soon">Em breve</Badge>
        </button>
      </div>
      <p className="muted small">Cada personagem tem personalidade, frases e voz próprias. A memória é a mesma para todos.</p>

      {profile && (
        <div className="char-detail" aria-live="polite">
          <header className="char-head">
            <span className="ring-dot" style={{ background: `linear-gradient(${profile.ring.dark.join(",")})` }} aria-hidden="true" />
            <h2>{profile.name}</h2>
            {profile.is_default ? <Badge tone="ok">Padrão</Badge> : <Button onClick={() => void setDefault(profile.id)}>Tornar padrão</Button>}
            <span className="muted">{profile.call}</span>
          </header>
          <div className="tabs" role="tablist" aria-label="Seções do personagem">
            {TABS.map((t) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
          {tab === "Personalidade" && <PersonalityTab p={profile} mutate={mutate} />}
          {tab === "Frases" && <PhrasesTab p={profile} mutate={mutate} />}
          {tab === "Voz" && <VoiceTab p={profile} mutate={mutate} />}
        </div>
      )}
    </Page>
  );
}

type Mutate = (op: string, args?: Record<string, unknown>) => Promise<boolean>;

function PersonalityTab({ p, mutate }: { p: Profile; mutate: Mutate }) {
  const [confirm, setConfirm] = useState(false);
  const changed = Object.values(p.personality.controls).filter((c) => c.value !== c.default).length + (p.personality.base_style !== p.personality.default_style ? 1 : 0) + (p.personality.extra ? 1 : 0);
  return (
    <>
      <Section title="Estilo base">
        <Segmented label="Estilo base" value={p.personality.base_style} options={STYLES} onChange={(v) => mutate("set_style", { style: v })} />
      </Section>
      <Section title="Jeito de falar" subtitle="Cada controle vira uma instrução para o personagem.">
        {CONTROLS.map((c) => {
          const v = p.personality.controls[c.key];
          return (
            <Slider key={c.key} label={c.label} value={v.value} left={c.left} right={c.right}
              onChange={(n) => n !== v.value && mutate("set_control", { control: c.key, value: n })}
              onRestore={v.value !== v.default ? () => mutate("reset_control", { control: c.key }) : undefined}
              restoreLabel={`Restaurar (${v.default})`} />
          );
        })}
        <TextField label="Instruções extras (opcional)" multiline maxLength={2000} value={p.personality.extra} placeholder="Ex.: prefira respostas curtas quando eu estiver dirigindo"
          onCommit={(t) => mutate("set_extra", { text: t })} />
        <p className="muted small">As instruções extras mudam só o jeito de falar. Elas nunca desligam confirmações nem as regras de segurança.</p>
      </Section>
      <footer className="tab-foot">
        <Button onClick={() => setConfirm(true)} disabled={!changed}>Restaurar personalidade padrão</Button>
        <span className="muted small">{changed ? `${changed} ajuste${changed > 1 ? "s" : ""}` : "Sem ajustes"} · salvo automaticamente</span>
      </footer>
      {confirm && <ConfirmDialog title="Restaurar a personalidade padrão?" text={`O estilo, os controles e as instruções extras de ${p.name} voltam ao padrão. As frases e a voz não mudam.`} confirmLabel="Restaurar"
        onCancel={() => setConfirm(false)} onConfirm={() => { setConfirm(false); void mutate("reset_personality"); }} />}
    </>
  );
}

function ItemRow({ item, onEdit, onToggle, onDelete }: { item: Item; onEdit: (t: string) => void; onToggle: (v: boolean) => void; onDelete: () => void }) {
  return (
    <li className="item">
      <Switch label={`Ativar: ${item.text}`} checked={item.enabled} onChange={onToggle} />
      <TextField label={`Editar frase: ${item.text}`} value={item.text} maxLength={300} onCommit={onEdit} />
      {item.origin === "usuario" && <Badge tone="ok">Nova</Badge>}
      {item.origin === "editada" && <Badge>Editada</Badge>}
      <Button variant="secondary" aria-label={`Apagar: ${item.text}`} onClick={onDelete}>Apagar</Button>
    </li>
  );
}

function ItemList({ list, data, mutate, noun }: { list: string; data: ListData; mutate: Mutate; noun: string }) {
  const [draft, setDraft] = useState("");
  return (
    <>
      <ul className="items">
        {data.items.map((i) => (
          <ItemRow key={i.id} item={i}
            onEdit={(t) => mutate("item_edit", { list, item: i.id, text: t })}
            onToggle={(v) => mutate("item_enable", { list, item: i.id, enabled: v })}
            onDelete={() => mutate("item_delete", { list, item: i.id })} />
        ))}
        {!data.items.length && <li className="muted small">Nenhum(a) {noun} ativo(a). Sem isso, o personagem fala só o que o modelo responder.</li>}
      </ul>
      <form className="add-row" onSubmit={async (e) => { e.preventDefault(); if (draft.trim() && (await mutate("item_add", { list, text: draft }))) setDraft(""); }}>
        <label htmlFor={`add-${list}`} className="sr-only">Nova {noun}</label>
        <input id={`add-${list}`} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={`+ Adicionar ${noun}`} maxLength={300} />
        <Button type="submit" disabled={!draft.trim()}>Adicionar</Button>
        {data.deleted.length > 0 && <Button onClick={() => mutate("restore_deleted", { list })}>Restaurar apagadas ({data.deleted.length})</Button>}
      </form>
    </>
  );
}

function PhrasesTab({ p, mutate }: { p: Profile; mutate: Mutate }) {
  const [moment, setMoment] = useState("inicio");
  const [confirm, setConfirm] = useState(false);
  const all = ["inicio", "concluir", "confirmar", "erro", "despedida", "tratamentos"];
  const stats = all.reduce((acc, l) => {
    const d: ListData = l === "tratamentos" ? { items: p.address.items, deleted: p.address.deleted } : p.phrases[l];
    acc.novas += d.items.filter((i) => i.origin === "usuario").length;
    acc.apagadas += d.deleted.length;
    return acc;
  }, { novas: 0, apagadas: 0 });
  return (
    <>
      <Section title="Como ele te chama" subtitle={`Variáveis: ${p.variables.join(" ")}. Uma frase cuja variável não tem valor é pulada.`}>
        <Segmented label="Modo do tratamento" value={p.address.mode} onChange={(v) => mutate("set_address_mode", { mode: v })}
          options={[{ value: "random", label: "Aleatório" }, { value: "fixed", label: "Fixo" }, { value: "context", label: "Por contexto" }]} />
        {p.address.mode === "fixed" && <TextField label="Tratamento fixo" value={p.address.fixed} maxLength={60} onCommit={(t) => mutate("set_address_mode", { mode: "fixed", fixed: t })} />}
        <ItemList list="tratamentos" data={{ items: p.address.items, deleted: p.address.deleted }} mutate={mutate} noun="tratamento" />
      </Section>
      <Section title="Falas" subtitle="O que ele diz em cada momento.">
        <Segmented label="Momento" value={moment} onChange={setMoment} options={MOMENTS} />
        <ItemList key={moment} list={moment} data={p.phrases[moment]} mutate={mutate} noun="frase" />
      </Section>
      <footer className="tab-foot">
        <Button onClick={() => setConfirm(true)} disabled={!stats.novas && !stats.apagadas && !p.edited}>Restaurar frases padrão</Button>
        <span className="muted small">{stats.novas} nova(s) · {stats.apagadas} apagada(s) · salvo automaticamente</span>
      </footer>
      {confirm && <ConfirmDialog title="Restaurar as frases padrão?" text={`Todas as listas de ${p.name} (tratamentos e falas) voltam ao padrão: as suas edições, apagadas e novas somem.`} confirmLabel="Restaurar"
        onCancel={() => setConfirm(false)}
        onConfirm={async () => { setConfirm(false); for (const l of all) await mutate("reset_list", { list: l }); }} />}
    </>
  );
}
