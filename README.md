# Fidus

Assistente de voz para desktop (Windows), "seu conselheiro de IA". Visão, arquitetura e roteiro em [`PROJETO.md`](PROJETO.md).

**Estado atual: Etapa 1, núcleo no terminal.** Sem voz, sem interface e sem Electron ainda.

## Instalação (Windows 10/11, PowerShell)

O projeto usa Python **3.15** gerenciado pelo [uv](https://docs.astral.sh/uv/). O uv baixa o Python certo sozinho.

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
  providers/        interface única (base.py) + adaptador da Anthropic
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

Imports pesados (`anthropic`, Google, `keyring`) acontecem só quando usados, nunca ao importar o núcleo. Whisper e TTS (etapa 2) seguirão a mesma regra.

## O que foi validado e o que falta validar no Windows

Desenvolvido e testado em Linux (34 testes passando; o teste da chave da API pula sem `ANTHROPIC_API_KEY`). **Precisa ser validado no Windows:**

- [ ] `abrir_app`: o lançamento real (`os.startfile`) é mockado nos testes. Conferir `abre o bloco de notas` e `abre a calculadora`.
- [ ] `keyring` no Gerenciador de Credenciais do Windows (os testes usam um módulo falso).
- [ ] `ler_agenda_google` com OAuth real (os testes usam a API mockada), incluindo o fluxo de autorização no navegador.
- [ ] `uv sync` com Python 3.15 no Windows: a 3.15 ainda estava em beta (3.15.0b4) quando o `uv.lock` foi gerado, então conferir se todas as dependências têm wheel para Windows.
- [ ] `uv run fidus --check-key` com a sua chave.

## Fora do escopo desta etapa

Voz, Whisper, TTS, detector "ei Alfred", personagens, memória, Gmail/Slack, interface e streaming de respostas. Ver o roteiro no `PROJETO.md`.
