import { useCallback, useEffect, useRef, useState } from "react";
import { useCore } from "../core";
import { Badge, Button, ConfirmDialog, Page, Row, Section, Switch } from "../ui";

interface Entry { id: string; section: string; text: string; tag: string | null; ts: string; source: "usuario" | "aprendida" }
interface Data { entries: Entry[]; sections: string[]; tags: string[] }

export function ago(ts: string, now = Date.now()): string {
  const t = Date.parse(ts);
  if (!ts || Number.isNaN(t)) return "";
  const days = Math.max(0, Math.floor((now - t) / 86400000));
  if (days === 0) return "hoje";
  if (days === 1) return "ontem";
  if (days < 7) return `há ${days} dias`;
  if (days < 30) return `há ${Math.floor(days / 7)} semana${days >= 14 ? "s" : ""}`;
  if (days < 365) return `há ${Math.floor(days / 30)} ${days >= 60 ? "meses" : "mês"}`;
  return `há ${Math.floor(days / 365)} ano${days >= 730 ? "s" : ""}`;
}

export function Memoria() {
  const { eff, save, call, subscribe, notify } = useCore();
  const [data, setData] = useState<Data | null>(null);
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [del, setDel] = useState<Entry | null>(null);
  const [wipe, setWipe] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(async (q: string) => {
    const d = await call<Data>("memory", { op: "list", query: q }, { quiet: true });
    if (d) setData(d);
  }, [call]);
  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void load(query), 200); // busca enquanto digita, sem martelar o núcleo
    return () => clearTimeout(timer.current);
  }, [query, load]);
  useEffect(() => subscribe((e) => e.type === "memory_changed" && void load(query)), [subscribe, load, query]);

  const exportMd = async () => {
    const r = await call<{ markdown: string; filename: string }>("memory", { op: "export" });
    if (r && (await window.fidus.saveTextFile(r.filename, r.markdown))) notify("ok", "Memória exportada em Markdown.");
  };

  return (
    <Page title="Memória" subtitle="O que o Fidus sabe sobre você. Fica guardado só neste computador.">
      <Section title="Lembranças" subtitle="Editar ou apagar vale para todos os personagens.">
        <div className="mem-toolbar">
          <label htmlFor="mem-search" className="sr-only">Buscar lembranças</label>
          <input id="mem-search" type="search" placeholder="Buscar lembranças" value={query} onChange={(e) => setQuery(e.target.value)} />
          <Button onClick={() => setAdding(true)}>+ Adicionar</Button>
        </div>
        {adding && data && <AddForm data={data} onDone={() => setAdding(false)} />}
        <ul className="memories">
          {data?.entries.map((e) => <MemoryRow key={e.id} e={e} tags={data.tags} onDelete={() => setDel(e)} />)}
          {data && !data.entries.length && <li className="muted small">{query ? "Nada encontrado." : "Nenhuma lembrança ainda. Peça ao Fidus para lembrar de algo, ou adicione aqui."}</li>}
        </ul>
      </Section>

      <Section title="Aprendizado" subtitle="Como o Fidus guarda o que aprende sobre você.">
        <Row label="Aprender com as conversas" hint="Se desligar, o Fidus não guarda nada sozinho; você adiciona as lembranças aqui.">
          <Switch label="Aprender com as conversas" checked={eff["memoria.aprender"] !== false} onChange={(v) => save({ "memoria.aprender": v })} />
        </Row>
        <Row label="Perguntar antes de guardar algo novo">
          <Switch label="Perguntar antes de guardar algo novo" checked={eff["memoria.perguntar_antes_de_guardar"] === true} onChange={(v) => save({ "memoria.perguntar_antes_de_guardar": v })} />
        </Row>
        <p className="muted small">A memória é uma só: trocar de personagem muda o jeito de falar, mas não o que ele sabe de você.</p>
        <div className="actions">
          <Button onClick={() => void exportMd()}>Exportar memória (Markdown)</Button>
          <Button variant="danger" onClick={() => setWipe(true)}>Apagar toda a memória</Button>
        </div>
      </Section>

      {del && <ConfirmDialog danger title="Apagar esta lembrança?" text={`“${del.text}”. Vale para todos os personagens e não dá para desfazer.`} confirmLabel="Apagar"
        onCancel={() => setDel(null)} onConfirm={async () => { await call("memory", { op: "delete", id: del.id, confirm: true }); setDel(null); }} />}
      {wipe && <ConfirmDialog danger requireWord="APAGAR" title="Apagar toda a memória?" text="Todas as lembranças (perfil, rotinas, contatos e projetos) e o histórico de conversas serão apagados. Não dá para desfazer." confirmLabel="Apagar tudo"
        onCancel={() => setWipe(false)} onConfirm={async () => { await call("memory", { op: "delete_all", confirm: true }); await call("privacy", { op: "clear_history", confirm: true }, { quiet: true }); setWipe(false); notify("ok", "Memória apagada."); }} />}
    </Page>
  );
}

function MemoryRow({ e, tags, onDelete }: { e: Entry; tags: string[]; onDelete: () => void }) {
  const { call } = useCore();
  const [text, setText] = useState(e.text);
  useEffect(() => setText(e.text), [e.text]);
  const commit = () => text.trim() && text !== e.text && void call("memory", { op: "edit", id: e.id, text });
  return (
    <li className="memory">
      <div className="memory-main">
        <label htmlFor={`m-${e.id}`} className="sr-only">Editar lembrança</label>
        <input id={`m-${e.id}`} value={text} maxLength={500} onChange={(x) => setText(x.target.value)} onBlur={commit} onKeyDown={(x) => x.key === "Enter" && (x.target as HTMLInputElement).blur()} />
        <span className="muted small">{e.source === "aprendida" ? "Aprendida" : "Você disse"} · {ago(e.ts)} · {e.section}</span>
      </div>
      <select aria-label="Etiqueta" value={e.tag ?? ""} onChange={(x) => void call("memory", { op: "edit", id: e.id, tag: x.target.value })}>
        <option value="">sem etiqueta</option>
        {tags.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      {e.source === "aprendida" && <Badge>Aprendida</Badge>}
      <Button aria-label={`Apagar: ${e.text}`} onClick={onDelete}>Apagar</Button>
    </li>
  );
}

function AddForm({ data, onDone }: { data: Data; onDone: () => void }) {
  const { call } = useCore();
  const [text, setText] = useState("");
  const [section, setSection] = useState("perfil");
  const [tag, setTag] = useState("");
  return (
    <form className="add-memory" onSubmit={async (e) => { e.preventDefault(); if (text.trim() && (await call("memory", { op: "add", text, section, tag }))) onDone(); }}>
      <label htmlFor="new-mem" className="sr-only">Nova lembrança</label>
      <input id="new-mem" autoFocus value={text} maxLength={500} onChange={(e) => setText(e.target.value)} placeholder="O que o Fidus deve lembrar?" />
      <select aria-label="Seção" value={section} onChange={(e) => setSection(e.target.value)}>{data.sections.map((s) => <option key={s} value={s}>{s}</option>)}</select>
      <select aria-label="Etiqueta da nova lembrança" value={tag} onChange={(e) => setTag(e.target.value)}><option value="">sem etiqueta</option>{data.tags.map((t) => <option key={t} value={t}>{t}</option>)}</select>
      <Button variant="primary" type="submit" disabled={!text.trim()}>Guardar</Button>
      <Button onClick={onDone}>Cancelar</Button>
    </form>
  );
}
