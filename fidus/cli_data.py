"""Comandos de dados: `fidus character ...`, `fidus memory ...`, `fidus user ...`."""

from __future__ import annotations

import argparse

from .core import settings
from .core.characters.models import ADDRESS_MODES, CONTROLS, MOMENTS, STYLES
from .core.characters.store import ADDRESS, CharacterStore
from .core.config import load_config
from .core.memory.markdown_store import TAGS
from .core.memory.service import get_memory


def _yes(prompt: str, assume: bool) -> bool:
    return assume or input(f"{prompt} [s/n] ").strip().lower() in {"s", "sim", "y", "yes"}


# ------------------------------------------------------------------ character


def cmd_character(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="fidus character", description="Personagens: perfis, personalidade e frases")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="lista os personagens")
    sh = sub.add_parser("show", help="mostra o perfil completo")
    sh.add_argument("id")
    rs = sub.add_parser("reset", help="volta ao padrão (escolha o que restaurar)")
    rs.add_argument("id")
    g = rs.add_mutually_exclusive_group(required=True)
    g.add_argument("--controle", choices=CONTROLS, help="restaura um controle de personalidade")
    g.add_argument("--lista", choices=[*MOMENTS, ADDRESS], help="restaura uma lista (frases do momento ou tratamentos)")
    g.add_argument("--apagadas", choices=[*MOMENTS, ADDRESS], help="traz de volta só as frases padrão apagadas")
    g.add_argument("--voz", action="store_true", help="restaura a voz")
    g.add_argument("--personalidade", action="store_true", help="restaura estilo, controles e instruções extras")
    g.add_argument("--tudo", action="store_true", help="restaura o personagem inteiro")
    df = sub.add_parser("default", help="define o personagem padrão (responde ao atalho)")
    df.add_argument("id")
    st = sub.add_parser("set", help="edita personalidade, tratamento ou voz")
    st.add_argument("id")
    st.add_argument("--controle", action="append", default=[], metavar="NOME=0..100")
    st.add_argument("--estilo", choices=STYLES)
    st.add_argument("--extra", help="instruções extras (só o jeito de falar)")
    st.add_argument("--tratamento-modo", choices=ADDRESS_MODES)
    st.add_argument("--tratamento-fixo")
    st.add_argument("--voz", help="nome (ou parte) da voz; no Piper, o caminho do modelo .onnx")
    st.add_argument("--motor", choices=["sapi", "piper", "descricao"])
    st.add_argument("--tom", type=int)
    st.add_argument("--velocidade", type=int)
    ph = sub.add_parser("phrase", help="edita frases e tratamentos")
    ph.add_argument("id")
    ph.add_argument("lista", choices=[*MOMENTS, ADDRESS])
    ph.add_argument("acao", choices=["add", "edit", "delete", "on", "off"])
    ph.add_argument("valor", nargs="?", help="texto (add) ou id (edit/delete/on/off)")
    ph.add_argument("texto", nargs="?", help="novo texto (edit)")
    a = p.parse_args(argv)

    cfg = load_config()
    store = CharacterStore(cfg.characters_dir)
    try:
        if a.cmd == "list":
            default = store.default_id()
            for cid in store.ids():
                pr = store.load(cid)
                marks = (" [padrão]" if cid == cfg.wake.default_character or (cid == default and cfg.wake.default_character not in store.ids()) else "") + (" [editado]" if store.has_user_edits(cid) else "")
                print(f"{cid:<8} {pr.name:<8} \"{pr.call}\"  {pr.summary}{marks}")
        elif a.cmd == "show":
            _show(store, a.id, cfg)
        elif a.cmd == "default":
            store.load(a.id)
            settings.set_value(cfg.settings_path, "chamados.personagem_padrao", a.id)
            print(f"Personagem padrão: {a.id}")
        elif a.cmd == "reset":
            if a.tudo:
                store.reset_character(a.id)
            elif a.personalidade:
                store.reset_personality(a.id)
            elif a.controle:
                store.reset_control(a.id, a.controle)
            elif a.lista:
                store.reset_list(a.id, a.lista)
            elif a.apagadas:
                store.restore_deleted(a.id, a.apagadas)
            elif a.voz:
                store.reset_voice(a.id)
            print("Restaurado. Os arquivos padrão não foram alterados.")
        elif a.cmd == "set":
            for item in a.controle:
                name, _, value = item.partition("=")
                store.set_control(a.id, name.strip(), int(value))
            if a.estilo:
                store.set_style(a.id, a.estilo)
            if a.extra is not None:
                store.set_extra(a.id, a.extra)
            if a.tratamento_modo or a.tratamento_fixo is not None:
                store.set_address_mode(a.id, a.tratamento_modo or store.load(a.id).address_mode, a.tratamento_fixo)
            fields = {k: v for k, v in (("engine", a.motor), ("voice", a.voz), ("pitch", a.tom), ("rate", a.velocidade)) if v is not None}
            if fields:
                store.set_voice(a.id, **fields)
            print("Salvo.")
        elif a.cmd == "phrase":
            if a.acao == "add":
                print(f"Adicionada: {store.add_item(a.id, a.lista, a.valor or '')}")
            elif a.acao == "edit":
                store.edit_item(a.id, a.lista, a.valor or "", a.texto or "")
                print("Editada.")
            elif a.acao == "delete":
                store.delete_item(a.id, a.lista, a.valor or "")
                print("Apagada (a padrão pode ser restaurada com `reset --apagadas`).")
            else:
                store.set_enabled(a.id, a.lista, a.valor or "", a.acao == "on")
                print("Ok.")
    except (KeyError, ValueError) as e:
        print(f"Erro: {str(e).strip(chr(39))}")
        return 1
    return 0


