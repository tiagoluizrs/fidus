"""Login do Google pela interface (Docker/navegador): servidor de retorno próprio, com a porta sempre liberada."""

import json
import socket
import sys
import threading
import time
import types
import urllib.request
from types import SimpleNamespace

import pytest

from fidus.core.bridge.commands import CoreCommands
from fidus.core.bridge.core_state import CoreState
from fidus.core.persona import PersonaService
from fidus.core.services import google_auth
from fidus.core.services.base import NotConnected
from test_services import FakeVault

DESKTOP = json.dumps({"installed": {
    "client_id": "abc.apps.googleusercontent.com", "client_secret": "segredo", "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeFlow:
    """Imita o que o fluxo do Google faz: monta o link, recebe o retorno e entrega as credenciais."""

    def __init__(self, path=None, scopes=None):
        self.scopes, self.redirect_uri, self.fetched = scopes, None, None

    def authorization_url(self, **kw):
        assert kw["access_type"] == "offline" and kw["prompt"] == "consent"
        return "https://accounts.google.com/o/oauth2/auth?x=1", "estado"

    def fetch_token(self, authorization_response):
        self.fetched = authorization_response

    @property
    def credentials(self):
        return SimpleNamespace(refresh_token="R", client_id="c", client_secret="s", token_uri=None)


def browser_returns(flow_ref, code="abc"):
    """Faz o papel do navegador: quando o link é entregue, o Google devolve o usuário ao endereço de retorno."""

    def open_url(url):
        def go():
            time.sleep(0.2)
            urllib.request.urlopen(f"{flow_ref['flow'].redirect_uri}?code={code}&state=estado", timeout=5).read()

        threading.Thread(target=go, daemon=True).start()

    return open_url


def test_retorno_do_login_chega_ao_fluxo_e_a_porta_volta_na_hora():
    port, flow = free_port(), FakeFlow()
    urls = []
    ref = {"flow": flow}
    inner = browser_returns(ref)
    creds = google_auth.run_flow_via_ui(flow, port, lambda u: (urls.append(u), inner(u)), timeout_s=10)
    assert creds.refresh_token == "R" and urls == ["https://accounts.google.com/o/oauth2/auth?x=1"]
    assert flow.redirect_uri == f"http://localhost:{port}/" and "code=abc" in flow.fetched and flow.fetched.startswith("https://")
    with socket.socket() as s:  # a porta já pode ser usada de novo (reutilizável, como o próprio servidor faz)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))


def test_dois_logins_seguidos_na_mesma_porta_funcionam():
    """O bug: depois do Gmail, a Agenda dava 'Address already in use'."""
    port = free_port()
    for _ in range(3):
        flow = FakeFlow()
        google_auth.run_flow_via_ui(flow, port, browser_returns({"flow": flow}), timeout_s=10)


def test_sem_retorno_vira_erro_claro_e_libera_a_porta():
    port = free_port()
    with pytest.raises(NotConnected, match="não foi concluído"):
        google_auth.run_flow_via_ui(FakeFlow(), port, lambda u: None, timeout_s=0.3)
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))


@pytest.fixture
def cmds(config, tmp_path, monkeypatch):
    monkeypatch.setenv("FIDUS_HOME", str(config.data_dir))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "nao.toml"))
    config.data_dir.mkdir(parents=True, exist_ok=True)
    seen = []
    sink = SimpleNamespace(has_clients=True, seen=seen, emit=lambda t, **d: seen.append((t, d)))
    persona = PersonaService(config)
    c = CoreCommands(config, CoreState(config, persona, sink), persona=persona)
    c.sink = sink
    c.loop = SimpleNamespace(headless=True, handler=None)
    c.h.loop = c.loop
    FakeVault().install(monkeypatch)
    monkeypatch.setattr(google_auth, "OAUTH_PORT", free_port())
    c.handle("accounts", {"op": "google_credentials", "json": DESKTOP})
    return c


def wait(pred, t=8):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def stub_google(monkeypatch, flows):
    def make(path, scopes):
        flows.append(FakeFlow(path, scopes))
        return flows[-1]

    mod = types.ModuleType("google_auth_oauthlib.flow")
    mod.InstalledAppFlow = SimpleNamespace(from_client_secrets_file=make)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", types.ModuleType("google_auth_oauthlib"))
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", mod)


def test_gmail_e_depois_agenda_conectam_um_apos_o_outro(cmds, monkeypatch):
    flows = []
    stub_google(monkeypatch, flows)
    for service in ("gmail", "agenda"):
        cmds.handle("accounts", {"op": "connect", "service": service})
        assert wait(lambda: any(t == "open_url" for t, _ in cmds.sink.seen) and flows[-1].redirect_uri)
        urllib.request.urlopen(f"{flows[-1].redirect_uri}?code=x&state=estado", timeout=5).read()
        assert wait(lambda s=service: any(t == "accounts" and d["service"] == s and d["status"] == "connected" for t, d in cmds.sink.seen))
        cmds.sink.seen.clear()
    assert len(flows) == 2


def test_segundo_clique_reenvia_o_link_e_outro_servico_espera(cmds, monkeypatch):
    flows = []
    stub_google(monkeypatch, flows)
    cmds.handle("accounts", {"op": "connect", "service": "agenda"})
    assert wait(lambda: any(t == "open_url" for t, _ in cmds.sink.seen) and flows[0].redirect_uri)
    cmds.handle("accounts", {"op": "connect", "service": "agenda"})  # segundo clique
    assert sum(1 for t, _ in cmds.sink.seen if t == "open_url") == 2 and len(flows) == 1
    with pytest.raises(ValueError, match="Já existe um login"):
        cmds.handle("accounts", {"op": "connect", "service": "gmail"})
    urllib.request.urlopen(f"{flows[0].redirect_uri}?code=x&state=estado", timeout=5).read()  # conclui o pendente
    assert wait(lambda: any(t == "accounts" and d["status"] == "connected" for t, d in cmds.sink.seen))
