import sys
import types

from fidus.core import secrets


def _fake_keyring(monkeypatch, value=None, boom=False):
    mod = types.ModuleType("keyring")

    def get_password(service, name):
        if boom:
            raise RuntimeError("sem backend")
        assert service == "fidus"
        return value

    mod.get_password = get_password
    monkeypatch.setitem(sys.modules, "keyring", mod)


def test_keyring_tem_prioridade(monkeypatch):
    _fake_keyring(monkeypatch, "do-cofre")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-env")
    assert secrets.get_anthropic_key() == "do-cofre"


def test_cai_no_env_quando_keyring_vazio_ou_quebrado(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-env")
    _fake_keyring(monkeypatch, None)
    assert secrets.get_anthropic_key() == "do-env"
    _fake_keyring(monkeypatch, boom=True)
    assert secrets.get_anthropic_key() == "do-env"


def test_sem_chave(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _fake_keyring(monkeypatch, None)
    assert secrets.get_anthropic_key() is None
