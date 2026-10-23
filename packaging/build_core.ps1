# Empacota o núcleo Python em app/resources-core/fidus-core (PyInstaller, onedir). Rode na raiz do repositório.
$ErrorActionPreference = "Stop"
uv sync --group build
uv run pyinstaller packaging/fidus-core.spec --noconfirm --distpath app/resources-core --workpath build/pyinstaller
if (-not (Test-Path app/resources-core/fidus-core/fidus-core.exe)) { throw "fidus-core.exe não foi gerado" }
Write-Host "Núcleo pronto em app/resources-core/fidus-core"
