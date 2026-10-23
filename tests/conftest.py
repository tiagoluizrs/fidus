import pytest

from fidus.core.config import Config
from fidus.core.providers.base import Response


@pytest.fixture
def config(tmp_path):
    allowed = tmp_path / "liberada"
    allowed.mkdir()
    return Config(allowed_folders=[allowed], data_dir=tmp_path / "data")


class FakeProvider:
    """Responde com uma sequência pré-definida de Response e guarda o que recebeu."""

    def __init__(self, responses: list[Response]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, system, messages, tools):
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        return self.responses.pop(0)
