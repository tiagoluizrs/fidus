# CONTEXT: o que foi feito (Etapa 1, núcleo no terminal)

Registro detalhado da sessão de desenvolvimento. Visão geral do produto em `PROJETO.md`; instalação e uso em `README.md`.

## Pedido

Construir **somente a Etapa 1** do roteiro: núcleo em Python no terminal (texto -> Claude -> ferramentas -> resposta). Sem interface, voz ou Electron. Alvo: Windows 10/11 com PowerShell, Python gerenciado pelo uv.

## Decisões tomadas

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Python | **3.15** (o pedido inicial dizia 3.12; o usuário corrigiu para 3.15, que também está no `PROJETO.md`) | Instrução do usuário. uv instalou a 3.15.0b4 (beta) e todas as dependências resolveram. |
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
