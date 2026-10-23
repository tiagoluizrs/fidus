# CONTEXT: o que foi feito (Etapa 1 e Etapa 2)

Registro detalhado da sessão de desenvolvimento. Visão geral do produto em `PROJETO.md`; instalação e uso em `README.md`.

## Pedido

Construir **somente a Etapa 1** do roteiro: núcleo em Python no terminal (texto -> Claude -> ferramentas -> resposta). Sem interface, voz ou Electron. Alvo: Windows 10/11 com PowerShell, Python gerenciado pelo uv.

## Decisões tomadas

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Python | Etapa 1 usou **3.15**. **Na Etapa 2 voltou para 3.12** (decisão do usuário, ver Etapa 2) | A 3.15 não tem wheel de `ctranslate2` (faster-whisper), `onnxruntime` nem `pywin32`. |
| Modelo | `CLAUDE_MODEL`, padrão `claude-sonnet-5-5` | Pedido. |
| `abrir_app` | Risco **escrita**. Apps da lista do `fidus.toml` abrem sem confirmação; qualquer outro pede `[s/n]` | O usuário não respondeu à pergunta; adotei o padrão que propus. |
| Demonstração de confirmação | Sem ferramenta extra. Usa-se `abre o regedit` (fora da lista) | O pedido era de três ferramentas. |
| Google OAuth | `credentials.json` e `token.json` em `~/.fidus/` (ou `FIDUS_HOME`); escopo só `calendar.readonly` | Token no keyring fica para a etapa seguinte. |
| Dados locais | `~/.fidus/` (`actions.log`, credenciais, token) | Fora do repositório, sem risco de commitar segredos. |
| Streaming | Não implementado; a interface do provedor usa `complete()` | Não exigido na Etapa 1. |

## Fontes acessadas

- `PROJETO.md` (anexo): copiado para a raiz do repositório.
- Documento do projeto no Claude (artifact `af5f7cf5-...`): conferido; mesmo conteúdo do `PROJETO.md`.
- Canvas de design (artifact `UynS7T7WVeX8VStgdSNK77`): acessado pela ferramenta de Artifacts, sem abrir por URL web. As 26 telas (claro e escuro) e o `canvas.json` foram copiados para `docs/design/` como **referência da Etapa 5**. Nada delas é usado no código.

## Arquivos criados

### Raiz
- `pyproject.toml`: projeto `fidus` 0.1.0, `requires-python >=3.15`, dependências `anthropic`, `python-dotenv`, `keyring`, `google-api-python-client`, `google-auth-oauthlib`; grupo dev com `pytest`; script `fidus`; build com hatchling.
- `.python-version` (`3.15`) e `uv.lock` (55 pacotes).
- `.env.example`, `fidus.example.toml`.
- `.gitignore`: acrescentados `.env`, `fidus.toml`, `.fidus/`, `credentials.json`, `token.json`.
- `README.md`, `PROJETO.md`, `CONTEXT.md`.

### `fidus/__main__.py`
CLI: `uv run fidus` (conversa), `uv run fidus "pedido"` (comando único), `--check-key` (testa a chave). Em erro de uma rodada da conversa, imprime e continua.

### `fidus/core/`
- `config.py`: `Config` com modelo, limite (padrão 8), pastas liberadas, apps liberados e pasta de dados. Lê `.env` (python-dotenv) e `fidus.toml` (busca `FIDUS_CONFIG`, `./fidus.toml`, `~/.fidus/fidus.toml`).
- `secrets.py`: chave procurada primeiro no keyring (serviço `fidus`), depois no ambiente/.env. Qualquer erro do keyring cai no ambiente (ex.: Linux sem cofre). `set_secret` grava no cofre.
- `orchestrator.py`: laço texto -> provedor -> ferramentas -> resposta. Detalhes:
  - o limite de chamadas vale **por comando**; ao estourar, as chamadas excedentes recebem erro, o evento é logado como `bloqueado_limite` e é feita uma última chamada **sem ferramentas** para o modelo explicar;
  - ferramenta desconhecida, negação do usuário e exceções viram resultado de erro para o modelo, sem derrubar o laço;
  - saída de ferramenta marcada como externa é embrulhada por `untrusted.wrap`;
  - o prompt de sistema (português) ensina a tratar `<dado_externo>` como dado e a aceitar a negação de uma ação.
