"""Servidor WebSocket local: autenticação, protocolo, eventos e o núcleo simulado."""

import io
import json
import threading
import time

import numpy as np
import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from fidus.core.bridge import protocol
from fidus.core.bridge.commands import CoreCommands
from fidus.core.bridge.confirm import ConfirmBroker
from fidus.core.bridge.core_state import CoreState, StateTap
from fidus.core.bridge.daemon import run_daemon
from fidus.core.bridge.server import Bridge, new_token
from fidus.core.bridge.settings_schema import InvalidSetting, validate
from fidus.core.persona import PersonaService


def url(b):
    return f"ws://127.0.0.1:{b.port}/"


import contextlib

_stack = contextlib.ExitStack()


@pytest.fixture(autouse=True)
def _close_clients():
    yield
    _stack.close()


class Client:
    """Cliente de teste: guarda os eventos que chegam antes da resposta de um comando."""

    def __init__(self, ws):
        self.ws, self.pending = ws, []

    def send(self, data):
        self.ws.send(data)

    def raw(self, timeout=3):
        return self.ws.recv(timeout=timeout)


def dial(u, **kw):
    return Client(_stack.enter_context(connect(u, open_timeout=3, **kw)))


def open_ws(b, token=None, auth=True, **kw):
    ws = dial(url(b), **kw)
    if auth:
        ws.send(protocol.encode({"type": "auth", "token": b.token if token is None else token}))
    return ws


def recv(ws, timeout=3):
    if ws.pending:
        return ws.pending.pop(0)
    return json.loads(ws.raw(timeout))


def cmd(ws, name, cid="1", **args):
    ws.send(protocol.encode({"type": "cmd", "id": cid, "name": name, "args": args}))
    while True:  # eventos que chegam antes da resposta ficam guardados para recv()
        m = json.loads(ws.raw())
        if m.get("type") == "reply":
            return m
        ws.pending.append(m)


@pytest.fixture
def bridge():
    calls = []

    def handler(name, args):
        calls.append((name, args))
        if name == "boom":
            raise RuntimeError("falhou")
        return {"echo": args}

    b = Bridge(handler, lambda: {"state": "idle"})
    b.calls = calls
    b.start()
    yield b
    b.stop()


# ---------- segurança ----------


def test_so_escuta_em_127_0_0_1_e_o_token_muda_a_cada_inicializacao():
    a, b = Bridge(lambda *x: None, dict), Bridge(lambda *x: None, dict)
    assert a.token != b.token and len(a.token) >= 40 and new_token() != new_token()
    a.start()
    try:
        assert a.host == "127.0.0.1" and a.port > 0
        import socket

        with pytest.raises(OSError):  # outra interface de rede (se existir) não aceita
            local = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")]
            if not local:
                raise OSError("sem outra interface")
            socket.create_connection((local[0], a.port), timeout=1)
    finally:
        a.stop()


def test_token_errado_e_fechado_com_4401(bridge):
    ws = open_ws(bridge, token="errado")
    with pytest.raises(ConnectionClosed) as e:
        ws.raw(3)
    assert e.value.rcvd.code == 4401


def test_sem_autenticar_a_conexao_cai(bridge, monkeypatch):
    monkeypatch.setattr("fidus.core.bridge.server.AUTH_TIMEOUT_S", 0.3)
    ws = open_ws(bridge, auth=False)
    with pytest.raises(ConnectionClosed):
        ws.raw(3)


def test_comando_antes_de_autenticar_nao_executa(bridge):
    ws = open_ws(bridge, auth=False)
    ws.send(protocol.encode({"type": "cmd", "id": "1", "name": "ping", "args": {}}))
    with pytest.raises(ConnectionClosed):
        ws.raw(3)
    assert bridge.calls == []


def test_navegadores_com_origin_sao_recusados(bridge):
    with pytest.raises(InvalidStatus) as e:
        with connect(url(bridge), origin="http://pagina-maliciosa.example", open_timeout=3):
            pass
    assert e.value.response.status_code == 403
    assert bridge.calls == []


def test_mensagem_gigante_derruba_a_conexao(bridge):
    ws = open_ws(bridge)
    assert recv(ws)["type"] == "ready"
    ws.send("x" * (protocol.MAX_MESSAGE_BYTES + 10))
    with pytest.raises(ConnectionClosed):
        ws.raw(3)


# ---------- protocolo ----------


