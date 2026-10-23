# Medições

Tudo aqui foi medido em **Linux** (servidor de desenvolvimento, xvfb, sem placa de som). Serve para achar regressões e
dar uma ordem de grandeza; **os números do Windows precisam ser refeitos** (tabela "A medir no Windows" no fim).

## Repouso por 10 minutos: app empacotado + núcleo simulado

Como: `electron-builder --dir` (app empacotado), executado sob `xvfb-run` com `--simulado` e `FIDUS_HOME` temporário.
Amostra a cada 10 s durante 10 min (61 amostras) somando a memória (RSS) e a CPU de todos os processos do app (Electron:
principal, GPU, utilitários + `fidus-core`). Sem janela aberta: só o ícone da bandeja e o núcleo.

| Medida | Resultado |
| --- | --- |
| Processos | 5 (4 do Electron + `fidus-core`) |
| Memória total (RSS somado) | média **264,8 MB**, máxima 264,9 MB (estável, sem crescimento em 10 min) |
| CPU total | média **0,08 % de um núcleo**, máxima 1,0 % (só na partida) |
| Núcleo simulado (`fidus-core`) isolado | ~37 MB |

Observações:

- O RSS somado conta páginas compartilhadas entre os processos do Chromium mais de uma vez, então a memória real é menor.
- Sem vazamento: a curva fica plana em 264,3 a 264,9 MB.
- A janela do anel é criada só durante a conversa e destruída depois (5A), por isso o repouso não a inclui.

## Tamanho do pacote (Linux, sem compressão)

| Item | Tamanho |
| --- | --- |
| App Electron empacotado (pasta completa) | 262 MB (inclui o Chromium) |
| `app.asar` (código e telas do app) | 0,6 MB |
| Núcleo Python congelado (`resources/core`) | 556 MB (numpy, onnxruntime, ctranslate2, Google API, SQLCipher...) |

O instalador NSIS comprime isso; o tamanho do `.exe` só dá para medir no Windows.

## Escuta passiva e voz (medidas nas etapas 2 e 2B, núcleo real)

Do `uv run fidus wake-bench` (modelo real `hey_jarvis`, áudio sintético): detector ~**7,6 % de um núcleo** e ~**105 MB**
(ver README, "Medições da escuta passiva"). O Whisper não pôde ser medido aqui (download bloqueado).

## Estimativa em repouso com tudo ligado (a confirmar)

App (~265 MB somados) + escuta passiva (~105 MB, 1 a 3 modelos) + Whisper `small` carregado (centenas de MB, a medir) =
a ordem de **meio gigabyte ou mais**. Se isso incomodar: Whisper `base` ou carregar o Whisper só quando há chamado
(troca RAM por ~1 s de latência), e as opções de casco menor em `docs/LANCAMENTO.md` (seção 5).

## A medir no Windows (núcleo real, app instalado)

| Medida | Como | Resultado |
| --- | --- | --- |
| RAM em repouso por 10 min (escuta passiva ligada) | Gerenciador de Tarefas > Detalhes, somar `Fidus` + `fidus-core` | _a preencher_ |
| CPU em repouso | idem, coluna CPU média | _a preencher_ |
| RAM com o anel aberto | durante uma conversa | _a preencher_ |
| Tempo de abertura (clique no atalho -> bandeja pronta) | cronômetro | _a preencher_ |
| Tamanho do instalador e instalado | `app\release` e pasta de instalação | _a preencher_ |
| Latência "chamado -> gravação" | evento `chamado` no `actions.log` | _a preencher_ |
