#!/usr/bin/env sh
# Mesmo build do .ps1, para testar o empacotamento em Linux/macOS (o instalador final é só Windows).
set -eu
uv sync --group build
uv run pyinstaller packaging/fidus-core.spec --noconfirm --distpath app/resources-core --workpath build/pyinstaller
test -x app/resources-core/fidus-core/fidus-core
echo "Núcleo pronto em app/resources-core/fidus-core"
