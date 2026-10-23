"""Monta os componentes reais dos comandos `listen`, `wake-test` e `wake-bench`."""

from __future__ import annotations

import time
from collections.abc import Callable

from ..actionlog import ActionLog
from ..config import Config
from .audio_manager import AudioManager


def make_manager(config: Config, stream_factory=None) -> AudioManager:
    from .audio import list_devices, resolve_device

    device = None if stream_factory else resolve_device(config.voice.microphone, list_devices())
    return AudioManager(device, config.wake.ring_s, stream_factory)


def build_listen_loop(config: Config, include_test: bool = False, events=None, broker_events=None):
    from ..assistant import build_assistant, build_speaker
    from ..bridge.confirm import ConfirmBroker
    from ..bridge.events import NullEvents
    from ..permissions import cli_confirmer
    from .audio_manager import to_float32
    from .confirm import VoiceConfirmer
    from .indicator import Indicator
    from .listen_loop import ListenLoop
    from .loop import VoiceLoop
    from .stt import Transcriber
    from .tts import TTSManager
    from .vad import SilenceEndpointer, capture_utterance, load_vad
    from .wakeword import ActivationGate, DetectorRunner, load_detector

    log = ActionLog(config.log_path, config)
    wake = config.wake
    manager = make_manager(config)
    ui = events or NullEvents()  # interface (Electron), se houver
    if events is not None:  # o anel reage ao nível do microfone, mas só enquanto há interface conectada
        manager.on_level = lambda values: ui.emit("level", values=values)
        manager.level_enabled = lambda: ui.has_clients
    broker = ConfirmBroker(broker_events) if broker_events is not None else None
    tts = TTSManager(config.voice.speech_rate)
    stt = Transcriber(config, log)
    vad = load_vad(wake.vad_threshold)
    indicator = Indicator()

    detector, active = load_detector(config, log, include_test)
    runner = None
    loop_ref: dict = {}
    if detector:
        gate = ActivationGate(active, wake.cooldown_s)
        runner = DetectorRunner(manager, detector, gate, lambda act: loop_ref["loop"].on_activation(act))
        names = ", ".join(w.id + (" (SOMENTE TESTE)" if w.test_only else "") for w in active)
        print(f"Palavras ativas: {names}")
    else:
        print("Nenhuma palavra de ativação ativa; só o push-to-talk. Veja docs/WAKEWORDS.md.")

    def speak_and_wait(text: str) -> None:
        if not config.voice.speak_replies:  # "Responder em voz alta" desligado: a pergunta vai só para a tela
            return
        tts.speak(text)
        tts.wait_idle()

    def listen(timeout: float) -> str | None:
        # a resposta "sim/não" usa o MESMO fluxo de microfone, por uma gravação temporária
        cap = manager.open_capture(0.0)
        try:
            audio, _ = capture_utterance(cap, vad, SilenceEndpointer(0.8, timeout + 5, timeout), broker.is_answered if broker else (lambda: False))
        finally:
            cap.close()
        return stt.transcribe(to_float32(audio)) if audio is not None else None

    speaker_ref: dict = {}
    voice_confirm = VoiceConfirmer(
        speak_and_wait, listen, broker.wait_ui if broker else cli_confirmer, config.voice.confirm_timeout_s,
        intro=lambda: speaker_ref["s"].text_for(orchestrator.personagem_ativo, "confirmar"),
    )
    # com interface: o pedido aparece na tela e é falado; vale o primeiro "sim/não" (clique ou voz)
    confirm = (lambda prompt: broker.run(prompt, voice_confirm)) if broker else voice_confirm
    orchestrator, persona, _ = build_assistant(config, confirm, log=log)
    speaker = build_speaker(config, persona, tts)
    speaker_ref["s"] = speaker
    handler = VoiceLoop(config, orchestrator, stt, tts, None, log, speaker=speaker, events=ui)
    loop = ListenLoop(config, manager, runner, vad, handler, tts, indicator, log, speaker=speaker, events=ui)
    loop.broker = broker
    loop_ref["loop"] = loop
    stt.load()  # o Whisper carrega uma vez, antes de começar a escutar
    if config.characters.speak_start:
        print("Preparando as falas de início (só demora na primeira vez)...")
        speaker.warm_up()
    return loop


def run_wake_test(config: Config, include_test: bool = False, out: Callable[[str], None] = print, stream_factory=None) -> int:
    """Mostra em tempo real a pontuação de cada palavra, para ajustar os limiares."""
    from .indicator import Indicator
    from .wakeword import ActivationGate, DetectorRunner, load_detector

    log = ActionLog(config.log_path)
    detector, active = load_detector(config, log, include_test, out)
    if not detector:
        out("Nenhuma palavra ativa. Coloque os modelos em models/wakewords/ ou use --somente-teste (veja docs/WAKEWORDS.md).")
        return 1
    manager = make_manager(config, stream_factory)
    gate = ActivationGate(active, config.wake.cooldown_s)
    peak = {w.id: 0.0 for w in active}
    hits = {w.id: 0 for w in active}
    last_print = [0.0]

    def on_scores(scores: dict) -> None:
        for w in active:
            peak[w.id] = max(peak[w.id], scores.get(w.score_key, 0.0))
        now = time.monotonic()
        if now - last_print[0] >= 0.1:
            last_print[0] = now
            cells = []
            for w in active:
                s = scores.get(w.score_key, 0.0)
                mark = "*" if s >= w.threshold else " "
                cells.append(f"{w.id} {s:4.2f}/{w.threshold:.2f}{mark}")
            print("\r" + " | ".join(cells) + "   ", end="", flush=True)

    def on_activation(act) -> None:
        hits[act.word.id] += 1
        print(f"\n>>> ATIVOU: {act.word.id} (pontuação {act.score:.2f}) -> {act.word.character}")

    runner = DetectorRunner(manager, detector, gate, on_activation, on_scores)
    Indicator(out).show("passive")
    out("Fale perto do microfone. Formato: pontuação/limiar; * = acima do limiar. Ctrl+C para ver o resumo.")
    runner.start()
    manager.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()
        runner.stop()
    out("\n\nResumo (pico de pontuação, ativações, limiar atual):")
    for w in active:
        out(f"  {w.id:<18} pico {peak[w.id]:.2f}   ativações {hits[w.id]}   limiar {w.threshold:.2f}")
    out("Dica: o limiar deve ficar acima do pico do ruído/TV e abaixo do pico da sua voz chamando.")
    return 0
