# Fidus

Assistente de voz para desktop (Windows), "seu conselheiro de IA". Visão, arquitetura e roteiro em [`PROJETO.md`](PROJETO.md).

**Estado atual: Etapa 2 (voz com push-to-talk) sobre o núcleo da Etapa 1.** Sem interface, sem Electron e sem detector "ei <nome>" (isso é a etapa 2B).

## Instalação (Windows 10/11, PowerShell)

O projeto usa Python **3.12** gerenciado pelo [uv](https://docs.astral.sh/uv/) (a 3.15 não serve: `faster-whisper`/`ctranslate2`, `onnxruntime` e `pywin32` não têm pacote para ela). O uv baixa o Python certo sozinho.

```powershell
# 1. instalar o uv (uma vez)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. instalar as dependências (lê pyproject.toml e uv.lock, cria a .venv)
uv sync

# 3. configurar
Copy-Item .env.example .env              # coloque a ANTHROPIC_API_KEY no .env
Copy-Item fidus.example.toml fidus.toml  # ajuste pastas liberadas e apps
```

- `uv sync`: instala exatamente as versões do `uv.lock` na `.venv` do projeto.
- `uv run <comando>`: roda o comando dentro dessa `.venv` (sem ativar nada à mão).
- `uv add <pacote>`: adiciona uma dependência e atualiza `pyproject.toml` e `uv.lock`.

## Execução

```powershell
uv run fidus --check-key                 # confirma que a chave da API funciona
uv run fidus                             # modo conversa (digite "sair" para encerrar)
uv run fidus "abre o bloco de notas"     # comando único
uv run pytest                            # testes
```

Exemplos para testar: `o que tenho hoje?` (agenda), `abre o bloco de notas`, `procura o arquivo relatório`.
Para ver a confirmação: `abre o regedit`. Apps fora da lista do `fidus.toml` pedem `[s/n]`.

## Configuração

| Onde | O quê |
| --- | --- |
| `.env` | `ANTHROPIC_API_KEY` (só desenvolvimento), `CLAUDE_MODEL` (padrão `claude-sonnet-5-5`), `FIDUS_HOME`, `FIDUS_CONFIG` |
| `fidus.toml` | `max_chamadas_ferramenta` (padrão 8), `pastas_liberadas`, `[apps.permitidos]` |
| `~/.fidus/` (ou `FIDUS_HOME`) | `actions.log` (log de ações), `credentials.json` e `token.json` do Google |

`.env`, `fidus.toml`, `.fidus/`, `credentials.json` e `token.json` estão no `.gitignore`.

### Chave da Anthropic

A chave é procurada primeiro no **Gerenciador de Credenciais do Windows** (via `keyring`, serviço `fidus`, nome `ANTHROPIC_API_KEY`) e, se não houver, no `.env`. A tela que grava no cofre vem na etapa seguinte; por enquanto o `.env` basta. Para gravar já no cofre:

```powershell
uv run python -c "from fidus.core.secrets import set_secret; set_secret('ANTHROPIC_API_KEY', input('chave: '))"
```

### Google Agenda (somente leitura)

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um projeto e ative a **Google Calendar API**.
2. Em *APIs e serviços > Tela de consentimento OAuth*, configure o app e adicione seu e-mail como usuário de teste.
3. Em *Credenciais*, crie um **ID do cliente OAuth** do tipo **App para computador** e baixe o JSON.
4. Salve-o como `~\.fidus\credentials.json`.
5. No primeiro "o que tenho hoje?" o navegador abre para você autorizar. O token fica em `~\.fidus\token.json`. O escopo pedido é só `calendar.readonly`.

## Estrutura

```
fidus/core/
  orchestrator.py   laço texto -> modelo -> ferramentas -> resposta
  permissions.py    confirmação [s/n], fora do modelo
  untrusted.py      conteúdo externo como dado delimitado (<dado_externo>)
  actionlog.py      log JSONL local
  config.py, secrets.py
  metrics.py        latências e memória (Etapa 2)
  providers/        interface única (base.py) + adaptador da Anthropic (com streaming)
  voice/            audio, hotkey (push-to-talk), stt (Whisper), tts (SAPI), sentences, confirm, loop
  tools/            um arquivo por ferramenta: abrir_app, buscar_arquivos, ler_agenda_google
docs/design/        telas do canvas de design (referência para a etapa 5; não usadas ainda)
```

**Nova ferramenta** = novo arquivo em `fidus/core/tools/` com uma classe `Tool` (nome, descrição, parâmetros, `risk`) e `TOOL = MinhaFerramenta()` no fim. O registro a encontra sozinho.

## Segurança (já valendo nesta etapa)

- **Permissão fora do modelo.** `leitura` roda direto; `escrita` pede `[s/n]` (salvo caso liberado na configuração, como apps da lista); `irreversível` sempre pede, nenhuma ferramenta pode dispensar.
- **Conteúdo externo é dado.** Eventos da agenda e nomes de arquivos chegam ao modelo dentro de `<dado_externo>`, e o texto não consegue fechar a tag. O prompt diz ao modelo para nunca obedecer instruções dali. É uma mitigação, não garantia: por isso as ações de risco são confirmadas por você, no código.
- **Só o necessário.** Da agenda vão título, hora e local; a descrição do evento não vai.
- **Pastas liberadas.** `buscar_arquivos` resolve `..` e não segue links simbólicos para fora delas.
- **Limite por comando**: 8 chamadas de ferramenta (configurável).
- **Log local** em `actions.log`: ferramenta, argumentos, decisão e um resumo curto. Resultados de conteúdo externo não são gravados. Sem telemetria.

## Desempenho

Imports pesados (`anthropic`, Google, `keyring`, `faster-whisper`, `sounddevice`, `pynput`, `psutil`, `win32com`) acontecem só quando usados, nunca ao importar o núcleo (conferido com `python -X importtime`). O Whisper só carrega ao iniciar `fidus voice`, uma vez, e fica na memória.

## O que foi validado e o que falta validar no Windows

Desenvolvido e testado em Linux (85 testes passando; o teste da chave da API pula sem `ANTHROPIC_API_KEY`). **Precisa ser validado no Windows:**

- [ ] `abrir_app`: o lançamento real (`os.startfile`) é mockado nos testes. Conferir `abre o bloco de notas` e `abre a calculadora`.
- [ ] `keyring` no Gerenciador de Credenciais do Windows (os testes usam um módulo falso).
- [ ] `ler_agenda_google` com OAuth real (os testes usam a API mockada), incluindo o fluxo de autorização no navegador.
- [ ] `uv sync` com Python 3.12 no Windows (o `uv.lock` foi gerado no Linux; as dependências de voz foram checadas para Windows com `uv pip compile --python-platform windows`).
- [ ] `uv run fidus --check-key` com a sua chave.
- [ ] **Voz (Etapa 2):** microfone real (`sounddevice`), atalho global (`pynput`), SAPI (`pywin32`), download e uso do Whisper, streaming real da API e as medições. Tudo isso usa mocks nos testes; ver o checklist da seção Voz.

## Voz (Etapa 2)

```powershell
uv run fidus mics                # lista os microfones (marca o padrão e o escolhido)
uv run fidus say "Olá, sou o Fidus"   # testa a voz do sistema
uv run fidus voice               # laço de voz: segure o atalho, fale, solte
```

`uv run fidus` e `uv run fidus "pedido"` (texto) continuam iguais, agora com a resposta aparecendo em streaming.

**Fluxo:** segurar `Ctrl+Alt+Espaço` grava; soltar envia -> faster-whisper transcreve -> o orquestrador (Claude, com streaming) responde -> a voz fala **frase a frase** enquanto o texto ainda chega. Falar por cima (apertar o atalho de novo) interrompe a voz.

**Escolhas técnicas**

- **Atalho global: `pynput`.** Usa o gancho de teclado do Windows e avisa tecla pressionada e solta sem exigir administrador (o `RegisterHotKey` do Windows não avisa quando solta). O atalho não é "engolido": o aplicativo em foco também recebe as teclas.
- **Áudio: `sounddevice`**, 16 kHz, mono. O fluxo do microfone só fica aberto enquanto você segura o atalho.
- **Transcrição: faster-whisper**, modelo `small`, `int8`, CPU, idioma pt, filtro de silêncio (VAD), `beam_size=1`. Modelo carregado uma vez ao iniciar `fidus voice`. O áudio fica **só na memória**; salvar em disco (`salvar_audio_debug`) vem desligado. A única rede do Whisper é o **download do modelo na primeira vez** (~480 MB, do Hugging Face, para `~\.cache\huggingface`); depois roda offline.
- **Voz: SAPI** (voz do Windows) via `pywin32`, atrás da interface `TTSProvider` (`fidus/core/voice/tts.py`), para trocar por Piper depois. Usa uma voz pt-BR se houver; senão, a padrão do sistema (o `fidus say` mostra qual).
- **Confirmação por voz:** quando uma ação pede `[s/n]`, o Fidus pergunta falando e escuta "sim" ou "não" (tempo limite configurável). Resposta confusa, ambígua ("pode não"), silêncio ou erro no microfone **caem no teclado**; nunca aprova sozinho.

### Configuração da voz (`fidus.toml`)

```toml
[voz]
atalho = "ctrl+alt+space"   # ex.: "f9", "ctrl+shift+space"
microfone = ""              # vazio = padrão; ou índice / parte do nome (veja `fidus mics`)
modelo_whisper = "small"    # base (mais leve) | small | medium (mais preciso)
compute_type = "int8"
dispositivo = "cpu"
idioma = "pt-BR"
velocidade_voz = 0          # -10 a 10
tempo_confirmacao_s = 8
salvar_audio_debug = false  # true grava .wav em ~\.fidus\debug_audio (só para depurar)
```

### Medições (no log)

Em `~\.fidus\actions.log` (JSON por linha, sem texto do que você falou):

- `memoria_whisper`: `rss_antes_mb`, `rss_depois_mb` e `carga_s` (uma vez, ao carregar o modelo).
- `metricas_pedido`, a cada pedido falado: `a_fala_ate_texto_s` (soltar o atalho -> texto), `b_texto_ate_primeira_palavra_s` (texto -> primeira palavra do modelo), `c_fala_ate_inicio_da_voz_s` (soltar o atalho -> a voz começar) e `rss_mb`.

Ver rápido: `Select-String '"metricas_pedido"|"memoria_whisper"' $HOME\.fidus\actions.log`

Medido no ambiente de desenvolvimento (Linux, sem modelo): o núcleo importado ocupa ~16 MB; só importar o `faster_whisper` leva a ~64 MB. **Latência e memória reais com o modelo carregado não puderam ser medidas lá (download bloqueado, sem microfone): meça no seu PC.**

### Checklist manual (Windows)

Marque conforme for testando:

- [ ] `uv sync` conclui sem erro (Python 3.12).
- [ ] `uv run pytest`: tudo passa.
- [ ] `uv run fidus mics` lista o seu microfone; ao pôr `microfone = "..."` no `fidus.toml`, ele aparece como `[escolhido no fidus.toml]`.
- [ ] `uv run fidus say "Olá, sou o Fidus"` fala em português; anote a voz que aparece em `Voz:`. Se disser "sem voz pt-BR instalada", instale o idioma em Configurações > Hora e idioma > Fala.
- [ ] `uv run fidus voice`: primeira execução baixa o modelo; depois mostra "Segure ctrl+alt+space...".
- [ ] Segurar o atalho, dizer "que horas são?" (ou "abre o bloco de notas") e soltar: aparece `você> ...` com o texto certo e a resposta é falada.
- [ ] A voz começa **antes** de o texto completo terminar (frase a frase).
- [ ] Apertar o atalho enquanto ele fala interrompe a voz.
- [ ] Toque rápido no atalho (< 0,3 s) é ignorado.
- [ ] O atalho funciona sem abrir o PowerShell como administrador.
- [ ] Pedir "abre o regedit": o Fidus pergunta **falando**; responder "sim" executa e "não" cancela.
- [ ] Na confirmação, ficar em silêncio ou dizer algo confuso: cai no `[s/n]` do teclado.
- [ ] Desconectar o microfone / usar um índice errado: mensagem clara, sem travar.
- [ ] `actions.log` tem `memoria_whisper` e `metricas_pedido`; anote os números (latências a, b, c e `rss_depois_mb`).
- [ ] Nenhum `.wav` em `~\.fidus` (a menos que `salvar_audio_debug = true`).
- [ ] Com o Gerenciador de Tarefas aberto, conferir a memória do Python com o modelo carregado e em repouso.

## Fora do escopo desta etapa

Detector "ei Alfred" (etapa 2B), personagens e memória (etapa 3), Gmail/Slack, interface, Piper e provedor Ollama. Ver o roteiro no `PROJETO.md`.
