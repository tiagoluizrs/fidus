"""Configuração: variáveis de ambiente (.env em desenvolvimento) + fidus.toml."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TOOL_CALLS = 8

# Apps que abrem sem confirmação (nome falado -> comando do Windows).
DEFAULT_APPS = {
    "bloco de notas": "notepad.exe",
    "calculadora": "calc.exe",
    "paint": "mspaint.exe",
    "explorador de arquivos": "explorer.exe",
}


@dataclass
class VoiceConfig:
    hotkey: str = "ctrl+alt+space"
    microphone: str = ""  # índice ou parte do nome; vazio = padrão do sistema
    whisper_model: str = "small"
    compute_type: str = "int8"
    device: str = "cpu"
    language: str = "pt-BR"
    speech_rate: int = 0  # -10 a 10 (SAPI)
    confirm_timeout_s: float = 8.0
    save_debug_audio: bool = False  # desligado: o áudio fica só na memória
    max_record_s: float = 30.0
    min_record_s: float = 0.3  # gravações menores são descartadas (toque acidental)

    @property
    def whisper_language(self) -> str:
        return self.language.split("-")[0].lower()  # pt-BR -> pt


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class WakeWord:
    """Uma palavra de ativação: id, modelo, personagem chamado e limiar próprio."""

    id: str
    model: str  # arquivo em models/wakewords/ (ex.: ei_alfred.onnx) ou nome de modelo pronto (ex.: hey_jarvis)
    character: str
    threshold: float = 0.5
    enabled: bool = True
    test_only: bool = False  # modelo pronto só para validar o encanamento; não é o chamado de verdade

    @property
    def score_key(self) -> str:
        """Nome com que o openWakeWord devolve a pontuação deste modelo."""
        return Path(self.model).stem


def default_wake_words() -> list[WakeWord]:
    return [
        WakeWord("ei_alfred", "ei_alfred.onnx", "alfred"),
        WakeWord("ei_donna", "ei_donna.onnx", "donna"),
        WakeWord("ei_jarbis", "ei_jarbis.onnx", "jarbis"),
        # SOMENTE TESTE: modelo pronto do openWakeWord (licença CC BY-NC-SA 4.0, uso não comercial).
        WakeWord("hey_jarvis_teste", "hey_jarvis", "jarbis", enabled=False, test_only=True),
    ]


@dataclass
class WakeConfig:
    words: list[WakeWord] = field(default_factory=default_wake_words)
    models_dir: Path = field(default_factory=lambda: PACKAGE_ROOT / "models" / "wakewords")
    cooldown_s: float = 2.0  # intervalo mínimo entre ativações
    silence_s: float = 1.2  # silêncio que encerra a gravação
    max_record_s: float = 15.0
    wait_speech_s: float = 5.0  # após o chamado, quanto esperar o início da fala
    followup_s: float = 5.0  # após a resposta, quanto esperar uma continuação sem chamar de novo
    preroll_call_s: float = 0.0  # áudio anterior ao chamado incluído na gravação (0 = só depois dele)
    preroll_ptt_s: float = 0.5
    beep: bool = False  # sinal sonoro ao começar a ouvir
    mute_hotkey: str = "ctrl+alt+m"
    default_character: str = "alfred"
    vad_threshold: float = 0.5  # fala/silêncio da gravação (Silero)
    ring_s: float = 2.0  # buffer circular de pré-roll, só em memória


@dataclass
class UserConfig:
    name: str = ""
    surname: str = ""


@dataclass
class MemoryConfig:
    ask_before_saving: bool = False  # True: toda lembrança nova pede confirmação
    max_context_chars: int = 1500  # limite do trecho de memória enviado ao modelo em cada pedido
    summarize_after_turns: int = 12  # depois disso a conversa antiga vira um resumo
    keep_turns: int = 6  # turnos recentes mantidos na íntegra
    encrypt: str = "auto"  # auto | sim | nao (SQLCipher)


@dataclass
class CharactersConfig:
    speak_start: bool = True  # fala curta pré-gravada ao ser chamado
    speak_farewell: bool = True


@dataclass
class AccountsConfig:
    calendar: str = "google"  # qual serviço está por trás de cada interface
    email: str = "gmail"
    chat: str = "slack"
    google_calendar_write: bool = False  # escrita liberada por serviço (criar/alterar eventos)
    gmail_drafts: bool = False  # criar rascunhos (o escopo do Gmail para isso também permite enviar; o Fidus nunca envia)
    slack_channels: list[str] = field(default_factory=list)  # só estes canais/conversas (nome ou id)
    slack_write: bool = False  # responder em canais permitidos (sempre com confirmação)


@dataclass
class LimitsConfig:
    """Quanto de conteúdo externo pode ir ao modelo."""

    item_chars: int = 600  # por e-mail/mensagem/evento
    max_items: int = 10
    request_chars: int = 4000  # por resultado de ferramenta


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    allowed_folders: list[Path] = field(default_factory=list)
    allowed_apps: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_APPS))
    data_dir: Path = field(default_factory=lambda: Path.home() / ".fidus")
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)
    user: UserConfig = field(default_factory=UserConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    characters: CharactersConfig = field(default_factory=CharactersConfig)
    accounts: AccountsConfig = field(default_factory=AccountsConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)

    @property
    def debug_audio_dir(self) -> Path:
        return self.data_dir / "debug_audio"

    @property
    def characters_dir(self) -> Path:
        return self.data_dir / "characters"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memoria"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "fidus.db"

    @property
    def speech_cache_dir(self) -> Path:
        return self.data_dir / "speech_cache"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "actions.log"

    @property
    def google_credentials_path(self) -> Path:
        return self.data_dir / "credentials.json"

    @property
    def google_token_path(self) -> Path:
        return self.data_dir / "token.json"


def _find_config_file(data_dir: Path) -> Path | None:
    explicit = os.environ.get("FIDUS_CONFIG")
    candidates = [Path(explicit)] if explicit else [Path("fidus.toml"), data_dir / "fidus.toml"]
    return next((p for p in candidates if p.is_file()), None)


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config() -> Config:
    from dotenv import load_dotenv  # só desenvolvimento; em produção a chave vem do keyring

    load_dotenv()
    cfg = Config(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        data_dir=Path(os.environ.get("FIDUS_HOME", Path.home() / ".fidus")),
    )
    data: dict = {}
    path = _find_config_file(cfg.data_dir)
    if path is not None:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    if cfg.settings_path.is_file():  # edições feitas pelo próprio Fidus (CLI/interface) valem sobre o fidus.toml
        data = _deep_merge(data, json.loads(cfg.settings_path.read_text(encoding="utf-8")))
    cfg.max_tool_calls = int(data.get("geral", {}).get("max_chamadas_ferramenta", cfg.max_tool_calls))
    folders = data.get("arquivos", {}).get("pastas_liberadas", [])
    cfg.allowed_folders = [Path(f).expanduser().resolve() for f in folders]
    cfg.allowed_apps.update({k.lower(): v for k, v in data.get("apps", {}).get("permitidos", {}).items()})
    _apply_voice(cfg.voice, data.get("voz", {}))
    _apply_wake(cfg.wake, data.get("chamados", {}))
    _apply_extras(cfg, data)
    return cfg


def _apply_extras(cfg: Config, data: dict) -> None:
    u = data.get("usuario", {})
    cfg.user.name = str(u.get("nome", cfg.user.name)).strip()
    cfg.user.surname = str(u.get("sobrenome", cfg.user.surname)).strip()
    m, mc = data.get("memoria", {}), cfg.memory
    mc.ask_before_saving = bool(m.get("perguntar_antes_de_guardar", mc.ask_before_saving))
    mc.max_context_chars = int(m.get("max_contexto_chars", mc.max_context_chars))
    mc.summarize_after_turns = int(m.get("resumir_apos_turnos", mc.summarize_after_turns))
    mc.keep_turns = int(m.get("turnos_recentes", mc.keep_turns))
    mc.encrypt = str(m.get("criptografar", mc.encrypt)).lower()
    c = data.get("personagens", {})
    cfg.characters.speak_start = bool(c.get("falar_inicio", cfg.characters.speak_start))
    cfg.characters.speak_farewell = bool(c.get("falar_despedida", cfg.characters.speak_farewell))
    a, ac = data.get("contas", {}), cfg.accounts
    ac.calendar, ac.email, ac.chat = (str(a.get(k, getattr(ac, v))) for k, v in (("agenda", "calendar"), ("email", "email"), ("chat", "chat")))
    g, sl = a.get("google", {}), a.get("slack", {})
    ac.google_calendar_write = bool(g.get("agenda_escrita", ac.google_calendar_write))
    ac.gmail_drafts = bool(g.get("gmail_rascunhos", ac.gmail_drafts))
    ac.slack_channels = [str(x).lstrip("#") for x in sl.get("canais_permitidos", ac.slack_channels)]
    ac.slack_write = bool(sl.get("escrita", ac.slack_write))
    lim, lc = data.get("limites", {}), cfg.limits
    lc.item_chars = int(lim.get("item_chars", lc.item_chars))
    lc.max_items = int(lim.get("max_itens", lc.max_items))
    lc.request_chars = int(lim.get("pedido_chars", lc.request_chars))


def _apply_voice(v: VoiceConfig, d: dict) -> None:
    v.hotkey = str(d.get("atalho", v.hotkey))
    v.microphone = str(d.get("microfone", v.microphone))
    v.whisper_model = str(d.get("modelo_whisper", v.whisper_model))
    v.compute_type = str(d.get("compute_type", v.compute_type))
    v.device = str(d.get("dispositivo", v.device))
    v.language = str(d.get("idioma", v.language))
    v.speech_rate = max(-10, min(10, int(d.get("velocidade_voz", v.speech_rate))))
    v.confirm_timeout_s = float(d.get("tempo_confirmacao_s", v.confirm_timeout_s))
    v.save_debug_audio = bool(d.get("salvar_audio_debug", v.save_debug_audio))


def _apply_wake(w: WakeConfig, d: dict) -> None:
    w.cooldown_s = float(d.get("intervalo_s", w.cooldown_s))
    w.silence_s = float(d.get("silencio_fim_s", w.silence_s))
    w.max_record_s = float(d.get("max_gravacao_s", w.max_record_s))
    w.wait_speech_s = float(d.get("esperar_fala_s", w.wait_speech_s))
    w.followup_s = float(d.get("continuacao_s", w.followup_s))
    w.preroll_call_s = float(d.get("preroll_chamado_s", w.preroll_call_s))
    w.preroll_ptt_s = float(d.get("preroll_atalho_s", w.preroll_ptt_s))
    w.beep = bool(d.get("som_ao_ouvir", w.beep))
    w.mute_hotkey = str(d.get("atalho_silenciar", w.mute_hotkey))
    w.default_character = str(d.get("personagem_padrao", w.default_character)).lower()
    w.vad_threshold = float(d.get("limiar_vad", w.vad_threshold))
    if "pasta_modelos" in d:
        w.models_dir = Path(d["pasta_modelos"]).expanduser().resolve()
    by_id = {x.id: x for x in w.words}
    for wid, wd in d.get("palavras", {}).items():
        word = by_id.get(wid) or WakeWord(wid, wd.get("modelo", f"{wid}.onnx"), wd.get("personagem", w.default_character))
        word.model = str(wd.get("modelo", word.model))
        word.character = str(wd.get("personagem", word.character)).lower()
        word.threshold = float(wd.get("limiar", word.threshold))
        word.enabled = bool(wd.get("ativa", word.enabled))
        word.test_only = bool(wd.get("somente_teste", word.test_only))
        by_id[wid] = word
    w.words = list(by_id.values())
