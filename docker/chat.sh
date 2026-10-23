#!/usr/bin/env bash
# Conversa por texto com o núcleo REAL (sem simulação). Usado por: docker compose run --rm chat
# O provedor e a chave vêm do que você configurou na tela (docker compose up web).
set -e
# O Fidus só fala com o Ollama em 127.0.0.1 (regra de segurança); encaminhamos essa porta ao container do Ollama.
socat TCP-LISTEN:11434,fork,reuseaddr,bind=127.0.0.1 TCP:${OLLAMA_UPSTREAM:-host.docker.internal:11434} &
exec uv run --frozen fidus "$@"
