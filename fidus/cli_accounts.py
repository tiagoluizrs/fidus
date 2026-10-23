"""Comandos de contas e segredos: `fidus secrets ...` e `fidus accounts ...`."""

from __future__ import annotations

import argparse
import getpass
import re
from pathlib import Path

from .core import secrets as vault
from .core import settings
from .core.config import load_config

_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_SERVICES = {"agenda": "calendar", "gmail": "gmail"}


def _source(name: str) -> str:
    if vault.get_vault_secret(name):
        return "cofre do sistema"
    return "variável de ambiente (.env, só desenvolvimento)" if vault.get_secret(name) else "não definido"


# ------------------------------------------------------------------ secrets


def cmd_secrets(argv: list[str], ask_secret=getpass.getpass, confirm=lambda p: input(p).strip().lower() in {"s", "sim"}) -> int:
    p = argparse.ArgumentParser(prog="fidus secrets", description="Chaves e tokens no Gerenciador de Credenciais do Windows")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("set", help="guarda um segredo no cofre")
    st.add_argument("nome")
    st.add_argument("--valor", help="evite: fica no histórico do terminal; sem isso o valor é pedido sem aparecer")
    gt = sub.add_parser("get", help="mostra um segredo (mascarado)")
    gt.add_argument("nome")
    gt.add_argument("--mostrar", action="store_true", help="mostra o valor inteiro")
    dl = sub.add_parser("delete", help="apaga um segredo do cofre")
    dl.add_argument("nome")
    sub.add_parser("list", help="mostra onde cada segredo conhecido está")
    mg = sub.add_parser("migrate", help="move a ANTHROPIC_API_KEY do .env para o cofre")
    mg.add_argument("--arquivo", default=".env")
    mg.add_argument("--remover-do-env", action="store_true", help="apaga a chave do .env depois de migrar")
    a = p.parse_args(argv)

    try:
        if a.cmd in {"set", "get", "delete"} and not _NAME.match(a.nome):
            print("Nome inválido: use letras, números e _.")
            return 2
        if a.cmd == "set":
            value = a.valor or ask_secret(f"Valor de {a.nome} (não aparece): ")
            if not value.strip():
                print("Valor vazio: nada foi guardado.")
                return 1
            vault.set_secret(a.nome, value.strip())
            print(f"{a.nome} guardado no cofre do sistema.")
        elif a.cmd == "get":
            value = vault.get_secret(a.nome)
            if not value:
                print(f"{a.nome}: não definido.")
                return 1
            print(f"{a.nome} ({_source(a.nome)}): {value if a.mostrar else vault.mask(value)}")
        elif a.cmd == "delete":
            print("Apagado do cofre." if vault.delete_secret(a.nome) else f"{a.nome} não estava no cofre.")
        elif a.cmd == "list":
            for name in vault.KNOWN:
                print(f"{name:<24} {_source(name)}")
        else:
            return _migrate(Path(a.arquivo), a.remover_do_env, confirm)
    except vault.VaultUnavailable as e:
        print(f"Cofre indisponível: {e}")
        return 1
    return 0


def _migrate(env_file: Path, remove: bool, confirm) -> int:
    key = vault.ANTHROPIC_KEY
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []
    idx = next((i for i, l in enumerate(lines) if re.match(rf"^\s*{key}\s*=", l)), None)
    value = lines[idx].split("=", 1)[1].strip().strip("'\"") if idx is not None else ""
    if not value:
        print(f"Não há {key} no {env_file}. Nada a migrar.")
        return 0
    vault.set_secret(key, value)
    if vault.get_vault_secret(key) != value:
        print("A chave não ficou no cofre; o .env foi mantido.")
        return 1
    print(f"{key} guardada no cofre ({vault.mask(value)}).")
    if remove or confirm(f"Remover a chave do {env_file} agora? [s/n] "):
        lines[idx] = f"# {key} foi movida para o Gerenciador de Credenciais (uv run fidus secrets list)"
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Removida do {env_file}.")
    else:
        print(f"Mantida no {env_file}: apague a linha quando quiser (o cofre tem prioridade sobre o .env).")
    return 0


# ------------------------------------------------------------------ accounts