def test_ready_traz_a_versao_e_o_snapshot(bridge):
    ws = open_ws(bridge)
    m = recv(ws)
    assert m == {"type": "ready", "protocol": protocol.PROTOCOL_VERSION, "snapshot": {"state": "idle"}}


def test_comando_valido_responde_com_o_mesmo_id(bridge):
    ws = open_ws(bridge)
    recv(ws)
    r = cmd(ws, "mute", cid="abc", value=True)
    assert r == {"type": "reply", "id": "abc", "ok": True, "data": {"echo": {"value": True}}}
    assert bridge.calls == [("mute", {"value": True})]


def test_erros_de_protocolo_nao_derrubam_a_conexao(bridge):
    ws = open_ws(bridge)
    recv(ws)
    for bad in ('{"type":"cmd","id":"1","name":"apagar_tudo","args":{}}', '{"type":"cmd","name":"mute"}',
                '{"type":"cmd","id":"1","name":"mute","args":[1]}', "isso não é json", '{"sem":"type"}', '{"type":"outra"}'):
        ws.send(bad)
        r = recv(ws)
        assert r["type"] == "reply" and r["ok"] is False and r["error"]
    assert cmd(ws, "ping")["ok"]  # continua funcionando
    assert bridge.calls == [("ping", {})]  # nenhum dos inválidos chegou ao núcleo


def test_erro_dentro_do_comando_vira_resposta_de_erro(bridge, monkeypatch):
    monkeypatch.setattr(protocol, "COMMANDS", (*protocol.COMMANDS, "boom"))
    ws = open_ws(bridge)
    recv(ws)
    r = cmd(ws, "boom")
    assert r["ok"] is False and "RuntimeError" in r["error"]
    assert cmd(ws, "ping")["ok"]


def test_eventos_chegam_a_todos_os_clientes_e_sem_cliente_nao_fazem_nada(bridge):
    bridge.emit("state", state="listening")  # ninguém conectado: descartado sem erro
    assert not bridge.has_clients
    a, b = open_ws(bridge), open_ws(bridge)
    recv(a), recv(b)
    time.sleep(0.1)
    assert bridge.has_clients
    bridge.emit("caption", role="user", text="olá", final=True)
    assert recv(a) == recv(b) == {"type": "caption", "role": "user", "text": "olá", "final": True}


