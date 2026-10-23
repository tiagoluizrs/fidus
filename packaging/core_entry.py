"""Ponto de entrada do núcleo empacotado (fidus-core.exe). O app Electron chama: fidus-core daemon --stdin-watch."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # necessário em executáveis congelados no Windows
    from fidus.__main__ import main

    sys.exit(main())