def _show(store: CharacterStore, cid: str, cfg) -> None:
    pr = store.load(cid)
    default = store._default(cid)["personality"]["controls"]
    print(f"{pr.name} ({pr.id}){'  [editado]' if store.has_user_edits(cid) else ''}")
    print(f"  chamado: \"{pr.call}\"   {pr.summary}")
    print(f"  anel escuro: {' '.join(pr.ring['dark'])}   claro: {' '.join(pr.ring['light'])}")
    print(f"  estilo: {pr.personality.base_style}")
    for k in CONTROLS:
        v = pr.personality.controls.get(k)
        print(f"  {k:<11} {v:>3}" + (f"   (padrão {default[k]})" if v != default[k] else ""))
    if pr.personality.extra:
        print(f"  instruções extras: {pr.personality.extra}")
    print(f"  tratamento: modo {pr.address_mode}" + (f", fixo \"{pr.address_fixed}\"" if pr.address_mode == "fixed" else ""))
    for i in pr.address:
        print(f"    [{i.id}] {'on ' if i.enabled else 'off'} {i.text}" + (f"  contextos: {','.join(i.contexts)}" if i.contexts else "") + (f"  ({i.origin})" if i.origin != "padrao" else ""))
    for m in MOMENTS:
        gone = store.deleted_items(cid, m)
        print(f"  {m}" + (f"  ({len(gone)} padrão apagada(s))" if gone else ""))
        for i in pr.phrases[m]:
            print(f"    [{i.id}] {'on ' if i.enabled else 'off'} {i.text}" + (f"  ({i.origin})" if i.origin != "padrao" else ""))
    v = pr.voice
    print(f"  voz: motor {v.engine}, voz '{v.voice or 'padrão do sistema'}', tom {v.pitch}, velocidade {v.rate}")


# ------------------------------------------------------------------ memory


def cmd_memory(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="fidus memory", description="Memória única (Markdown em ~/.fidus/memoria)")
    sub = p.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="lista as lembranças")
    ls.add_argument("--secao")
    ls.add_argument("--etiqueta", choices=TAGS)
    sr = sub.add_parser("search", help="busca por assunto")
    sr.add_argument("consulta", nargs="+")
    ad = sub.add_parser("add", help="guarda uma lembrança")
    ad.add_argument("texto", nargs="+")
    ad.add_argument("--secao", default="perfil", help="perfil, rotinas, contatos ou projetos/<nome>")
    ad.add_argument("--etiqueta", choices=TAGS)
    dl = sub.add_parser("delete", help="apaga uma lembrança (pede confirmação)")
    dl.add_argument("id")
    dl.add_argument("--sim", action="store_true", help="não perguntar")
    ed = sub.add_parser("edit", help="edita o texto de uma lembrança")
    ed.add_argument("id")
    ed.add_argument("texto", nargs="+")
    sub.add_parser("export", help="imprime tudo em Markdown")
    fa = sub.add_parser("forget-all", help="apaga TODA a memória e o histórico (pede confirmação)")
    fa.add_argument("--sim", action="store_true")
    a = p.parse_args(argv)

    cfg = load_config()
    mem = get_memory(cfg)
    try:
        if a.cmd == "list":
            rows = mem.md.list(a.secao, a.etiqueta)
        elif a.cmd == "search":
            rows = mem.md.search(" ".join(a.consulta))
        elif a.cmd == "add":
            e = mem.md.add(a.secao, " ".join(a.texto), a.etiqueta)
            print(f"Guardado em {e.section} (id {e.id}).")
            return 0
        elif a.cmd == "edit":
            e = mem.md.edit(a.id, " ".join(a.texto))
            print(f"Atualizado (id {e.id}).")
            return 0
        elif a.cmd == "delete":
            e = mem.md.get(a.id)
            if not e:
                print("Lembrança não encontrada.")
                return 1
            if _yes(f'Apagar "{e.text}"?', a.sim):
                mem.md.delete(a.id)
                print("Apagado.")
            return 0
        elif a.cmd == "export":
            print(mem.md.export_markdown(), end="")
            return 0
        else:  # forget-all
            if _yes("Apagar TODAS as lembranças e o histórico? Não dá para desfazer.", a.sim):
                print(mem.forget_everything())
            return 0
        for e in rows:
            print(f"[{e.id}] ({e.section}{', ' + e.tag if e.tag else ''}) {e.text}")
        if not rows:
            print("Nada encontrado.")
    except (KeyError, ValueError) as e:
        print(f"Erro: {str(e).strip(chr(39))}")
        return 1
    return 0


# ------------------------------------------------------------------ user


def cmd_user(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="fidus user", description="Seu nome (usado nas falas dos personagens)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    st = sub.add_parser("set")
    st.add_argument("--nome")
    st.add_argument("--sobrenome")
    a = p.parse_args(argv)
    cfg = load_config()
    if a.cmd == "set":
        if a.nome is not None:
            settings.set_value(cfg.settings_path, "usuario.nome", a.nome.strip())
        if a.sobrenome is not None:
            settings.set_value(cfg.settings_path, "usuario.sobrenome", a.sobrenome.strip())
        cfg = load_config()
    print(f"nome: {cfg.user.name or '(não definido)'}   sobrenome: {cfg.user.surname or '(não definido)'}")
    return 0