def test_emit_de_varios_threads(bridge):
    ws = open_ws(bridge)
    recv(ws)
    time.sleep(0.1)
    ts = [threading.Thread(target=lambda i=i: [bridge.emit("level", values=[i / 10] * 3) for _ in range(20)]) for i in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    got = [recv(ws) for _ in range(100)]
    assert all(m["type"] == "level" and len(m["values"]) == 3 for m in got)


def test_decode_e_parse_command():
    assert protocol.decode(b'{"type":"x"}') == {"type": "x"}
    assert protocol.parse_command({"type": "cmd", "id": 7, "name": "ping"}) == ("7", "ping", {})
    for bad in ({"type": "cmd", "id": True, "name": "ping"}, {"type": "evt"}, {"type": "cmd", "id": "1", "name": "x"}):
        with pytest.raises(protocol.ProtocolError):
            protocol.parse_command(bad)
    assert set(protocol.STATES) == {"idle", "listening", "thinking", "speaking", "muted"}  # parado, ouvindo, pensando, falando, silenciado


# ---------- núcleo simulado de ponta a ponta ----------


class Lines(io.StringIO):
    pass


def start_simulated(config):
    out, ready = Lines(), threading.Event()
    t = threading.Thread(target=run_daemon, kwargs={"config": config, "simulated": True, "out": out, "ready_event": ready}, daemon=True)
    t.start()
    assert ready.wait(10)
    info = json.loads(out.getvalue().split("FIDUS_READY ", 1)[1])
    return info, t


def test_nucleo_simulado_anuncia_porta_e_token_e_encena_uma_conversa(config, monkeypatch):
    info, t = start_simulated(config)
    assert set(info) == {"port", "token", "protocol"} and info["protocol"] == 1
    ws = dial(f"ws://127.0.0.1:{info['port']}/")
    ws.send(protocol.encode({"type": "auth", "token": info["token"]}))
    ready = recv(ws)
    snap = ready["snapshot"]
    assert snap["character"]["id"] == "alfred" and snap["default_character"] == "alfred" and snap["model"]["name"] == "claude-sonnet-5-5"
    assert {c["id"] for c in snap["characters"]} == {"alfred", "donna", "jarbis"} and len(snap["character"]["ring"]["dark"]) == 3

    ws.send(protocol.encode({"type": "cmd", "id": "s", "name": "simulate", "args": {}}))
    events = []
    t0 = time.time()
    while time.time() - t0 < 20:
        m = recv(ws, timeout=10)
        if m["type"] != "reply":
            events.append(m)
        if m["type"] == "state" and m["state"] == "idle" and any(e["type"] == "caption" for e in events):
            break
    states = [e["state"] for e in events if e["type"] == "state"]
    assert states == ["listening", "thinking", "speaking", "idle"]
    levels = [e["values"] for e in events if e["type"] == "level"]
    assert levels and all(len(v) == 3 and all(0 <= x <= 1 for x in v) for v in levels)
    caps = [e for e in events if e["type"] == "caption"]
    assert caps[0] == {"type": "caption", "role": "user", "text": "O que tenho na agenda hoje?", "final": True}
    assistant = "".join(c["text"] for c in caps if c["role"] == "assistant")
    assert assistant.strip() == "Bom dia. Você tem duas reuniões; a primeira é às 9h."
    assert caps[-1]["final"] is True
    assert cmd(ws, "quit")["ok"]
    t.join(5)
    assert not t.is_alive()


def test_simulado_comandos_da_bandeja(config):
    info, t = start_simulated(config)
    ws = dial(f"ws://127.0.0.1:{info['port']}/")
    ws.send(protocol.encode({"type": "auth", "token": info["token"]}))
    recv(ws)
    r = cmd(ws, "mute", value=True)
    assert r["ok"] and recv(ws) == {"type": "state", "state": "muted", "mic": "muted"}
    cmd(ws, "mute", value=False)
    assert recv(ws)["state"] == "idle"
    cmd(ws, "pause", minutes=60)
    ev = recv(ws)
    assert ev["type"] == "calls" and ev["enabled"] is False and ev["until"] > time.time() + 3500
    assert cmd(ws, "mute", value="sim")["ok"] is False  # tipo errado é recusado
    r = cmd(ws, "set_default_character", id="batman")
    assert r["ok"] is False
    cmd(ws, "quit")
    t.join(5)


# ---------- configurações: só o que está na tabela ----------


def test_schema_valida_tipos_e_faixas():
    assert validate("usuario.nome", "  Ana ") == "Ana"
    assert validate("chamados.som_ao_ouvir", True) is True
    for key, val in (("usuario.nome", 5), ("usuario.nome", "x" * 500), ("chamados.som_ao_ouvir", "sim"),
                     ("chamados.personagem_padrao", "batman"), ("api.chave", "x"), ("../x", 1), ("usuario.sobrenome", None)):
        with pytest.raises(InvalidSetting):
            validate(key, val)


@pytest.fixture
def commands(config, tmp_path, monkeypatch):
    monkeypatch.setenv("FIDUS_HOME", str(config.data_dir))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "nao.toml"))
    config.data_dir.mkdir(parents=True, exist_ok=True)
    seen = []

    class Sink:
        has_clients = True

        def emit(self, type, **d):
            seen.append((type, d))

    persona = PersonaService(config)
    state = CoreState(config, persona, Sink())
    c = CoreCommands(config, state, persona=persona)
    c.seen = seen
    return c


def test_set_settings_grava_valida_e_aplica_sem_reiniciar(commands, config):
    r = commands.handle("set_settings", {"patch": {"usuario.nome": "Ana", "chamados.som_ao_ouvir": True}})
    assert r["saved"] == ["chamados.som_ao_ouvir", "usuario.nome"]
    assert json.loads(config.settings_path.read_text())["usuario"]["nome"] == "Ana"
    assert config.user.name == "Ana" and config.wake.beep is True  # já aplicado ao núcleo em execução
    assert commands.seen[-1][0] == "settings"


def test_patch_com_um_valor_invalido_nao_grava_nada(commands, config):
    with pytest.raises(InvalidSetting):
        commands.handle("set_settings", {"patch": {"usuario.nome": "Ana", "chamados.personagem_padrao": "batman"}})
    assert not config.settings_path.exists()
    with pytest.raises(ValueError):
        commands.handle("set_settings", {"patch": {}})