- `permissions.py`: `needs_confirmation` (leitura: não; escrita: sim, salvo `preapproved`; irreversível: **sempre**, nenhuma ferramenta pode dispensar) e `ask`/`cli_confirmer` (`[s/n]`).
- `untrusted.py`: `wrap(origem, texto)` delimita em `<dado_externo origem="...">`; qualquer `<dado_externo`/`</dado_externo` dentro do texto é substituído por `[tag removida]`.
- `actionlog.py`: log JSON por linha com data, ferramenta, risco, argumentos, decisão (`permitido`, `confirmado`, `negado`, `erro`, `bloqueado_limite`, `ferramenta_desconhecida`) e resultado truncado em 200 caracteres. Para ferramentas externas só grava o tamanho do resultado.
- `providers/base.py`: interface única (`Provider.complete(system, messages, tools) -> Response`) e dataclasses neutras (`Message`, `ToolSpec`, `ToolCall`, `ToolResult`).
- `providers/anthropic.py`: adaptador. O SDK só é importado na primeira chamada; converte mensagens/ferramentas para o formato da API; `check_key()` faz uma chamada mínima.
- `providers/__init__.py`: `create_provider(config)`.
- `tools/base.py`: `Tool` (nome, descrição, parâmetros em JSON Schema, `risk`, `untrusted`, `preapproved`, `run`), `Risk` (leitura, escrita, irreversível) e `ToolError`.
- `tools/registry.py`: descobre qualquer módulo em `tools/` que exponha `TOOL`. Nova ferramenta = novo arquivo.
- `tools/abrir_app.py`: abre por nome via `os.startfile` (Windows; `subprocess` fora dele, só para dev). Nomes fora da lista são aceitos apenas se forem um nome simples de executável: rejeita `:`, `/`, `\`, espaço, aspas e `& | < > ;`, o que bloqueia caminhos, URLs e injeção de argumentos. O lançamento fica em `_launch()` para ser mockado.
- `tools/buscar_arquivos.py`: busca por nome (todas as palavras), só nas pastas liberadas. Resolve `..`, não segue links simbólicos, limita a 50 resultados e a 100 mil itens varridos. Marcada como externa (nomes de arquivo são dados de terceiros).
- `tools/ler_agenda_google.py`: OAuth `InstalledAppFlow`, `calendar.readonly`, token com `chmod 600` quando possível. Lê de 1 a 14 dias a partir de uma data. Devolve só horário, título e local (a descrição do evento **não** é enviada). Marcada como externa. Imports do Google só dentro de `_get_service`.

### `tests/` (34 passam, 1 é pulado)
- `test_api_key.py`: chamada real mínima à API; pula sem chave.
- `test_secrets.py`: prioridade do keyring, fallback no ambiente, ausência de chave (keyring falso).
- `test_untrusted.py`: delimitação e impossibilidade de fechar a tag.
- `test_permissions.py`: as quatro regras de risco.
- `test_tools.py`: registro; `abrir_app` (lista, não pré-aprovado, rejeição de caminhos/URLs/comandos); `buscar_arquivos` (pastas liberadas, `..`, link simbólico, sem pastas, limite); agenda (formatação, descrição omitida, data inválida, escopo só leitura). Lançamento e Google são mockados.
- `test_orchestrator.py`: laço completo com provedor falso, conteúdo externo delimitado, limite por comando e padrão 8, confirmação negada/aceita, app da lista sem perguntar, ferramenta desconhecida, log sem conteúdo externo.

## Verificações feitas

- `uv sync` com Python 3.15.0b4 resolveu tudo; `uv lock --check` ok.
- `uv run pytest`: 34 passed, 1 skipped.
- Importar `fidus.core.orchestrator` não carrega `anthropic`, Google, `keyring` nem `pydantic` (medido com `-X importtime`).
- `uv run fidus --check-key` sem chave falha com mensagem clara (esperado).
- Um erro do próprio teste (`test_log_nao_guarda_conteudo_externo` olhava o argumento, não o resultado) foi corrigido; o código estava certo.

## O que NÃO foi validado (precisa de teste no Windows ou com credenciais)

- Chamada real à API da Anthropic (sem chave neste ambiente).
- `os.startfile` abrindo o Bloco de Notas e a Calculadora.
- keyring no Gerenciador de Credenciais do Windows.
- OAuth real do Google Agenda (navegador, token, "o que tenho hoje?").
- `uv sync` com Python 3.15 no Windows (a versão estava em beta quando o lock foi gerado).

## Publicação

Os primeiros pushes falharam com **403** (o Claude ainda não tinha acesso de escrita ao `tiagoluizrs/fidus`). Depois que o acesso foi liberado, o push funcionou: a branch `claude/repo-development-chfqvc` está no GitHub com a Etapa 1 e o `CONTEXT.md`. Nenhum PR foi aberto.

## Estado atual e combinado

- **Código da Etapa 1: completo** (os 7 itens do pedido), 34 testes passando e 1 pulado (chave da API).
- **Critérios de "pronto" do `PROJETO.md` ainda NÃO confirmados de verdade.** Tudo foi testado só com mocks, em Linux.
- **Próxima ação (manhã seguinte): o usuário testa tudo no Windows** seguindo o README (`uv sync`, `uv run fidus --check-key`, "abre o bloco de notas", "o que tenho hoje?" com o OAuth do Google, "abre o regedit" para ver o `[s/n]`, `uv run pytest`).
- O que quebrar no teste vira correção antes de qualquer trabalho novo. A Etapa 2 só começa depois disso.
- Se aparecer erro de dependência no `uv sync`, suspeitar primeiro do Python 3.15, que estava em beta (3.15.0b4) quando o `uv.lock` foi gerado.

## Próximo passo (não iniciado)

Etapa 2 do `PROJETO.md`: voz (push-to-talk com atalho global, faster-whisper local, resposta falada pela voz do sistema) e depois o detector "ei <nome>". Aplicar a mesma regra de imports preguiçosos a Whisper e TTS.


---

# Etapa 2: voz (apenas push-to-talk)

Branch `claude/etapa-2-voz`, criada a partir do `main` atualizado depois do squash merge do PR #1 (https://github.com/tiagoluizrs/fidus/pull/1, commit `b475a25`). Não existe branch `develop` no repositório; o PR e o merge foram em `main`. **Não foram feitos:** interface, Electron e detector "ei <nome>" (etapa 2B).

## Antes de começar (verificações pedidas)

- `uv run pytest` na etapa 1: 34 passaram, 1 pulado. Nada quebrado.
- Divergências da etapa 1 em relação ao `PROJETO.md`: provedor sem streaming e sem adaptador Ollama/OpenAI; sem memória e personagens (etapas seguintes).
- **Descoberta importante:** com Python 3.15 o `faster-whisper` não instala (`ctranslate2` só tem wheels até cp312; `onnxruntime` e `pywin32` também sem 3.15). Com 3.12 e 3.13 tudo resolve para Windows (`uv pip compile --python-platform windows`). O usuário aprovou voltar para **3.12**: `.python-version` = `3.12`, `requires-python = ">=3.12"`, venv recriada, `uv.lock` regenerado. O código da etapa 1 não dependia de nada da 3.15.
- Respostas às perguntas do plano: Python 3.12 (confirmado pelo usuário). As demais seguiram os padrões propostos: atalho `Ctrl+Alt+Espaço`; voz pt-BR se existir, senão a padrão do sistema; download do modelo na primeira vez (~480 MB do Hugging Face, gratuito, modelo aberto); streaming impresso também nos comandos de texto.

## Decisões técnicas

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Atalho global | `pynput` | Usa o gancho de teclado do Windows e dá eventos de apertar e soltar sem administrador. `RegisterHotKey` não avisa a soltura. Contra: não "engole" a tecla, o app em foco também a recebe. |
| Áudio | `sounddevice`, 16 kHz, mono, float32 | Pedido. Fluxo aberto só enquanto o atalho está pressionado (nada de escuta contínua; fica para a 2B). |
| STT | `faster-whisper` `small` `int8` CPU, `language="pt"`, `vad_filter=True`, `beam_size=1`, `condition_on_previous_text=False` | Pedido + escolhas de latência. Modelo carregado uma vez (`Transcriber.load`, idempotente). |
| Privacidade do áudio | Só memória. `salvar_audio_debug=false` por padrão; ligado grava `.wav` em `~/.fidus/debug_audio/` | Pedido. A única rede do Whisper é o download do modelo. |
| TTS | Interface `TTSProvider` (`speak`, `wait_idle`, `stop`, `close`, `on_start`) + `SapiTTS` (pywin32) | Pedido; Piper entra depois só trocando a implementação. |
| SAPI e COM | Thread próprio é dono do objeto COM; fala assíncrona (`Speak(text, 1)`) com sondagem de 50 ms; `stop()` incrementa uma "geração" que invalida a frase atual e a fila | COM exige usar no thread que criou o objeto. A versão inicial tinha corrida (`wait_idle` voltando cedo, `stop` perdido); foi reescrita com contador de pendentes e geração antes dos testes. |
| Voz pt-BR | Procura voz com LCID `416`; senão usa a padrão e `fidus say` avisa "sem voz pt-BR instalada" | Windows nem sempre tem o pacote de idioma. |
| Confirmação por voz | Fala o pedido, escuta com detecção de fim por energia (RMS), transcreve, interpreta. Ambíguo ("pode não", "sim, não"), vazio, timeout ou erro: **cai no `[s/n]` do teclado** | Nunca aprovar sozinho. |
| Streaming | `complete_stream` no provedor (Anthropic `messages.stream`); o orquestrador usa se existir, senão cai em `complete` e entrega o texto de uma vez | Compatível com provedores sem streaming e com os testes antigos. |
| Frases | `SentenceSplitter`: fecha em `. ! ? …` seguidos de espaço ou em quebra de linha; não corta decimais (`3.5`) nem abreviações (`Dr.`); limpa Markdown | A voz não deve ler `**` nem `#`. |
| Métricas | Em `actions.log` como eventos `memoria_whisper` e `metricas_pedido`; sem o texto falado, só o tamanho | Pedido; privacidade. |

