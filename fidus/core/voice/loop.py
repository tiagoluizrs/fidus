"""Laço de voz: atalho pressionado -> grava -> solta -> transcreve -> orquestrador -> fala."""

from __future__ import annotations

import queue
import time

from ..actionlog import ActionLog
from ..config import Config
from ..metrics import Timings, rss_mb
from .sentences import SentenceSplitter
from .hotkey import GlobalKeyListener, PushToTalk, parse_hotkey

SAMPLE_RATE = 16_000


class VoiceLoop:
    def __init__(self, config: Config, orchestrator, transcriber, tts, recorder, log: ActionLog, out=print):
        self.config, self.orchestrator, self.stt = config, orchestrator, transcriber
        self.tts, self.recorder, self.log, self.out = tts, recorder, log, out

    def handle_audio(self, audio, speech_end: float, personagem: str = "alfred") -> None:
        """Processa uma gravação (já solta o atalho). `speech_end` vem de time.perf_counter()."""
        if len(audio) < self.config.voice.min_record_s * SAMPLE_RATE:
            return  # toque acidental no atalho
        t = Timings(speech_end=speech_end)
        text = self.stt.transcribe(audio)
        t.text_ready = time.perf_counter()
        if not text:
            self.out("(não ouvi nada)")
            return
        self.out(f"você> {text}")

        splitter = SentenceSplitter()
        self.tts.on_start = t.mark_speech_start

        def on_text(chunk: str) -> None:
            t.mark_first_word()
            print(chunk, end="", flush=True)
            for sentence in splitter.feed(chunk):
                self.tts.speak(sentence)  # fala frase a frase, sem esperar o fim da resposta

        print("fidus> ", end="", flush=True)
        try:
            self.orchestrator.run(text, on_text=on_text, personagem_ativo=personagem)
        except Exception as e:
            self.out(f"\nErro: {type(e).__name__}: {e}")
            self.tts.speak("Desculpe, algo deu errado.")
        if (rest := splitter.flush()):
            self.tts.speak(rest)
        print()
        self.tts.wait_idle()
        self.log.event("metricas_pedido", **t.as_log(), rss_mb=rss_mb(), texto_chars=len(text), personagem=personagem)

    def run(self) -> None:
        v = self.config.voice
        self.out(f"Carregando o Whisper '{v.whisper_model}' ({v.compute_type}, {v.device})...")
        self.stt.load()
        self.out(f"Segure {v.hotkey} para falar e solte para enviar. Ctrl+C para sair.")

        pending: queue.Queue = queue.Queue()

        def on_start() -> None:
            try:
                self.tts.stop()  # falar por cima interrompe a resposta
                self.recorder.start()
            except Exception as e:  # uma exceção aqui derrubaria o ouvinte global do teclado
                self.out(f"Não consegui abrir o microfone: {e}")

        def on_stop() -> None:
            end = time.perf_counter()
            try:
                pending.put((self.recorder.stop(), end))
            except Exception as e:
                self.out(f"Erro ao parar a gravação: {e}")

        listener = GlobalKeyListener(PushToTalk(parse_hotkey(v.hotkey), on_start, on_stop))
        listener.start()
        try:
            while True:
                try:
                    audio, end = pending.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    self.handle_audio(audio, end)
                except Exception as e:  # um pedido com erro não encerra o laço
                    self.out(f"Erro: {type(e).__name__}: {e}")
        except KeyboardInterrupt:
            self.out("\nAté logo.")
        finally:
            listener.stop()
            self.tts.close()


def build_voice_loop(config: Config) -> VoiceLoop:
    """Monta os componentes reais. Cada import pesado acontece aqui, não ao importar o módulo."""
    from ..orchestrator import Orchestrator
    from ..permissions import cli_confirmer
    from ..providers import create_provider
    from .audio import Recorder, list_devices, record_until_silence, resolve_device
    from .confirm import VoiceConfirmer
    from .stt import Transcriber
    from .tts import create_tts

    v = config.voice
    log = ActionLog(config.log_path)
    device = resolve_device(v.microphone, list_devices())
    tts = create_tts(v.speech_rate)
    stt = Transcriber(config, log)
    recorder = Recorder(device, v.max_record_s)

    def speak_and_wait(text: str) -> None:
        tts.speak(text)
        tts.wait_idle()

    def listen(timeout: float) -> str | None:
        audio = record_until_silence(device, timeout)
        return stt.transcribe(audio) if audio is not None else None

    confirm = VoiceConfirmer(speak_and_wait, listen, cli_confirmer, v.confirm_timeout_s)
    orchestrator = Orchestrator(config, create_provider(config), confirm, log=log)
    return VoiceLoop(config, orchestrator, stt, tts, recorder, log)
