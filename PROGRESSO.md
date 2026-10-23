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
| 3 | Personagens e memória | **Feita** (branch `claude/etapa-3-personagens`) |
| 4 | Integrações (Gmail, Slack, Agenda, keyring) | Pendente |
| 5A/5B | Interface Electron + React | Pendente |
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