## Arquivos criados ou alterados

- `fidus/core/config.py`: `VoiceConfig` (atalho, microfone, modelo, compute_type, dispositivo, idioma, velocidade, tempo de confirmação, áudio de debug, limites de gravação) e `[voz]` do `fidus.toml`; velocidade limitada a -10..10; `pt-BR` vira `pt` para o Whisper.
- `fidus/core/metrics.py`: `rss_mb()` (psutil, import preguiçoso) e `Timings` com as três latências: (a) soltar o atalho -> texto, (b) texto -> primeira palavra do modelo, (c) soltar o atalho -> início da voz.
- `fidus/core/actionlog.py`: `event(kind, **campos)` genérico.
- `fidus/core/providers/base.py` e `anthropic.py`: `complete_stream`; conversão de resposta compartilhada.
- `fidus/core/orchestrator.py`: `run(texto, on_text=None)`; entrega `"\n"` entre o texto anterior a uma ferramenta e o posterior, para as frases não grudarem.
- `fidus/core/voice/`: `audio.py` (listar e resolver dispositivo, `Recorder`, `EnergyEndpointer`, `record_until_silence`), `hotkey.py` (`PushToTalk` puro + `GlobalKeyListener`), `stt.py`, `tts.py`, `sentences.py`, `confirm.py` (`parse_yes_no`, `VoiceConfirmer`), `loop.py` (`VoiceLoop` e `build_voice_loop`).
- `fidus/__main__.py`: subcomandos `mics`, `say`, `voice`; `fidus` e `fidus "pedido"` continuam, agora com streaming. `fidus mics` sem PortAudio dá mensagem clara.
- `fidus.example.toml` (bloco `[voz]`), `README.md` (seção Voz, escolhas, configuração, medições, checklist manual), `pyproject.toml` (novas dependências; `pywin32` só em Windows), `uv.lock`.
- Testes novos: `test_sentences.py`, `test_hotkey_state.py`, `test_voice_confirm.py`, `test_stt_tts_audio.py`, `test_voice_loop.py`, `test_provider_stream.py`.

