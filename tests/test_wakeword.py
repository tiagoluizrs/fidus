import json

import numpy as np
import pytest

from fidus.core.actionlog import ActionLog
from fidus.core.config import Config, WakeWord, load_config
from fidus.core.voice.characters import character_for
from fidus.core.voice.wakeword import (
    Activation,
    ActivationGate,
    DetectorRunner,
    OpenWakeWordDetector,
    load_detector,
)

ALFRED = WakeWord("ei_alfred", "ei_alfred.onnx", "alfred", threshold=0.5)
DONNA = WakeWord("ei_donna", "ei_donna.onnx", "donna", threshold=0.7)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---------- limiar e intervalo ----------


def test_limiar_por_palavra():
    gate = ActivationGate([ALFRED, DONNA], cooldown_s=0, clock=Clock())
    assert gate.check({"ei_alfred": 0.49, "ei_donna": 0.69}) is None
    assert gate.check({"ei_donna": 0.69}) is None  # donna exige 0.7
    a = gate.check({"ei_donna": 0.71})
    assert a.word.id == "ei_donna" and a.score == 0.71


def test_vence_a_maior_pontuacao_entre_as_acima_do_limiar():
    gate = ActivationGate([ALFRED, DONNA], cooldown_s=0, clock=Clock())
    assert gate.check({"ei_alfred": 0.9, "ei_donna": 0.8}).word.id == "ei_alfred"


def test_intervalo_minimo_entre_ativacoes():
    clock = Clock()
    gate = ActivationGate([ALFRED], cooldown_s=2.0, clock=clock)
    assert gate.check({"ei_alfred": 0.9}) is not None
    clock.t += 1.0
    assert gate.check({"ei_alfred": 0.9}) is None and gate.suppressed == 1
    clock.t += 1.1  # 2,1 s depois da primeira
    assert gate.check({"ei_alfred": 0.9}) is not None


def test_ativacao_suprimida_nao_reinicia_o_intervalo():
    clock = Clock()
    gate = ActivationGate([ALFRED], cooldown_s=2.0, clock=clock)
    gate.check({"ei_alfred": 0.9})
    clock.t += 1.5
    gate.check({"ei_alfred": 0.9})  # suprimida
    clock.t += 0.6  # 2,1 s desde a ativação real
    assert gate.check({"ei_alfred": 0.9}) is not None


# ---------- palavra -> personagem ----------


def test_mapeamento_palavra_para_personagem():
    ws = {w.id: w for w in Config().wake.words}
    assert character_for(ws["ei_alfred"]) == "alfred"
    assert character_for(ws["ei_donna"]) == "donna"
    assert character_for(ws["ei_jarbis"]) == "jarbis"
    assert character_for(ws["hey_jarvis_teste"]) == "jarbis"


def test_sem_palavra_ou_personagem_desconhecido_cai_no_padrao():
    assert character_for(None) == "alfred"  # atalho de teclado
    assert character_for(WakeWord("x", "x.onnx", "batman")) == "alfred"
    assert character_for(WakeWord("x", "x.onnx", "Donna")) == "donna"


def test_config_de_chamados_do_toml(tmp_path, monkeypatch):
    f = tmp_path / "fidus.toml"
    f.write_text(
        '[chamados]\nintervalo_s = 3\ncontinuacao_s = 7\nsom_ao_ouvir = true\npersonagem_padrao = "donna"\n'
        '[chamados.palavras.ei_alfred]\nativa = false\n'
        '[chamados.palavras.ei_donna]\nlimiar = 0.8\n'
        '[chamados.palavras.hey_alfred]\nmodelo = "hey_alfred.onnx"\npersonagem = "alfred"\nlimiar = 0.6\n'
    )
    monkeypatch.setenv("FIDUS_CONFIG", str(f))
    monkeypatch.setenv("FIDUS_HOME", str(tmp_path))
    w = load_config().wake
    ids = {x.id: x for x in w.words}
    assert (w.cooldown_s, w.followup_s, w.beep, w.default_character) == (3.0, 7.0, True, "donna")
    assert ids["ei_alfred"].enabled is False and ids["ei_donna"].threshold == 0.8
    assert ids["hey_alfred"].model == "hey_alfred.onnx" and ids["hey_alfred"].enabled
    assert ids["hey_jarvis_teste"].test_only and not ids["hey_jarvis_teste"].enabled  # teste: desligado por padrão


def test_padroes_pedidos():
    w = Config().wake
    assert (w.silence_s, w.max_record_s, w.followup_s, w.beep, w.cooldown_s, w.ring_s) == (1.2, 15.0, 5.0, False, 2.0, 2.0)


# ---------- carga dos modelos ----------


class FakeModel:
    instances = []

    def __init__(self, wakeword_models, inference_framework):
        FakeModel.instances.append((list(wakeword_models), inference_framework))
        if any(p.endswith("corrompido.onnx") for p in wakeword_models):
            raise ValueError("arquivo corrompido")
        self.resets = 0

    def predict(self, frame):
        return {"ei_alfred": np.float32(0.1)}

    def reset(self):
        self.resets += 1


@pytest.fixture
def models_dir(config, tmp_path):
    d = tmp_path / "models"
    d.mkdir()
    config.wake.models_dir = d
    return d


