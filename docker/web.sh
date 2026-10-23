#!/usr/bin/env bash
# Servidor de teste no navegador com o núcleo REAL (sem áudio). Usado por: docker compose up web
set -e
# O Fidus só fala com o Ollama em 127.0.0.1 (regra de segurança); encaminhamos essa porta ao Ollama do seu PC.
socat TCP-LISTEN:11434,fork,reuseaddr,bind=127.0.0.1 TCP:host.docker.internal:11434 &
cd app
npm run build:renderer
node scripts/build-electron.mjs
exec node dist-electron/webhost.js