def test_trocar_personagem_padrao(commands, config):
    commands.handle("set_default_character", {"id": "donna"})
    assert config.wake.default_character == "donna" and commands.persona.default_id() == "donna"
    kinds = [t for t, _ in commands.seen]
    assert "settings" in kinds and any(t == "character" and d["id"] == "donna" for t, d in commands.seen)
    with pytest.raises(ValueError):
        commands.handle("set_default_character", {"id": "batman"})


def test_snapshot_acompanha_os_eventos(config):
    seen = []

    class Sink:
        has_clients = False

        def emit(self, t, **d):
            seen.append(t)

    persona = PersonaService(config)
    state = CoreState(config, persona, Sink())
    tap = StateTap(Sink(), state)
    tap.emit("state", state="listening", mic="recording")
    tap.emit("character", id="donna", name="Donna")
    tap.emit("calls", enabled=False, until=123.0)
    s = state.snapshot()
    assert (s["state"], s["mic"], s["calls"]) == ("listening", "recording", {"enabled": False, "until": 123.0})
    assert state.character_id == "donna" and state.model_info()["where"] == "Nuvem"
    tap.emit("state", state="muted", mic="muted")
    assert state.snapshot()["muted"] is True


# ---------- confirmação: clique na tela ou voz, vale a primeira ----------


class Events:
    def __init__(self, clients=True):
        self.has_clients, self.sent = clients, []

    def emit(self, t, **d):
        self.sent.append((t, d))


def test_confirmacao_pela_interface_antes_da_voz():
    ev = Events()
    b = ConfirmBroker(ev, timeout_s=3)
    release = threading.Event()

    def voice(prompt):  # a voz "fala" e depois cai no plano B (esperar a interface)
        release.wait(3)
        return b.wait_ui(prompt)

    result = []
    t = threading.Thread(target=lambda: result.append(b.run("Abrir regedit?", voice)))
    t.start()
    while not ev.sent:
        time.sleep(0.01)
    kind, data = ev.sent[0]
    assert kind == "confirm" and data["text"] == "Abrir regedit?" and data["id"]
    assert b.reply(data["id"], True) is True and b.is_answered()  # o clique: a voz deve parar de ouvir
    release.set()
    t.join(3)
    assert result == [True] and ev.sent[-1][0] == "confirm_done"


def test_confirmacao_por_voz_antes_da_interface():
    ev = Events()
    b = ConfirmBroker(ev, timeout_s=3)
    assert b.run("x", lambda p: False) is False
    assert [t for t, _ in ev.sent] == ["confirm", "confirm_done"]
    assert b.reply("velho", True) is False  # resposta atrasada da interface: ignorada


def test_resposta_de_confirmacao_com_id_errado_e_ignorada():
    b = ConfirmBroker(Events(), timeout_s=3)
    done = []

    def voice(prompt):
        assert b.reply("outro-id", True) is False  # id que não é o pedido atual
        return False

    assert b.run("x", voice) is False


def test_sem_interface_o_plano_b_nega_na_hora():
    b = ConfirmBroker(Events(clients=False), timeout_s=30)
    t0 = time.time()
    assert b.wait_ui("x") is False and time.time() - t0 < 1


def test_timeout_sem_resposta_nega():
    b = ConfirmBroker(Events(), timeout_s=0.2)
    assert b.run("x", lambda p: b.wait_ui(p)) is False


# ---------- nível de áudio e integração com os laços ----------


def test_nivel_de_audio_tres_valores_por_bloco_entre_0_e_1():
    from fidus.core.voice.levels import block_levels

    quiet = block_levels(np.zeros(1280, dtype=np.int16))
    loud = block_levels((np.sin(np.arange(1280) / 5) * 20000).astype(np.int16))
    assert len(quiet) == len(loud) == 3 and quiet == [0.0] * 3 and all(0.5 < v <= 1 for v in loud)
    assert all(0 <= v <= 1 for v in block_levels(np.full(1280, 32767, dtype=np.int16)))


def test_gerenciador_de_audio_so_calcula_nivel_com_interface_conectada():
    from fidus.core.voice.audio_manager import AudioManager

    class S:
        def __init__(self, cb): ...
        def start(self): ...
        def stop(self): ...
        def close(self): ...

    got, watching = [], [False]
    m = AudioManager(stream_factory=S)
    m.start()
    m.on_level, m.level_enabled = got.append, lambda: watching[0]
    m.feed(np.full(1280, 3000, dtype=np.int16))
    assert got == []  # janela fechada: custo zero
    watching[0] = True
    m.feed(np.full(1280, 3000, dtype=np.int16))
    assert len(got) == 1 and len(got[0]) == 3
    # ~12,5 blocos por segundo x 3 valores = ~37 valores por segundo