def load(config, include_test=False):
    out = []
    det, active = load_detector(config, ActionLog(config.log_path), include_test, out.append, FakeModel, lambda names: None)
    return det, active, out


def events(config):
    return [json.loads(l) for l in config.log_path.read_text().splitlines()]


def test_modelo_ausente_desativa_so_aquela_palavra_e_avisa_no_log(config, models_dir):
    (models_dir / "ei_alfred.onnx").write_bytes(b"x")  # donna e jarbis não existem
    det, active, out = load(config)
    assert [w.id for w in active] == ["ei_alfred"]
    off = [e for e in events(config) if e["type"] == "wakeword_desativada"]
    assert {e["palavra"] for e in off} == {"ei_donna", "ei_jarbis"}
    assert any("push-to-talk continua" in m for m in out)


def test_sem_nenhum_modelo_nao_ha_detector_mas_nao_quebra(config, models_dir):
    det, active, out = load(config)
    assert det is None and active == []


def test_modelo_quebrado_desativa_so_ele(config, models_dir):
    (models_dir / "ei_alfred.onnx").write_bytes(b"x")
    (models_dir / "ei_donna.onnx").write_bytes(b"x")
    config.wake.words[1].model = "corrompido.onnx"
    (models_dir / "corrompido.onnx").write_bytes(b"x")
    det, active, out = load(config)
    assert [w.id for w in active] == ["ei_alfred"]
    assert any(e["type"] == "wakeword_desativada" and e["palavra"] == "ei_donna" for e in events(config))


def test_modelo_de_teste_so_entra_quando_pedido_e_vai_com_nome_e_onnx(config, models_dir):
    det, active, _ = load(config, include_test=False)
    assert det is None
    FakeModel.instances.clear()
    det, active, _ = load(config, include_test=True)
    assert [w.id for w in active] == ["hey_jarvis_teste"] and active[0].test_only
    assert FakeModel.instances[-1] == (["hey_jarvis"], "onnx")  # nome do modelo pronto + runtime ONNX


def test_varios_modelos_ao_mesmo_tempo_usam_caminho_do_arquivo(config, models_dir):
    for n in ("ei_alfred", "ei_donna", "ei_jarbis"):
        (models_dir / f"{n}.onnx").write_bytes(b"x")
    FakeModel.instances.clear()
    det, active, _ = load(config)
    paths, fw = FakeModel.instances[-1]
    assert len(active) == 3 and fw == "onnx"
    assert paths == [str(models_dir / f"{n}.onnx") for n in ("ei_alfred", "ei_donna", "ei_jarbis")]
    assert det.predict(np.zeros(1280, dtype=np.int16)) == {"ei_alfred": pytest.approx(0.1)}


# ---------- runner ----------


class FakeDetector:
    def __init__(self, scores):
        self.scores, self.resets, self.calls = scores, 0, 0

    def predict(self, frame):
        self.calls += 1
        return self.scores

    def reset(self):
        self.resets += 1


class FakeManager:
    def __init__(self):
        self.subs = []

    def subscribe(self, cb):
        self.subs.append(cb)


def test_runner_ativa_zera_o_detector_e_respeita_o_intervalo():
    got = []
    det = FakeDetector({"ei_alfred": 0.9})
    runner = DetectorRunner(FakeManager(), det, ActivationGate([ALFRED], 60.0), got.append)
    blk = np.zeros(1280, dtype=np.int16)
    for _ in range(3):
        runner.process(blk)
    assert len(got) == 1 and got[0].word.id == "ei_alfred"  # as outras 2 caíram no intervalo
    assert det.resets == 1 and runner.frames == 3 and runner.gate.suppressed == 2


def test_runner_em_thread_processa_tudo_e_flush_descarta():
    got = []
    det = FakeDetector({"ei_alfred": 0.0})
    m = FakeManager()
    runner = DetectorRunner(m, det, ActivationGate([ALFRED], 1), got.append)
    runner.start()
    for _ in range(20):
        m.subs[0](np.zeros(1280, dtype=np.int16))
    runner.stop()
    assert det.calls == 20
    runner._q.put(np.zeros(1280, dtype=np.int16))
    runner.flush()
    assert runner._q.empty() and det.resets >= 1


def test_runner_nao_trava_o_fluxo_quando_a_fila_enche():
    runner = DetectorRunner(FakeManager(), FakeDetector({}), ActivationGate([ALFRED], 1), lambda a: None)
    for _ in range(80):  # thread não iniciada: a fila (50) enche
        runner._push(np.zeros(1280, dtype=np.int16))
    assert runner.dropped == 30


# ---------- openWakeWord de verdade (pulado se os modelos não estiverem baixados) ----------


def test_openwakeword_real_com_modelo_pronto_em_silencio():
    openwakeword = pytest.importorskip("openwakeword")
    from pathlib import Path

    base = Path(openwakeword.__file__).parent / "resources" / "models"
    if not all((base / n).exists() for n in ("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx")):
        pytest.skip("modelos do openWakeWord não baixados")
    det = OpenWakeWordDetector([WakeWord("hey_jarvis_teste", "hey_jarvis", "jarbis")], base)
    scores = {}
    for _ in range(30):
        scores = det.predict(np.zeros(1280, dtype=np.int16))
    assert set(scores) == {"hey_jarvis"} and scores["hey_jarvis"] < 0.1
    det.reset()
