"""Import enxuto do openWakeWord.

O pacote importa scikit-learn e scipy só para treinar "verificadores" de voz, recurso que o Fidus não usa.
Isso custa ~100 MB de memória em repouso, então o módulo de treino é trocado por um substituto vazio.
"""

from __future__ import annotations

import sys
import types


def import_openwakeword():
    name = "openwakeword.custom_verifier_model"
    if "openwakeword" not in sys.modules and name not in sys.modules:
        stub = types.ModuleType(name)

        def train_custom_verifier(*args, **kwargs):
            raise RuntimeError("Verificadores personalizados não são usados no Fidus.")

        stub.train_custom_verifier = train_custom_verifier
        sys.modules[name] = stub
    import openwakeword

    return openwakeword
