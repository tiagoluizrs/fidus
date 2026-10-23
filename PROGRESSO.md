# PROGRESSO

Este arquivo permite **retomar o trabalho em outra sessão**. Detalhes históricos das etapas 1, 2 e 2B estão em
`CONTEXT.md`; o visão geral do produto, em `PROJETO.md`; instalação e uso, em `README.md`.

## Como retomar

1. `git checkout main && git pull`, depois `uv sync` e `uv run pytest` (tudo deve passar; 1 teste é pulado sem chave).
2. Leia a seção "Estado por etapa" abaixo e "Dúvidas para refinar".
3. Fluxo de trabalho combinado: **uma branch, um PR e um squash merge por etapa** (`claude/etapa-N-...`), atualizar
   `README.md` e este arquivo no fim de cada etapa.
4. Ambiente de desenvolvimento é Linux; tudo que é do Windows (microfone, SAPI, atalho, keyring, OAuth, instalador) foi
   testado só com mocks e está marcado para validação no PC (listas no README).

## Estado por etapa

| Etapa | O quê | Estado |
| --- | --- | --- |
| 1 | Núcleo no terminal (orquestrador, provedor Anthropic, 3 ferramentas, permissão, log) | Feita, mergeada (PR #1) |
| 2 | Voz push-to-talk (Whisper local, SAPI, streaming, confirmação por voz) | Feita, mergeada (PR #2) |
| 2B | Palavra de ativação (openWakeWord), AudioManager, `listen`, personagens pelo nome | Feita, mergeada (PR #2) |
| 3 | Personagens e memória | Feita, mergeada (PR #3) |
| 4 | Integrações (Gmail, Slack, Agenda, keyring) | Feita, mergeada (PR #4) |
| 5A | Servidor WebSocket, Electron, bandeja e anel | **Feita** (branch `claude/etapa-5a-nucleo-e-anel`) |
| 5B | Janela de Configurações | Pendente |
| 6 | Empacotar | Pendente |

## Etapa 3: personagens e memória

**O que foi feito** (detalhes no README, seção "Personagens e memória"):

- Perfis em JSON: padrões em `fidus/defaults/characters/` (imutáveis) e edições do usuário em `~/.fidus/characters/`
  (só o que mudou). Alfred, Donna e Jarbis com ≥ 6 frases por categoria, tratamentos, controles e voz.
- Personalidade: 4 estilos + personalizado, 5 controles 0-100 com padrão por personagem e instruções extras; prompt de
  sistema montado por faixas (`characters/prompt.py`), com texto do usuário e memória delimitados como dado.
- Frases: tratamentos (aleatório/fixo/contexto), 5 momentos, variáveis `{tratamento} {nome} {sobrenome} {periodo}
  {hora} {dia}` (+ `{saudacao}`), sorteio sem repetir, pular frase com variável sem valor, ativar/desativar, editar, apagar,
  adicionar, restaurar apagadas, restaurar lista, restaurar controle e personagem inteiro.
- Falas de início pré-gravadas em cache de disco por (personagem, frase, voz), com invalidação e limpeza.
- Voz por personagem atrás de `TTSProvider`: SAPI (padrão, tom via XML), Piper local opcional (executável `piper`) e
  interface `CloudVoiceProvider` para voz por descrição (sem serviço).
- Memória única: Markdown (perfil, rotinas, contatos, projetos/) + SQLite (histórico e resumos) com SQLCipher quando
  possível; ferramenta `memoria`; opção "perguntar antes de guardar"; trecho relevante no prompt com limite; resumo
  periódico; cache de prompt (parte estável do prompt marcada com `cache_control`).
- Troca de personagem no meio da conversa sem perder o contexto; o padrão responde ao atalho.
- CLI: `character list|show|reset|default|set|phrase`, `memory list|search|add|edit|delete|export|forget-all`,
  `user show|set`, `say --personagem`, `fidus "pedido" --personagem`.
- Configuração: `settings.json` (escrito pelo Fidus/CLI/interface) vale sobre o `fidus.toml` (nunca reescrito).

**Mudanças em relação ao PROJETO.md**

- O **log de ações continua em JSONL** (`actions.log`), não em SQLite. Motivo: auditável a olho, sem chave, e usado desde
  a etapa 1. O SQLite guarda histórico e resumos. (Ver dúvida 3.)
- Arquivos Markdown da memória **não são cifrados** (são para o usuário ler/editar); só o SQLite é.
- Defesa extra não prevista: depois de ler conteúdo externo em um comando, nenhuma ação é dispensada de confirmação.
- `Tool.risk_for(args)`: o risco pode variar por ação (usado pela ferramenta `memoria`).
- A confirmação por voz agora abre com a fala "confirmar" do personagem.
- Dependências novas: `sqlcipher3-wheels` (criptografia). Piper e Ollama continuam opcionais/fora.
- `requires-python = ">=3.12,<3.13"` (o openwakeword puxa o tflite-runtime no Linux; descartado por override).

**Pendências de validação no Windows**

- Voz de cada personagem (SAPI pt-BR, tom por XML, `SpFileStream` para gerar o cache), reprodução com `winsound`.
- SQLCipher no Windows (wheel `sqlcipher3-wheels` para cp312 resolveu no `uv pip compile`, não foi instalado lá) e a
  chave no Gerenciador de Credenciais.
- Piper (opcional) nunca foi executado de verdade, só com um executável simulado.
- A qualidade do sorteio de frases e o tom de cada personagem precisam de ouvido humano.
- Checklist manual: README, seção "Personagens e memória".

## Etapa 4: integrações

**O que foi feito** (README, seção "Integrações"; passo a passo do usuário em `docs/INTEGRACOES.md`):

- Interfaces `CalendarService`, `EmailService` e `ChatService` (`fidus/core/services/base.py`) e `ServiceHub` que escolhe o
  adaptador pela configuração (`[contas]`). As ferramentas (`agenda`, `email`, `rascunho_email`, `chat`) não importam
  nenhum adaptador (há teste para isso). `ler_agenda_google` foi substituída por `agenda` (ler/criar/alterar).
- Adaptadores diretos: Google Agenda e Gmail (`google-api-python-client`, já instalado) e Slack (API Web via `urllib`).
- Gmail: buscar (só metadados + trecho), ler um e-mail (corpo em texto, sem anexos, cortado), criar **rascunho**
  (validação de destinatário e de cabeçalhos). **Não existe envio** (nem método, nem ação, nem ferramenta; há teste).
- Slack: só canais/conversas em `canais_permitidos`; responder só com `escrita = true` e sempre com confirmação.
- Escrita liberada por serviço e **barrada antes de perguntar** (`Tool.precheck`) quando não está liberada.
- OAuth do Google com escopos mínimos (leitura por padrão); só o refresh token vai para o cofre (JSON curto);
  migração do `token.json` da etapa 1; `accounts connect|disconnect|list|channels`.
- Cofre do Windows de verdade: `secrets set|get|delete|list|migrate` (migra a chave do `.env` e remove a linha).
- Limites de conteúdo externo em `[limites]` (item 600 chars, 10 itens, 4000 por pedido).
- Testes de segurança: e-mail com injeção + "modelo" obediente = 5 ações tentadas, 5 confirmações, 0 execuções; todas as
  escritas pedem confirmação; delimitação não escapa; Slack fora da lista nem é consultado.

**Mudanças em relação ao PROJETO.md**

- Servidores **MCP** não foram usados (ver dúvida 8). O desenho por interfaces permite plugar MCP depois.
- O Gmail não tem escopo só de rascunho (`gmail.compose` também envia); documentado, e o Fidus nunca envia.
- O Slack usa **token de usuário** (respostas saem como você), não token de bot (ver dúvida 11).
- A ferramenta `ler_agenda_google` deixou de existir (nome genérico `agenda`).

**Pendências de validação no Windows / com contas reais**

- OAuth real do Google (navegador, aviso de app não verificado, expiração em modo Teste), Gmail e Agenda reais.
- Token do Slack real, escopos, aprovação do administrador, nomes de DMs.
- Keyring: tamanho máximo da credencial do Windows (o JSON do Google tem < 1000 caracteres) e entradas `fidus/*`.
- Checklist: README, "Checklist manual (Windows, Etapa 4)".

## Etapa 5A: servidor local, bandeja e anel

**O que foi feito** (README, seção "Interface"; protocolo em `docs/PROTOCOLO.md`):

- **Núcleo** (`fidus/core/bridge/`): servidor WebSocket em `127.0.0.1` (porta aleatória, token aleatório por
  inicialização anunciado só na saída padrão do processo filho, recusa `Origin`, autenticação em 5 s, 1 MB por mensagem),
  protocolo v1 (estado, nível ~37/s, legendas em pedaços, personagem, confirmação pendente, chamados, configurações),
  comandos validados (`mute`, `pause`, `calls`, `set_default_character`, `confirm_reply`, `get/set_settings`, `ping`,
  `quit`), `fidus daemon [--simulado] [--stdin-watch]` e **núcleo simulado** (sem microfone/modelo/voz).
- `ConfirmBroker`: a confirmação aparece na tela (Sim/Não) e é falada ao mesmo tempo; vale a primeira resposta. O
  `listen` do terminal continua com `[s/n]`.
- `ListenLoop` passou a avisar a interface (estado, "escutar chamados", pausa por tempo, silenciar); `VoiceLoop` envia
  legendas e estados; `AudioManager` calcula o nível só quando há interface conectada.
- `settings_schema.py`: só chaves da tabela, com tipo e faixa, são gravadas pela interface (tudo ou nada).
- **App** (`app/`, Electron + React + TypeScript + Vite): processo principal com o cliente do WebSocket (o token nunca vai
  ao renderer), bandeja, janela do anel criada sob demanda e destruída depois de 6 s parado, anel em Canvas (4 camadas,
  estados, temas claro/escuro como no design), legendas, indicador de microfone, Esc, diálogo de confirmação acessível,
  tema que acompanha o Windows ao vivo, ícones gerados por script (`app/scripts/make_icons.py`).
- Segurança do Electron: `contextIsolation`, sem `nodeIntegration`, sandbox, preload mínimo, CSP restritiva, sem rede nem
  navegação, sem permissões, comandos por allowlist e só de páginas do app (`quit` fora). Testes impedem afrouxar.
- Testes: Python 301 (servidor, auth, origin, protocolo, núcleo simulado, confirmação, órfão); app 59 (anel, modelo,
  tela, bandeja, ciclo de vida, núcleo, segurança, protocolo contra o núcleo simulado **real**).
- Verificado no Electron de verdade (xvfb, Linux): núcleo simulado conectado, janela do anel criada na conversa e
  destruída depois, capturas de tela nos dois temas conferidas.

**Mudanças em relação ao PROJETO.md**

- Dependência nova no Python: `websockets` (a biblioteca padrão não tem servidor WebSocket). No app: Electron, React,
  Vite, Vitest etc. (lista em `app/package.json`).
- O **Esc** é um atalho global registrado só enquanto o anel existe (a janela abre sem roubar o foco, então não receberia
  a tecla). Ver dúvida 14.
- Ícones provisórios gerados por código (anel, anel ondulado e ponto). A versão final do logo (texto em contornos,
  SVG/ICO) continua pendente, como no PROJETO.md.
- O nível de áudio da **voz do assistente** não existe no núcleo (SAPI não expõe); no estado "falando" o anel usa um
  envelope sintético.
- O adaptador de modelo **local (Ollama)** do PROJETO continua **não implementado** (só Claude). A tela "Modelo de IA" da
  5B mostrará Local como "em breve". Ver dúvida 16.

**Pendências de validação no Windows**

- Tudo do app foi verificado em Linux (xvfb). No Windows: ícone na bandeja (cores/tamanho), `showInactive` + `alwaysOnTop`
  em tela cheia, Esc global, tema ao vivo, múltiplos monitores (o anel abre no principal), o núcleo Python como filho
  (`uv run fidus daemon`) e o encerramento sem processo órfão.
- Nível de áudio real e latência da interface com o microfone real.

## Dúvidas para refinar quando o usuário acordar

1. **Tratamento padrão neutro:** Alfred usa "senhor" fixo (mordomo). Para tratamento neutro quanto a gênero, melhor
   perguntar ao usuário como quer ser chamado na primeira execução? (Hoje: `character set alfred --tratamento-fixo ...`.)
2. **`perguntar_antes_de_guardar` padrão:** deixei **falso** (o PROJETO diz que o Fidus guarda o que aprende), mas toda
   escrita depois de ler conteúdo externo já exige confirmação. Prefere começar com verdadeiro?
3. **Log de ações em SQLite?** O PROJETO sugere SQLite para histórico e log. Mantive JSONL (auditável, sem chave). A
   interface (etapa 5) lerá o JSONL. Trocar, ou manter?
4. **Fala de início antes de gravar:** a fala curta ("Pois não, senhor.") toca **antes** de abrir a gravação, para o
   microfone não gravar a própria voz. Isso atrasa 1 a 2 s quem fala "ei Alfred, que horas são" de uma vez. Alternativa:
   chime curto (já existe, `som_ao_ouvir`) e falar só depois. Qual prefere? (`falar_inicio = false` desliga.)
5. **Frases com "ei"/português no TTS e nomes próprios** (Jarbis, Alfred) dependem da voz SAPI instalada.
6. **Memória Markdown sem criptografia:** aceitável? Alternativa: cifrar também (perde edição à mão).
7. **Piper:** quer que eu deixe o download/instalação guiados em `docs/`? Hoje é só o adaptador.
8. **MCP:** a regra pede justificar e **perguntar antes** de adicionar dependência de terceiros. Usei clientes diretos
   (sem dependência nova). Um servidor MCP de Gmail/Slack exigiria o SDK `mcp` e processos Node de terceiros (mais
   memória em repouso e mais superfície de ataque). Quer mesmo assim algum MCP (ex.: Google Agenda), ou mantemos direto?
9. **App do Google em "Em produção" sem verificação** (para o token não expirar em 7 dias): aceitável para uso pessoal?
10. **`gmail.compose`** também permite enviar (o Google não tem escopo só de rascunho). Aceita, ou prefere não ter
    rascunho na v1 e ficar só com `gmail.readonly`?
11. **Slack:** token de **usuário** (lê DMs e canais privados dos quais você participa; respostas saem como você) ou de
    **bot** (precisa ser convidado nos canais; respostas saem como "Fidus")? Hoje: usuário.
12. **Fricção da regra de contaminação:** depois de ler e-mail/mensagem/evento, até "abre o bloco de notas" pede
    confirmação no mesmo comando. Aceitável? (Ler a própria memória não conta.)
13. **Chave do Windows Credential Manager:** limite de ~2,5 KB por credencial. O JSON do Google cabe, mas confirmar no PC.
14. **Esc global enquanto o anel está aberto:** o anel não rouba o foco (para não atrapalhar quem está digitando), então
    uso um atalho global só enquanto ele existe. Aceitável? Alternativa: a janela toma o foco (Esc normal, mas interrompe
    a digitação).
15. **Fechar o anel depois de 6 s parado** é configurável (`app.janela_inatividade_s` na 5B). Valor padrão ok?
16. **Modelo local (Ollama):** está no escopo da v1 do PROJETO, mas nenhuma etapa pedida inclui o adaptador. Quer que eu
    faça (adaptador no formato OpenAI, restrito a ferramentas de leitura) depois da etapa 6?
17. **Logo final:** os ícones atuais são provisórios (gerados por código). Quando tiver o SVG final, é só trocar
    `app/assets/` e rodar o empacotamento.
