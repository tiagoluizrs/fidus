"""Push-to-talk: segurar o atalho grava, soltar envia.

A lógica (`PushToTalk`) é pura e testável. `GlobalKeyListener` liga ela ao teclado com o pynput, que usa o
gancho de teclado do Windows e funciona sem administrador (RegisterHotKey não avisa quando a tecla solta).
"""

from __future__ import annotations

from collections.abc import Callable

_ALIASES = {
    "control": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift_l": "shift", "shift_r": "shift",
    "cmd_l": "cmd", "cmd_r": "cmd", "win": "cmd", "windows": "cmd",
    "espaco": "space", "esc": "esc",
}


def normalize(name: str) -> str:
    name = name.strip().lower()
    return _ALIASES.get(name, name)


def parse_hotkey(spec: str) -> frozenset[str]:
    keys = frozenset(normalize(k) for k in spec.split("+") if k.strip())
    if not keys:
        raise ValueError("Atalho vazio. Exemplo: ctrl+alt+space")
    return keys


def key_name(key) -> str | None:
    """Nome normalizado de uma tecla do pynput (por duck typing: `.name` das especiais, `.char` das comuns)."""
    name = getattr(key, "name", None) or getattr(key, "char", None)
    return normalize(name) if name else None


class PushToTalk:
    """Máquina de estados: IDLE -> RECORDING quando o atalho inteiro está pressionado; volta ao soltar qualquer tecla."""

    def __init__(self, combo: frozenset[str], on_start: Callable[[], None], on_stop: Callable[[], None]):
        self.combo, self.on_start, self.on_stop = combo, on_start, on_stop
        self.down: set[str] = set()
        self.recording = False

    def press(self, name: str) -> None:
        self.down.add(name)  # o auto-repeat do teclado repete 'press': conjunto ignora a repetição
        if not self.recording and self.combo <= self.down:
            self.recording = True
            self.on_start()

    def release(self, name: str) -> None:
        self.down.discard(name)
        if self.recording and name in self.combo:
            self.recording = False
            self.on_stop()


class GlobalKeyListener:
    def __init__(self, ptt: PushToTalk):
        self.ptt = ptt
        self._listener = None

    def start(self) -> None:
        from pynput import keyboard  # import preguiçoso (também evita erro em máquina sem tela)

        def on_press(key):
            if (n := key_name(key)):
                self.ptt.press(n)

        def on_release(key):
            if (n := key_name(key)):
                self.ptt.release(n)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