def cmd_accounts(argv: list[str], ask_secret=getpass.getpass) -> int:
    p = argparse.ArgumentParser(prog="fidus accounts", description="Contas: Google Agenda, Gmail e Slack")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    cn = sub.add_parser("connect")
    cn.add_argument("servico", choices=["agenda", "gmail", "slack"])
    cn.add_argument("--escrita", action="store_true", help="libera escrita (agenda: criar/alterar; gmail: rascunhos; slack: responder)")
    dc = sub.add_parser("disconnect")
    dc.add_argument("servico", choices=["agenda", "gmail", "slack"])
    ch = sub.add_parser("channels", help="canais do Slack que o Fidus pode ler")
    ch.add_argument("acao", choices=["list", "add", "remove"])
    ch.add_argument("nome", nargs="?")
    a = p.parse_args(argv)
    cfg = load_config()

    from .core.services import google_auth
    from .core.services.base import NotConnected

    try:
        if a.cmd == "list":
            ac = cfg.accounts
            for label, svc, write_flag in (("agenda", "calendar", ac.google_calendar_write), ("gmail", "gmail", ac.gmail_drafts)):
                on = google_auth.is_connected(svc)
                print(f"{label:<8} {'conectado' if on else 'não conectado'}" + (f", escrita {'liberada' if write_flag else 'desligada'}" if on else ""))
            tok = bool(vault.get_secret(vault.SLACK_TOKEN))
            print(f"{'slack':<8} {'conectado' if tok else 'não conectado'}" + (f", resposta {'liberada' if ac.slack_write else 'desligada'}, canais: {', '.join(ac.slack_channels) or '(nenhum permitido)'}" if tok else ""))
            print("Outlook, Teams e Microsoft Agenda: em breve.")
        elif a.cmd == "connect":
            if a.servico == "slack":
                token = ask_secret("Token de usuário do Slack (xoxp-..., não aparece): ").strip()
                from .core.services.slack import Slack

                info = Slack(cfg, token=token)._call("auth.test")  # valida o token antes de guardar
                vault.set_secret(vault.SLACK_TOKEN, token)
                settings.set_value(cfg.settings_path, "contas.slack.escrita", a.escrita)
                print(f"Slack conectado ({info.get('team', '?')} como {info.get('user', '?')}). Resposta {'liberada' if a.escrita else 'desligada'}.")
                if not cfg.accounts.slack_channels:
                    print("Agora escolha os canais que o Fidus pode ler: uv run fidus accounts channels add <nome>")
            else:
                scopes = google_auth.connect(cfg, _SERVICES[a.servico], a.escrita)
                flag = "contas.google.agenda_escrita" if a.servico == "agenda" else "contas.google.gmail_rascunhos"
                settings.set_value(cfg.settings_path, flag, a.escrita)
                print(f"{a.servico} conectado. Permissões pedidas ao Google: {', '.join(s.rsplit('/', 1)[-1] for s in scopes)}.")
        elif a.cmd == "disconnect":
            if a.servico == "slack":
                done = vault.delete_secret(vault.SLACK_TOKEN)
                settings.set_value(cfg.settings_path, "contas.slack.escrita", False)
            else:
                done = google_auth.disconnect(_SERVICES[a.servico])
                settings.set_value(cfg.settings_path, "contas.google.agenda_escrita" if a.servico == "agenda" else "contas.google.gmail_rascunhos", False)
            print("Desconectado e apagado do cofre." if done else "Já estava desconectado.")
            print("Para revogar também no provedor: conta Google > Segurança > Acesso de terceiros; Slack > Apps > Remover.")
        else:  # channels
            chans = list(cfg.accounts.slack_channels)
            name = (a.nome or "").lstrip("#")
            if a.acao == "add" and name and name not in chans:
                chans.append(name)
            elif a.acao == "remove":
                chans = [c for c in chans if c != name]
            if a.acao != "list":
                settings.set_value(cfg.settings_path, "contas.slack.canais_permitidos", chans)
            print("Canais permitidos: " + (", ".join(chans) or "(nenhum)"))
    except (NotConnected, vault.VaultUnavailable) as e:
        print(f"Erro: {e}")
        return 1
    return 0
