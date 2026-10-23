# PyInstaller (modo onedir): gera dist/fidus-core/fidus-core(.exe) com as bibliotecas ao lado.
# Build: veja packaging/build_core.ps1 (Windows) ou packaging/build_core.sh (teste em Linux).
# Os imports do Fidus são preguiçosos, então o PyInstaller não os enxerga sozinho: coletamos o pacote inteiro.
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = collect_submodules("fidus")
hidden += collect_submodules("keyring.backends")
if sys.platform == "win32":  # voz SAPI (pywin32)
    hidden += ["win32com.client", "pythoncom", "pywintypes"]
hidden += ["sqlcipher3", "websockets.asyncio.server"]

datas = [("../fidus.example.toml", "."), ("../fidus/defaults", "fidus/defaults")]  # personagens padrão (JSON) e exemplo de config
for pkg in ("openwakeword", "faster_whisper", "googleapiclient", "certifi"):
    try:
        datas += collect_data_files(pkg)
    except Exception:  # pacote ausente nesta plataforma
        pass

a = Analysis(
    ["core_entry.py"],
    pathex=[".."],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "sklearn", "scipy.spatial.cKDTree", "tensorflow", "torch"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fidus-core", console=True, upx=False)
# console=True: o app Electron lê a porta e o token pela saída padrão; a janela de console é escondida pelo processo pai.
coll = COLLECT(exe, a.binaries, a.datas, name="fidus-core", upx=False)
