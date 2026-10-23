import numpy as np

from fidus.core.voice.audio_manager import BLOCK, AudioManager, to_float32


class FakeStream:
    def __init__(self, cb):
        self.cb, self.started, self.closed = cb, False, False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


def blk(v=0):
    return np.full(BLOCK, v, dtype=np.int16)


def make(ring_s=2.0):
    states, streams = [], []

    def factory(cb):
        streams.append(FakeStream(cb))
        return streams[-1]

    m = AudioManager(stream_factory=factory, ring_s=ring_s, on_state=states.append)
    m.start()
    return m, states, streams


def test_um_unico_fluxo_para_detector_e_gravacao():
    m, _, streams = make()
    got = []
    m.subscribe(got.append)
    cap = m.open_capture()
    m.start()  # chamar de novo não abre outro fluxo
    m.feed(blk(1))
    assert len(streams) == 1 and len(got) == 1 and cap.queue.qsize() == 1


def test_buffer_circular_de_2s_guarda_so_os_ultimos_blocos():
    m, _, _ = make(ring_s=2.0)
    for i in range(40):  # 3,2 s de áudio
        m.feed(blk(i))
    assert len(m._ring) == 25  # 2 s = 25 blocos de 80 ms
    assert m._ring[0][0] == 15 and m._ring[-1][0] == 39  # os mais antigos saíram


def test_pre_roll_entrega_o_que_veio_antes_da_gravacao():
    m, _, _ = make()
    for i in range(20):
        m.feed(blk(i))
    cap = m.open_capture(preroll_s=0.5)  # 0,5 s = 6 blocos
    audio = cap.drain()
    assert len(audio) == 6 * BLOCK and audio[0] == 14 and audio[-1] == 19
    m.feed(blk(99))  # e a partir daí, os blocos novos
    assert cap.drain()[0] == 99


def test_sem_pre_roll_so_recebe_o_que_vem_depois():
    m, _, _ = make()
    m.feed(blk(1))
    cap = m.open_capture(0.0)
    assert len(cap.drain()) == 0
    m.feed(blk(2))
    assert cap.drain()[0] == 2


def test_pausar_a_deteccao_nao_para_a_gravacao():
    m, _, _ = make()
    got = []
    m.subscribe(got.append)
    cap = m.open_capture()
    m.pause_detection()
    m.feed(blk(1))
    assert got == [] and cap.queue.qsize() == 1
    m.resume_detection()
    m.feed(blk(2))
    assert len(got) == 1


def test_estados_do_microfone():
    m, states, _ = make()
    assert m.state == "passive"
    cap = m.open_capture()
    assert m.state == "recording"
    cap.close()
    m.pause_detection()
    assert m.state == "paused"
    m.resume_detection()
    m.mute()
    assert m.state == "muted"
    m.unmute()
    assert m.state == "passive"
    assert states[0] == "passive" and "muted" in states and states[-1] == "passive"


def test_silenciar_fecha_o_microfone_e_descarta_tudo():
    m, _, streams = make()
    got = []
    m.subscribe(got.append)
    m.feed(blk(1))
    cap = m.open_capture()
    m.mute()
    assert streams[0].closed and cap.closed and len(m._ring) == 0
    m.feed(blk(2))  # mesmo que chegue algo, é ignorado
    assert len(got) == 1 and cap.queue.empty()
    m.unmute()
    assert len(streams) == 2  # abriu um fluxo novo


def test_to_float32_normaliza():
    a = to_float32(np.array([0, 16384, -32768], dtype=np.int16))
    assert a.dtype == np.float32 and list(a) == [0.0, 0.5, -1.0]
