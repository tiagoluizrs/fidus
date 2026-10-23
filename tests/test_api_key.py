"""Teste real: confirma que a chave da Anthropic funciona. Pula se não houver chave."""

import pytest

from fidus.core.config import load_config
from fidus.core.providers.anthropic import AnthropicProvider
from fidus.core.secrets import get_anthropic_key


def test_chave_anthropic_funciona():
    load_config()  # carrega o .env
    if not get_anthropic_key():
        pytest.skip("ANTHROPIC_API_KEY não definida")
    cfg = load_config()
    assert AnthropicProvider(cfg.model).check_key().strip()