def test_voz_avisa_a_interface_das_legendas_e_estados(config):
    from conftest import FakeProvider
    from fidus.core.actionlog import ActionLog
    from fidus.core.orchestrator import Orchestrator
    from fidus.core.providers.base import Response
    from fidus.core.voice.loop import VoiceLoop
    from test_voice_loop import FakeSTT, FakeTTS, StreamingProvider, audio

    ev = Events()
    prov = StreamingProvider([Response("Bom dia. Duas reuniões.")], ["Bom dia", ". Duas reuniões", "."])
    log = ActionLog(config.log_path)
    orch = Orchestrator(config, prov, lambda p: True, tools={}, log=log)
    tts = FakeTTS()
    loop = VoiceLoop(config, orch, FakeSTT("o que tenho hoje"), tts, None, log, out=lambda s: None, events=ev)
    loop.handle_audio(audio(), 0.0)
    kinds = [t for t, _ in ev.sent]
    assert kinds[0] == "caption" and ev.sent[0][1] == {"role": "user", "text": "o que tenho hoje", "final": True}
    assert ("state", {"state": "thinking", "mic": "paused"}) in ev.sent and ("state", {"state": "speaking", "mic": "paused"}) in ev.sent
    streamed = "".join(d["text"] for t, d in ev.sent if t == "caption" and d["role"] == "assistant")
    assert streamed == "Bom dia. Duas reuniões." and ev.sent[-1][1]["final"] is True


def test_listen_loop_pausa_chamados_e_avisa_a_interface(config, tmp_path):
    from fidus.core.actionlog import ActionLog
    from fidus.core.voice.audio_manager import AudioManager
    from fidus.core.voice.indicator import Indicator
    from fidus.core.voice.listen_loop import ListenLoop
    from test_listen_loop import FakeStream, FakeTTS, FakeVAD, Handler

    config.data_dir = tmp_path / "d"
    ev = Events()
    m = AudioManager(stream_factory=FakeStream)
    m.start()
    loop = ListenLoop(config, m, None, FakeVAD(), Handler(), FakeTTS(), Indicator(lambda s: None), ActionLog(config.log_path), out=lambda s: None, events=ev)
    loop._sleep()
    assert m.state == "passive"
    loop.pause_calls(60)
    assert m.state == "paused" and loop.calls_enabled is False and loop.paused_until > time.time() + 3500
    assert ("calls", {"enabled": False, "until": loop.paused_until}) in ev.sent
    loop._sleep()  # voltar a dormir NÃO reativa a detecção enquanto pausado
    assert m.state == "paused"
    loop.pause_calls(0)  # cancela a pausa
    assert loop.calls_enabled and m.state == "passive" and loop.paused_until is None
    loop.set_calls_enabled(False)
    assert m.state == "paused"
    loop.set_calls_enabled(True)
    loop.set_muted(True)
    assert m.state == "muted" and ("state", {"state": "muted", "mic": "muted"}) in ev.sent
    loop.set_muted(False)
    assert m.state == "passive"
    loop.request_stop()
    assert loop._stopping


def test_estado_da_interface_a_partir_do_laco():
    from fidus.core.bridge.events import ui_state

    assert [ui_state(s, False) for s in ("sleeping", "recording", "followup", "processing")] == ["idle", "listening", "listening", "thinking"]
    assert ui_state("recording", True) == "muted"


def test_daemon_encerra_sozinho_quando_o_pai_morre(tmp_path):
    """O Electron mantém o stdin aberto. Se ele morrer, o stdin fecha e o núcleo não pode ficar órfão."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "FIDUS_HOME": str(tmp_path), "FIDUS_CONFIG": str(tmp_path / "x.toml"), "PYTHONUNBUFFERED": "1"}
    p = subprocess.Popen([sys.executable, "-m", "fidus", "daemon", "--simulado", "--stdin-watch"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True)
    try:
        line = p.stdout.readline()
        assert line.startswith("FIDUS_READY ")
        info = json.loads(line.split(" ", 1)[1])
        assert info["port"] > 0 and len(info["token"]) >= 40
        p.stdin.close()  # "o Electron morreu"
        assert p.wait(timeout=15) == 0
    finally:
        if p.poll() is None:
            p.kill()