## Detalhes do laço de voz

Atalho completo pressionado -> `tts.stop()` (falar por cima interrompe) e começa a gravar. Soltar -> marca o tempo, para a gravação e enfileira. O laço principal descarta gravações < 0,3 s, transcreve, imprime `você> ...`, chama o orquestrador com `on_text`, que alimenta o `SentenceSplitter` e o TTS frase a frase; ao fim, `flush`, espera a voz terminar e grava `metricas_pedido`. Exceções no gancho de teclado são capturadas (uma exceção derrubaria o ouvinte global). Erro de um pedido vira "Desculpe, algo deu errado." e o laço continua.

## Verificações feitas

- `uv run pytest`: **85 passed, 1 skipped** (era 34).
- Importar `__main__`, orquestrador e todos os módulos de voz não carrega `faster_whisper`, `sounddevice`, `pynput`, `psutil`, `numpy`, `ctranslate2`, `anthropic` nem `onnxruntime` (`-X importtime`).
- Memória medida em Linux, sem modelo: núcleo importado ~16 MB; depois de importar `faster_whisper` ~64 MB (import 0,23 s).

## O que NÃO foi validado (precisa do PC do usuário)

- **Latências (a, b, c) e memória com o modelo carregado:** não medidas. O download do modelo (Hugging Face) é bloqueado neste ambiente (HTTP 403) e não há microfone. As medições ficam gravadas em `actions.log` quando o usuário rodar `fidus voice`.
- Microfone real, atalho global com `pynput`, SAPI com `pywin32` e voz pt-BR instalada, confirmação por voz de ponta a ponta, qualidade do "sim/não" em português, `Ctrl+Alt+Espaço` sem conflito com outro programa.
- Streaming real da API da Anthropic (testado só com cliente falso).
- Tudo da etapa 1 ainda pendente de validação no Windows (ver acima).
- Checklist manual completo está no `README.md`, seção "Voz (Etapa 2)".

## Limitações conhecidas

- O atalho não é bloqueado para o app em foco (`Ctrl+Alt+Espaço` também chega a ele).
- Detecção de fim da resposta "sim/não" por energia (RMS, limiar 0,015): em sala barulhenta pode demorar até o tempo limite e cair no teclado.
- A frase lida na confirmação é o texto técnico do pedido (`abrir_app (escrita): nome='regedit'`), um pouco robótico; dá para melhorar na etapa de personagens (falas por momento).
- O `stop()` do TTS usa sondagem de 50 ms.

## Próximo passo (não iniciado)

Etapa 2B: detector "ei <nome>" com openWakeWord. Antes, validar no Windows o checklist da voz e anotar as latências.
