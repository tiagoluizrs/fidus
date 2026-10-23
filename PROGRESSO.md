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
| 5A | Servidor WebSocket, Electron, bandeja e anel | Feita, mergeada (PR #5) |
| 5B | Janela de Configurações | Feita, mergeada (PR #6) |
| 6 | Empacotar | **Feita** (branch `claude/etapa-6-empacotar`); falta gerar o `.exe` e validar no Windows |

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

## Etapa 5B: janela de Configurações

**O que foi feito** (README, seção "Configurações"; comandos em `docs/PROTOCOLO.md` 4.1):

- **Núcleo**: `Handlers` com as operações das telas (personagens, memória, contas, privacidade, sobre, vozes,
  microfones, chave da API), `settings_schema` ampliado (+ `RESTART_REQUIRED`, `effective`), `apply_live` (a maioria das
  mudanças vale na hora; atalho, microfone e modelo de voz pedem reinício e a tela avisa), log de ações lido pela tela,
  memória com origem (`usuario`/`aprendida`) e `memoria.aprender`.
- **App**: janela única com 8 telas (Geral, Voz, Personagem, Modelo de IA, Contas, Privacidade, Memória, Sobre), fiel
  ao design, temas claro/escuro, teclado e leitor de tela (switch/radiogroup/alertdialog), toasts, captura de atalho.
- **IPC novo** (só a janela de Configurações; o processo principal confere a origem): escolher pasta/arquivo, salvar
  texto, abrir pasta, ajustes do microfone (URL fixa `ms-settings:privacy-microphone`), copiar, reiniciar o núcleo.
- Segurança: ações sem volta exigem `confirm: true`; exportação sem chaves/tokens; a chave da API nunca volta para a tela.
- Testes: Python 356; app 73+ (telas contra um núcleo de mentira, atalho, funções puras, preload mínimo atualizado e
  um teste de ponta a ponta contra o núcleo simulado real).

**Mudanças em relação ao PROJETO.md**

- A chave da Anthropic pode ser colada na tela (vai direto ao cofre do Windows). Ver dúvida 18.
- Modelo local (Ollama) aparece como "em breve" (dúvida 16). Outlook, Teams e Microsoft Agenda também.
- Alguns controles ficam desabilitados com explicação quando o recurso ainda não existe (ver dúvida 19).

**Pendências de validação no Windows**: vozes SAPI e prévia, lista de microfones, estado da permissão do microfone,
abrir ajustes do Windows, "iniciar com o Windows", escolha de pasta/arquivo, OAuth do Google, token do Slack, captura
do atalho (incluindo teclas com a tecla Win), reinício do núcleo pela tela.

### Checklist manual (Windows, Etapa 5B)

- [ ] `cd app; npm start`: bandeja > Configurações abre a janela; cada item do menu abre a tela certa.
- [ ] Geral: trocar o tema (muda na hora), ligar "Iniciar junto com o sistema" (conferir em Configurações do Windows >
      Aplicativos > Inicialização), esconder o ícone da bandeja.
- [ ] Voz: trocar a voz e ouvir a prévia, mudar a velocidade, escolher o microfone; atalho novo pede reinício.
- [ ] Personagem: editar uma frase, apagar e restaurar, ajustar um controle e conferir que a fala muda.
- [ ] Contas: conectar o Google (navegador), colar o token do Slack, desconectar.
- [ ] Privacidade: adicionar/remover pasta, ver o log, exportar os dados (conferir que o zip não tem chaves).
- [ ] Memória: adicionar, buscar, editar, apagar uma, apagar tudo (digitando APAGAR).
- [ ] Sobre: copiar o diagnóstico (sem segredos).

## Etapa 6: empacotar

**O que foi feito** (README "Empacotar e instalar"; passo a passo em `docs/LANCAMENTO.md`; números em `docs/MEDICOES.md`):

- **Núcleo congelado:** `packaging/fidus-core.spec` (PyInstaller, onedir), `core_entry.py`, `build_core.ps1`/`.sh`. Como os
  imports são preguiçosos, o `.spec` coleta o pacote `fidus` inteiro e os dados de `openwakeword`, `faster_whisper`,
  `googleapiclient`, `certifi` e os personagens padrão. Achado no teste: sem `fidus/defaults` o núcleo congelado quebrava
  (`StopIteration` ao escolher o personagem); corrigido e coberto pelo novo `fidus-core selftest`.
- **`fidus selftest`:** importa as bibliotecas pesadas e confere os dados empacotados (sai com 1 se faltar algo).
- **Instalador:** `electron-builder` (NSIS, por usuário, sem administrador, atalho só no Menu Iniciar, sem publicação),
  núcleo em `resources\core\fidus-core.exe`, `deleteAppDataOnUninstall: false`.
- **Dados:** novo padrão `%APPDATA%\Fidus` (`fidus/core/paths.py`) com **cópia** (nunca remoção) da antiga `~\.fidus` na
  primeira execução; cache do Electron em `%APPDATA%\Fidus\app` (não conta como "já tem dados" na migração).
- "Iniciar com o Windows" já existia (5B, `setLoginItemSettings`, só empacotado).
- **Verificado em Linux:** build do núcleo congelado, `selftest` congelado, núcleo congelado anunciando porta/token, o app
  empacotado (`electron-builder --dir`) iniciando o núcleo de `resources/core` e conectando, medição de 10 min em repouso.
- Testes: Python 361 (incl. `test_paths.py`); app 75 (incl. pastas de dados).

**Mudanças em relação ao PROJETO.md**

- Dependências novas só de build: `pyinstaller` (grupo `build` do uv) e `electron-builder` (devDependency). Nenhuma entra
  no app instalado além do que já havia.
- Pasta de dados padrão no Windows mudou de `~\.fidus` para `%APPDATA%\Fidus` (dúvida 20).
- Tauri/MSIX: só analisados em texto (`docs/LANCAMENTO.md`), nada executado.

**Pendências (precisam do Windows)**

- Gerar o `.exe` de verdade (`npm run dist`), medir tamanho do instalador e do núcleo, instalar numa máquina limpa e
  percorrer o checklist de `docs/LANCAMENTO.md`; rodar `fidus-core.exe selftest` no Windows (PortAudio, pynput, pywin32,
  SQLCipher, openWakeWord com ONNX).
- As medições do `MEDICOES.md` foram feitas com o núcleo **simulado** em Linux; refazer com núcleo real (Whisper
  carregado, escuta passiva ligada) no Windows.
- Assinatura de código, falso positivo de antivírus, logo final.

### Checklist manual (Windows, Etapa 6)

Está em `docs/LANCAMENTO.md`, seção 4.

## Dúvidas para refinar quando o usuário acordar

1. **Tratamento padrão neutro:** Alfred usa "senhor" fixo (mordomo). Para tratamento neutro quanto a gênero, melhor
   perguntar ao usuário como quer ser chamado na primeira execução? (Hoje: `character set alfred --tratamento-fixo ...`.)
   R: Acho que precisa ter area para dizer se é homem, mulher, prefere não informar, isso deixa as respostas padrões mas podendo ser alteradas.
2. **`perguntar_antes_de_guardar` padrão:** deixei **falso** (o PROJETO diz que o Fidus guarda o que aprende), mas toda
   escrita depois de ler conteúdo externo já exige confirmação. Prefere começar com verdadeiro?
   R: Talvez fazer igual vc, ter a opção de ativar uma conversa temporária, quando ela é encecrrada alfred dormir mais de 1 horas podemos deletar. Mas quero fazer algo fluido, então toda conversa meio que deve fazer ele guardar contexto se eu citei meu filho 1 mes atrás ele deve saber quem é meu filho, mas se eu citar, quero bater um papo mais privado agora, e depois terminar com você pode sair do modo privado, ele sai, se após 1 hora quieto sem conversa não pedir volta sozinho.
3. **Log de ações em SQLite?** O PROJETO sugere SQLite para histórico e log. Mantive JSONL (auditável, sem chave). A
   interface (etapa 5) lerá o JSONL. Trocar, ou manter?
   R: Quero que seja seguindo a LGPD e que seja o mais performático para o OS. Inclusive falando de performance evite reescrever variavies para evitar problema de realocação em memória, use boas práticas ok?
4. **Fala de início antes de gravar:** a fala curta ("Pois não, senhor.") toca **antes** de abrir a gravação, para o
   microfone não gravar a própria voz. Isso atrasa 1 a 2 s quem fala "ei Alfred, que horas são" de uma vez. Alternativa:
   chime curto (já existe, `som_ao_ouvir`) e falar só depois. Qual prefere? (`falar_inicio = false` desliga.)
   R: Quero que seja da melhor forma para não dar bug e como outros agentes tem feito. Ideal tmb tentar reconhecer as 3 vozes do robo e ignorar, mas se isso consumir tempo e memória melhor sempre desligar mic quando robo estiver falando
5. **Frases com "ei"/português no TTS e nomes próprios** (Jarbis, Alfred) dependem da voz SAPI instalada.
  R: Vc quer permissão ou tá dizendo que é impossível?
6. **Memória Markdown sem criptografia:** aceitável? Alternativa: cifrar também (perde edição à mão).
  R: Qual o melhor padrão, mais rápido e que respeita LGPD? Coloque tudo em uma balança e decida.
7. **Piper:** quer que eu deixe o download/instalação guiados em `docs/`? Hoje é só o adaptador.
  R: Como assim download e o que é piper?
8. **MCP:** a regra pede justificar e **perguntar antes** de adicionar dependência de terceiros. Usei clientes diretos
   (sem dependência nova). Um servidor MCP de Gmail/Slack exigiria o SDK `mcp` e processos Node de terceiros (mais
   memória em repouso e mais superfície de ataque). Quer mesmo assim algum MCP (ex.: Google Agenda), ou mantemos direto?
  R: Acho que por enquanto não precisa né? Talvez no futuro criemos uma área que a pessoa faz seus MCPs, mas para agora tá de boa sem.
9. **App do Google em "Em produção" sem verificação** (para o token não expirar em 7 dias): aceitável para uso pessoal?
  R: Não quero que nada expire.
10. **`gmail.compose`** também permite enviar (o Google não tem escopo só de rascunho). Aceita, ou prefere não ter
    rascunho na v1 e ficar só com `gmail.readonly`?
    Cara acho que devemos deixar a pessoa escolher em cada add on se quer somente ler ou responder, isso para slack, gmail e qualquer outro email ou chat, para calendario poder ver agendas e criar eventos editar etc. Se nos emails e conversa for possível ler anexos, baixar e ler, avaliar por vc mesmo e citar para a pessoa, seria genial.
11. **Slack:** token de **usuário** (lê DMs e canais privados dos quais você participa; respostas saem como você) ou de
    **bot** (precisa ser convidado nos canais; respostas saem como "Fidus")? Hoje: usuário.
    R: Precisa parecer o usuário respondendo isso é crucial.
12. **Fricção da regra de contaminação:** depois de ler e-mail/mensagem/evento, até "abre o bloco de notas" pede
    confirmação no mesmo comando. Aceitável? (Ler a própria memória não conta.)
    R: Não entendi o que seria se contaminar nesse caso, é meu robô ficar puto comprando uma briga minha?
13. **Chave do Windows Credential Manager:** limite de ~2,5 KB por credencial. O JSON do Google cabe, mas confirmar no PC.
    R: O que isso significa? Precisa para algo?
14. **Esc global enquanto o anel está aberto:** o anel não rouba o foco (para não atrapalhar quem está digitando), então
    uso um atalho global só enquanto ele existe. Aceitável? Alternativa: a janela toma o foco (Esc normal, mas interrompe
    a digitação).
    R: E se fizessemos um flutuante? Tipo o teams faz quando saimos da tela da reunião? Ou o que o chrome faz com o meet?
15. **Fechar o anel depois de 6 s parado** é configurável (`app.janela_inatividade_s` na 5B). Valor padrão ok?
    R: Fechar o anel é tudo ou ele parar? Tipo como se ele se calasse? Prq seria legal 30s, prq tem gente que pensa mais lento.
16. **Modelo local (Ollama):** está no escopo da v1 do PROJETO, mas nenhuma etapa pedida inclui o adaptador. Quer que eu
    faça (adaptador no formato OpenAI, restrito a ferramentas de leitura) depois da etapa 6?
    R: Pensei nele ser um alternativo ao antropic, ferramenta de leitura vc diz que ele seria limitado? E sim eu quero o ollama, parece que vc botou o gpt free só foi isso?
17. **Logo final:** os ícones atuais são provisórios (gerados por código). Quando tiver o SVG final, é só trocar
    `app/assets/` e rodar o empacotamento.
    R: Nesse link https://claude.ai/artifact/UynS7T7WVeX8VStgdSNK77?sk=h7t2vMr4W5pphwtTYjMe2A tem um primeiro box da linha 1 e da linha 2 com Clara Logo e Escuro Logo. E se desse para a pessoa em uma área de configuração escolher o ícone um dos 3 que é mostrado na área Ícone do app: escuro, claro e colorido que tá nesse link?
18. **Chave da API pela tela:** a tela "Modelo de IA" aceita colar a chave e a grava no cofre do Windows (nunca volta
    para a tela). O PROJETO só falava em `fidus secrets`. Manter as duas formas?
    R: Tipo ele pede falando vc da ctrl+v e ele absorve? Se sim parece legal.
19. **Controles desabilitados:** o que ainda não existe no núcleo (Local/Ollama, Outlook/Teams) aparece desabilitado
    com "em breve", em vez de escondido. Prefere esconder até existir?
    R: Perfiro que vc coloque pelo menos Ollama. Os outros vc deixa em breve
20. **Pasta de dados no Windows:** mudei o padrão para `%APPDATA%\Fidus` (o PROJETO falava em `~/.fidus`) e copio a antiga
    sem apagar. Concorda, ou prefere manter `~\.fidus` e só mudar o instalador?
    R: Deixa po, acho de boa.
21. **Assinatura de código:** o instalador sai sem assinatura (SmartScreen avisa). Vai comprar certificado? Se sim, qual
    (OV/EV) e onde guardar a senha (nunca no repositório).
    R: Prq comprar cecrtificado, precisa?
22. **Tamanho:** o núcleo congelado é grande (~550 MB em Linux, sem compressão). Aceitável, ou quer que eu corte
    dependências/modelos (por exemplo, trocar o Whisper embutido por baixar no primeiro uso, que já é o padrão)?
    R: Qual o melhor caminho? Siga.
23. **Tauri:** vale migrar do Electron para reduzir RAM/tamanho? Minha sugestão é só depois de medir no Windows (ver
    `docs/LANCAMENTO.md` seção 5).
    R: Então vamos aguardar.