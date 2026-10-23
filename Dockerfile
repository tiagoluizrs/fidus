# Ambiente de DESENVOLVIMENTO e TESTE (Linux). Não roda voz real (microfone, SAPI) nem gera o .exe:
# o .exe é feito no Windows (ver .github/workflows/windows-build.yml e docs/LANCAMENTO.md).
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" \
    FIDUS_HOME=/tmp/fidus-home

# gcc: o pynput puxa o evdev no Linux, que compila na instalação.
# Node 22 (testes do app) + bibliotecas do Electron e Xvfb (tela virtual) + PortAudio (importar sounddevice)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git xvfb xauth libportaudio2 gcc libc6-dev socat \
      libgtk-3-0 libnss3 libasound2 libgbm1 libxss1 libxtst6 libxkbcommon0 libdrm2 libatk-bridge2.0-0 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /work

# Dependências primeiro (cache de camadas)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY app/package.json app/package-lock.json app/
RUN cd app && npm ci

COPY . .
RUN uv sync --frozen

CMD ["bash"]
