from fidus.core.permissions import needs_confirmation
from fidus.core.tools.base import Risk, Tool


class T(Tool):
    name = "t"
    description = "d"
    parameters = {"type": "object"}

    def __init__(self, risk, approved=False):
        self.risk = risk
        self._approved = approved

    def preapproved(self, args, config):
        return self._approved


def test_leitura_nao_pergunta(config):
    assert not needs_confirmation(T(Risk.LEITURA), {}, config)


def test_escrita_pergunta(config):
    assert needs_confirmation(T(Risk.ESCRITA), {}, config)


def test_escrita_preaprovada_nao_pergunta(config):
    assert not needs_confirmation(T(Risk.ESCRITA, approved=True), {}, config)


def test_irreversivel_sempre_pergunta_mesmo_preaprovada(config):
    assert needs_confirmation(T(Risk.IRREVERSIVEL, approved=True), {}, config)
