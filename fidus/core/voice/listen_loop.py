"""Laço completo: chamado ou atalho -> grava até o silêncio -> transcreve -> orquestrador -> fala -> continuação.

Estados: SLEEPING (escuta passiva) -> RECORDING -> PROCESSING -> FOLLOWUP -> SLEEPING.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections.abc import Callable
from enum import Enum

from ..actionlog import ActionLog
from ..config import Config
from .audio_manager import SAMPLE_RATE, to_float32
from .characters import character_for
from ..bridge.events import NullEvents, ui_state
from .hotkey import GlobalKeyListener, PushToTalk, ToggleHotkey, parse_hotkey
from .indicator import Indicator
from .vad import SilenceEndpointer, capture_utterance
from .wakeword import Activation


class State(str, Enum):
    SLEEPING = "sleeping"
    RECORDING = "recording"
    PROCESSING = "processing"
    FOLLOWUP = "followup"


def beep() -> None:
    """Sinal sonoro de 'estou ouvindo'. winsound só existe no Windows."""
    try:
        import winsound

        winsound.Beep(880, 120)
    except ImportError:
        sys.stdout.write("\a")
        sys.stdout.flush()


class ListenLoop:
    def __init__(
        self,
        config: Config,
        manager,
        runner,
        vad,
        handler,
        tts,
        indicator: Indicator,
        log: ActionLog,
        out: Callable[[str], None] = print,
        clock: Callable[[], float] = time.perf_counter,
        beep_fn: Callable[[], None] = beep,
        speaker=None,
        events=None,
    ):
        self.speaker = speaker  # PersonaSpeaker (opcional)
        self.ui = events or NullEvents()  # interface (opcional): estado, personagem... (self.events é a fila do laço)
        self.calls_enabled = True  # "Escutar chamados" (a bandeja liga e desliga)
        self.paused_until: float | None = None
        self._pause_timer: threading.Timer | None = None
        self._stopping = False
        self._last_ui: tuple | None = None
        self.config, self.manager, self.runner, self.vad = config, manager, runner, vad
        self.handler, self.tts, self.indicator, self.log = handler, tts, indicator, log
        self.out, self.clock, self.beep = out, clock, beep_fn
        self.state = State.SLEEPING
        self.events: queue.Queue = queue.Queue()
        self._ptt_capture = None
        self._abort = threading.Event()

    # ---- entradas (podem vir de outros threads) ----

    def on_activation(self, act: Activation) -> None:
        self.events.put(("wake", act))

    def ptt_down(self) -> None:
        if not self.config.voice.hotkey_enabled:
            return  # "Aceitar também o atalho" desligado
        if self.manager.muted:
            self.out("Microfone silenciado: o atalho foi ignorado.")
            return
        self.tts.stop()  # falar por cima interrompe a resposta
        self.manager.pause_detection()
        if self.state in (State.RECORDING, State.FOLLOWUP):
            self._abort.set()  # o atalho assume a gravação em curso
        self._ptt_capture = self.manager.open_capture(self.config.wake.preroll_ptt_s)
        self.indicator.show("recording")
        self._emit_state("listening")

    def ptt_up(self) -> None:
        self.events.put(("ptt_up", self.clock()))

    def toggle_mute(self) -> None:
        if self.manager.muted:
            self.manager.unmute()
            self.runner and self.runner.flush()
            self._show()
        else:
            self._abort.set()
            self._ptt_capture = None
            self.manager.mute()
            self.indicator.show("muted")
            self._emit_state()

    # ---- controles externos (bandeja e interface; podem vir de outros threads) ----

    def set_muted(self, value: bool) -> None:
        if bool(value) != self.manager.muted:
            self.toggle_mute()

    def set_calls_enabled(self, value: bool) -> None:
        """Liga/desliga a escuta por chamados ("Escutar chamados"). O atalho de teclado continua funcionando."""
        self._cancel_pause_timer()
        self.paused_until = None
        self.calls_enabled = bool(value)
        if not value:
            self.manager.pause_detection()
        elif self.state is State.SLEEPING and self._ptt_capture is None:
            self.manager.resume_detection()
            if self.runner:
                self.runner.flush()
        self.ui.emit("calls", enabled=self.calls_enabled, until=self.paused_until)
        self._show()

    def pause_calls(self, minutes: float) -> None:
        """Pausa os chamados por um tempo (ex.: 60 min) e volta sozinho. 0 cancela a pausa."""
        if minutes <= 0:
            self.set_calls_enabled(True)
            return
        self.set_calls_enabled(False)
        self.paused_until = time.time() + minutes * 60
        self._pause_timer = threading.Timer(minutes * 60, lambda: self.set_calls_enabled(True))
        self._pause_timer.daemon = True
        self._pause_timer.start()
        self.ui.emit("calls", enabled=False, until=self.paused_until)

    def _cancel_pause_timer(self) -> None:
        if self._pause_timer:
            self._pause_timer.cancel()
            self._pause_timer = None

    def request_stop(self) -> None:
        self._stopping = True
        self.events.put(("stop",))  # acorda o laço

    # ---- laço principal ----

    def run(self) -> None:
        w = self.config.wake
        self.manager.start()
        if self.runner:
            self.runner.start()
        keys = GlobalKeyListener(
            PushToTalk(parse_hotkey(self.config.voice.hotkey), self.ptt_down, self.ptt_up),
            ToggleHotkey(parse_hotkey(w.mute_hotkey), self.toggle_mute),
        )
        keys.start()
        self.out(f"Segure {self.config.voice.hotkey} para falar; {w.mute_hotkey} silencia/reativa o microfone. Ctrl+C sai.")
        self._sleep()
        try:
            while not self._stopping:
                try:
                    event = self.events.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.dispatch(event)
        except KeyboardInterrupt:
            self.out("\nAté logo.")
        finally:
            keys.stop()
            if self.runner:
                self.runner.stop()
            self.manager.stop()
            self.tts.close()

    def dispatch(self, event: tuple) -> None:
        if event[0] == "wake":
            self._on_wake(event[1])
        elif event[0] == "ptt_up":
            self._on_ptt_up(event[1])

    # ---- transições ----

    def _emit_state(self, override: str | None = None) -> None:
        state = override or ui_state(self.state.value, self.manager.muted)
        key = (state, self.manager.state)
        if key != self._last_ui:
            self._last_ui = key
            self.ui.emit("state", state=state, mic=self.manager.state)

    def _show(self) -> None:
        self._emit_state()
        if self.manager.muted:
            self.indicator.show("muted")
        elif self.state is State.PROCESSING:
            self.indicator.show("paused")
        elif self.state is State.SLEEPING:
            self.indicator.show("passive")
        else:
            self.indicator.show("recording")

    def _sleep(self) -> None:
        self._abort.clear()
        self.state = State.SLEEPING
        if self._ptt_capture is None and self.calls_enabled:  # atalho gravando ou chamados desligados: detecção pausada
            self.manager.resume_detection()
            if self.runner:
                self.runner.flush()
        self._show()
        if self.speaker and self._ptt_capture is None:
            self.speaker.flush_pending()  # guarda no cache o que foi falado sem cache

    def _on_wake(self, act: Activation) -> None:
        if self.state is not State.SLEEPING or self.manager.muted or self._ptt_capture is not None:
            return
        self.state = State.RECORDING
        self.manager.pause_detection()
        character = character_for(act.word, self.config.wake.default_character)
        if self.speaker and self.config.characters.speak_start:
            self.indicator.show("paused")  # enquanto fala, o microfone não grava nada
            self._emit_state("speaking")
            self.speaker.say_moment(character, "inicio", wait=True)  # fala curta, em cache, na voz do personagem
        capture = self.manager.open_capture(self.config.wake.preroll_call_s)
        opened = self.clock()
        if self.config.wake.beep:
            self.beep()
        self.indicator.show("recording")
        self._emit_state()
        self.out(f"Chamado: {act.word.id} -> {character} (pontuação {act.score:.2f})")
        self.log.event(
            "chamado",
            palavra=act.word.id,
            personagem=character,
            pontuacao=round(act.score, 3),
            somente_teste=act.word.test_only,
            deteccao_ate_gravacao_s=round(opened - act.t, 4),
        )
        self._conversation(capture, character)

    def _conversation(self, capture, character: str) -> None:
        w = self.config.wake
        wait = w.wait_speech_s
        while True:
            ep = SilenceEndpointer(w.silence_s, w.max_record_s, wait)
            self.state = State.RECORDING if wait == w.wait_speech_s else State.FOLLOWUP
            self._emit_state()
            audio, reason = capture_utterance(capture, self.vad, ep, self._abort.is_set)
            capture.close()
            if audio is None:
                if reason == "sem_fala":
                    self.out("(sem fala; voltando a dormir)")
                break
            end = self.clock() - (w.silence_s if reason == "silencio" else 0.0)  # fim real da fala
            self.state = State.PROCESSING
            self.indicator.show("paused")
            self._emit_state()
            farewell = self.handler.handle_audio(to_float32(audio), end, character)
            if farewell or self._abort.is_set() or self.manager.muted:
                break  # despedida, atalho ou silêncio: encerra a conversa sem esperar continuação
            wait = w.followup_s  # espera uma continuação sem precisar chamar de novo
            self.state = State.FOLLOWUP
            self.indicator.show("recording")
            self.out(f"(aguardando continuação por {wait:.0f} s)")
            capture = self.manager.open_capture(w.preroll_ptt_s)
        self._sleep()

    def _on_ptt_up(self, t: float) -> None:
        capture, self._ptt_capture = self._ptt_capture, None
        if capture is None:
            return
        audio = capture.drain()[: int(self.config.voice.max_record_s * SAMPLE_RATE)]
        capture.close()
        if len(audio) >= self.config.voice.min_record_s * SAMPLE_RATE and not self.manager.muted:
            self.state = State.PROCESSING
            self.indicator.show("paused")
            self._emit_state()
            self.handler.handle_audio(to_float32(audio), t, self.config.wake.default_character)
        self._sleep()
