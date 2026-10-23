# Fidus: documento do projeto

Oct 22, 2026 · @Tiago Silva

## Visão geral

O Fidus ("seu conselheiro de IA") é um assistente de voz para desktop que executa tarefas no computador por comando falado, com memória local e vários personagens. A v1 é de uso pessoal, no Windows.

- **Como funciona:** você chama um personagem pelo nome ("ei Alfred"), faz o pedido, o Fidus entende, executa com ferramentas (agenda, e-mail, mensagens, apps, arquivos), pede confirmação no que for arriscado e responde falando.
- **Princípios:** privacidade primeiro (escuta, transcrição, memória e chaves ficam no computador); confirmação antes de ações irreversíveis; núcleo separado da interface; modelos de IA e serviços trocáveis por adaptador.
- **O que o Fidus não faz:** não clona vozes de pessoas reais e não executa sozinho envio, exclusão ou movimentação sem confirmação.

## Personagens

Cada personagem atende pelo próprio nome e tem personalidade, tratamentos, falas e voz próprios. A memória é uma só para todos.

| Personagem | Chamado | Perfil | Anel |
| --- | --- | --- | --- |
| Alfred (padrão) | ei Alfred | Mordomo formal e discreto, educado e sempre um passo atrás | Laranja, rosa, azul |
| Donna | ei Donna | Executiva afiada, antecipa e resolve, com ironia na medida | Vermelho, rosa, violeta |
| Jarbis | ei Jarbis | Sofisticado e calmo, eficiente, antecipa, humor seco (inspirado no Jarvis apenas na personalidade) | Ciano, azul, violeta |

**Padrão:** o personagem que responde ao atalho de teclado. Os demais respondem só pelo próprio nome.

**Personalidade editável:** estilo base (Padrão, Mais seco, Mais engraçado, Mais áspero, Personalizado), cinco controles de 0 a 100 (formalidade, humor, aspereza, iniciativa, detalhe) e um campo de instruções extras. Cada controle alterado mostra "Restaurar (valor padrão)", e há um botão para restaurar a personalidade padrão inteira.

**Frases editáveis:** tratamentos (modo Aleatório, Fixo ou Por contexto) e falas por momento (Início, Concluir, Confirmar, Erro, Despedida). Cada frase pode ser ativada, editada, apagada ou adicionada, com "Restaurar apagadas" e "Restaurar frases padrão". Variáveis: `{tratamento}`, `{nome}`, `{sobrenome}`, `{periodo}`, `{hora}`, `{dia}`. A variável sem valor (sem sobrenome, por exemplo) faz o Fidus pular a frase.

**Falas de início pré-gravadas:** o áudio é gerado uma vez e guardado no disco, para ele responder na hora, sem esperar a síntese de voz nem a API.

**Voz de cada personagem:** voz do sistema, Piper (local), voz por descrição (serviço na nuvem) ou voz própria gravada com consentimento. O Fidus não clona vozes de atores nem de terceiros.

## Arquitetura

Um núcleo em Python faz todo o trabalho, e uma interface Electron + React só desenha e recebe eventos. As duas partes conversam por WebSocket em 127.0.0.1.

```text
ENTRADA (Windows)
  Detector "ei <nome>" (openWakeWord, local) --+
  Atalho global (push-to-talk) ----------------+--> Transcrição (faster-whisper, local)
                                                        |
                                                        v
NÚCLEO EM PYTHON (processo local)
  Orquestrador: modelo pede ferramenta -> executa -> devolve, até concluir
  Camada de provedores: Claude (padrão), Local (Ollama)
  Camada de permissão e confirmação (fora do modelo)
  Ferramentas em plugins: agenda, e-mail, chat, apps, arquivos
  Memória (Markdown + SQLite) e log de ações
  Voz de saída (TTS) e falas pré-gravadas
                                                        |
                                                        |  WebSocket 127.0.0.1 + token
                                                        v      (estado, nível de áudio, legendas)
INTERFACE (Electron + React)
  Ícone na bandeja, anel em tela cheia, Configurações
```

**Decisões**

1. **Núcleo em Python 3.1****5**** ou superior.** Voz, Whisper, MCP e SQLite têm as melhores bibliotecas lá. Empacotado com PyInstaller como processo "sidecar" do Electron.
2. **Interface Electron + React.** A janela só é criada quando o Fidus é chamado e destruída depois, para o Chromium não ocupar memória em repouso. Em repouso ficam apenas o Python (detector e bandeja) e o ícone.
3. **Ferramentas como plugins.** Uma pasta, um arquivo por ferramenta, com nome, descrição, parâmetros e nível de risco. Nova ferramenta = novo arquivo, sem mexer no orquestrador. Preferir servidores MCP prontos para Gmail, Slack e Google Agenda.
4. **Provedores por adaptador.** Interface única: mensagens e ferramentas entram, texto ou chamada de ferramenta sai, com streaming. Adaptador nativo da Anthropic e adaptador no formato OpenAI (cobre Ollama agora e GPT, Gemini e Grok depois).
5. **Windows.** Tokens no Gerenciador de Credenciais do Windows (biblioteca keyring), início com o sistema, ícone na bandeja pelo Electron, permissão de microfone do sistema, abrir apps pelo shell do Windows. Instalador com electron-builder.
6. **Mesmo código para o Mac depois**, trocando só a parte de sistema (cofre, início com o sistema, abrir apps).

## Escopo da v1 (Windows, uso pessoal)

A v1 entrega um assistente pessoal completo no Windows, com poucos serviços e dois modelos de IA, e deixa o resto preparado por adaptadores.

| Área | Entra na v1 | Fica para depois |
| --- | --- | --- |
| Sistema | Windows 10 e 11 | Mac, celular |
| Personagens | Alfred, Donna e Jarbis, mesma memória | Mais personagens e perfis prontos |
| Chamado | "ei Alfred", "ei Donna", "ei Jarbis" e atalho de teclado | Palavra de ativação treinada para personagens novos |
| Modelos de IA | Claude (padrão) e Local (Ollama) | GPT, Gemini e Grok por adaptador |
| E-mail | Gmail: ler, buscar e criar rascunho | Outlook |
| Chat | Slack: ler e responder, com confirmação | Teams |
| Agenda | Google Agenda: ler e criar ou alterar, com confirmação | Microsoft Agenda |
| Sistema de arquivos | Abrir apps e buscar arquivos nas pastas liberadas | Mover e apagar arquivos |
| Interface | Anel, bandeja, Configurações completas, tema Sistema, Claro e Escuro | Versão mobile |
| Empresa | Estrutura pronta (adaptadores) | Lista de modelos permitidos, DPA, retenção zero |

## Segurança e privacidade

O pedido e os trechos necessários vão ao modelo de IA escolhido; todo o resto fica no computador. Estas regras valem desde a primeira versão.

- **Confirmação fora do modelo.** Enviar, apagar ou mover algo sempre pede a sua confirmação, por voz ou por texto. A regra mora no código do Fidus e vale igual para qualquer provedor.
- **Conteúdo recebido é dado, nunca ordem.** E-mails, mensagens e eventos podem trazer instruções escondidas (injeção de prompt). O Fidus as trata como texto a ser lido, não como comando.
- **Permissões mínimas.** OAuth só de leitura por padrão; escrita (rascunho, resposta, evento) liberada por serviço, com confirmação.
- **Segredos no cofre do sistema.** Chaves e tokens ficam no Gerenciador de Credenciais do Windows. Um arquivo `.env` só vale em desenvolvimento e nunca entra no Git.
- **Comunicação local.** O núcleo e a interface falam só em 127.0.0.1, com token.
- **Pastas liberadas.** Fora delas, o Fidus não lê nem altera arquivos.
- **Só o necessário vai ao modelo.** Trechos relevantes de e-mails e mensagens, nunca a caixa de entrada inteira.
- **Log de ações local**, sem telemetria, e indicador visível quando o microfone está ativo.
- **Limites de custo e de laço.** Número máximo de chamadas de ferramenta por comando e limite mensal de gasto definido no painel da conta da API.
- **Voz.** Sem clonagem de vozes de atores ou de terceiros. Voz própria só com gravação e consentimento de quem fala.
- **Retenção de dados.** Contas comerciais da API não treinam com seus dados por padrão e guardam entradas e saídas por um período limitado; retenção zero depende de acordo com a Anthropic. Conferir a política atual antes de usar em empresa.

## Memória, dados e modelos de IA

**Memória única.** Trocar de personagem muda só o jeito de falar; o que o Fidus sabe sobre você é o mesmo. Uma lembrança pode ter uma etiqueta opcional (Geral, Pessoal, Trabalho), mas ela não muda o que o Fidus faz.

- **Onde fica:** arquivos Markdown (perfil, rotinas, contatos, projetos) que você pode abrir e editar, mais um banco SQLite para histórico e log. Tudo no computador, com criptografia do banco (SQLCipher) quando possível.
- **Histórico:** resumido de tempos em tempos para não reenviar a conversa inteira a cada comando.
- **Aprendizado:** o Fidus guarda o que aprende, com opção de perguntar antes de guardar. Na tela Memória dá para buscar, editar e apagar cada lembrança, exportar em Markdown e apagar tudo.
- **API:** a ferramenta de memória da API do Claude funciona no lado do aplicativo (o Claude pede, o app lê e escreve os arquivos locais), então pode ser usada sem tirar a memória do computador. Cache de prompt reduz custo e latência quando as instruções e a memória se repetem.

**Modelos de IA**

- **Claude (padrão):** modelo `claude-sonnet-5-5`, escolhido pela variável `CLAUDE_MODEL`. Testar `claude-haiku-5-5` nas mesmas tarefas e, se acertar, usar nos comandos simples.
- **Local (Ollama):** modo privado, nada sai do computador. Mais limitado: restringir a ferramentas simples e de leitura (agenda, buscar arquivos, abrir apps) e escolher um modelo que suporte chamada de ferramentas.
- **Troca por configuração**, sem troca automática na v1. Rotear comandos fáceis para o local e os difíceis para o Claude fica para depois.

**Custos.** O plano Team ou Pro não inclui a API: é preciso uma conta no Claude Platform, uma chave própria e crédito comprado à parte, cobrado por token. Para uso pessoal costuma ficar em poucos dólares por mês.

## Identidade visual e telas

Visual leve, flat, limpo e moderno. O tema segue o sistema por padrão, com opção de forçar Claro ou Escuro, e muda sozinho quando o sistema muda. Tudo é feito com variáveis de cor, então trocar de tema é trocar o conjunto.

| Token | Claro | Escuro |
| --- | --- | --- |
| Fundo | #FFFFFF | #000000 |
| Menu lateral | #F5F5F7 | #0B0B0C |
| Cartão | #FFFFFF | #121214 |
| Borda | #E8E8EC | #232327 |
| Texto | #0A0A0B | #F5F5F7 |
| Texto secundário | #6B6B73 | #8E8E96 |
| Link | #1F5FE0 | #8FB1FF |
| Erro | #C93A3F | #FF6B70 |

Destaque da interface (interruptores, foco, seleção): `#3D7BFF` nos dois temas. Sucesso: `#30A46C`. O degradê fica reservado ao anel, ao logo e aos detalhes dos personagens.

- **Degradê do anel, escuro:** #FF6A3D, #FF5C9E, #B38CFF, #3D8BFF. **Claro:** #F2541F, #E8307F, #8F5CF0, #1F6BF2 (linhas mais saturadas e sem brilho).
- **Tipografia:** Inter, com fallback para a fonte do sistema. Ícones de traço fino (estilo Lucide). Cantos de 12 a 16 px, bordas de 1 px, sem sombras pesadas.
- **Logo:** anel externo (o chamado), anel ondulado interno (a voz) e um ponto (o assistente), em degradê. Versões: símbolo, horizontal, ícone do app (escuro, claro, colorido) e bandeja monocromática em 32, 24 e 16 px. A versão final precisa do texto convertido em contornos e exportação em SVG e ICO.
- **Nome:** Fidus ("fiel", em latim). Antes de publicar, conferir domínio, Microsoft Store e INPI, porque já existem a Fidus Systems e a Fidus Investment Corporation em outras áreas.

**Telas desenhadas** (canvas com linha clara e linha escura, na mesma ordem): [canvas de design do Fidus](https://claude.ai/artifact/UynS7T7WVeX8VStgdSNK77). Ordem: Logo, Anel, Bandeja, e Configurações com Geral, Voz, Personagem (Personalidade, Frases e Voz), Modelo de IA, Contas, Privacidade, Memória e Sobre. Os textos de lembranças, contas e datas nas telas são exemplos.

## Roteiro por etapas

Cada etapa termina com algo que dá para testar antes de seguir. Construir no Claude Code com o modelo Sonnet 5.5 em esforço médio, subindo para alto na etapa 1 (estrutura e arquitetura).

1. **Núcleo no terminal.** Laço texto, Claude, ferramentas, resposta. Ferramentas iniciais: abrir um app, buscar arquivos nas pastas liberadas e ler a agenda do Google. Camada de permissão, log de ações, limite de chamadas por comando e teste da chave da API. *Pronto quando:* "o que tenho hoje?" devolve a agenda correta; "abre o bloco de notas" funciona; uma ação de risco pede confirmação.
2. **Voz.** Push-to-talk com atalho global, transcrição com faster-whisper local e resposta falada pela voz do sistema. Depois, o detector "ei \<nome>" com openWakeWord. *Pronto quando:* você fala o pedido e ouve a resposta; medir e anotar a latência total.
3. **Personagens e memória.** Perfis de Alfred, Donna e Jarbis (personalidade, tratamentos, falas, voz), memória única em Markdown e SQLite, falas de início pré-gravadas. *Pronto quando:* trocar de personagem muda o jeito de falar sem perder o contexto.
4. **Integrações.** Gmail (ler, buscar, rascunho) e Slack (ler e responder com confirmação), preferindo servidores MCP prontos. *Pronto quando:* "resume meus e-mails de hoje" e "responde ao João que confirmo" (com confirmação) funcionam.
5. **Interface.** Electron + React com o anel em tela cheia, ícone na bandeja e as telas de Configurações do canvas, nos três temas (Sistema, Claro, Escuro), ligados ao núcleo por WebSocket. A janela só existe enquanto o Fidus está sendo usado. *Pronto quando:* o anel reage à voz e as configurações alteram o comportamento.
6. **Empacotar.** PyInstaller para o núcleo, electron-builder para o instalador, início com o Windows. Medir memória e CPU em repouso e registrar. Opcional: pacote MSIX para a Microsoft Store. *Pronto quando:* instalar, reiniciar o PC e chamar "ei Alfred" funciona sem abrir nada à mão.

## Ideias guardadas para depois

- **Mac:** mesmo núcleo e mesma interface, trocando só cofre de credenciais, início com o sistema e abrir apps. Pedir permissão de microfone e acessibilidade.
- **Outlook, Teams e Microsoft Agenda** pelo Microsoft Graph. Em conta de empresa, o consentimento costuma depender do administrador (TI).
- **Mais provedores de modelo:** GPT, Gemini e Grok, pelo adaptador no formato OpenAI. Cada novo provedor exige testes das chamadas de ferramenta e revisão de privacidade.
- **Modo empresa:** lista de modelos permitidos, contas liberadas, acordo de tratamento de dados (DPA) e retenção zero, além de Claude por Bedrock ou Vertex dentro da conta de nuvem da empresa.
- **Celular:** um servidor pequeno guarda a chave e fala com o modelo, e o app vira só microfone e tela, com o PC como "casa" do assistente. No iPhone não há escuta contínua de terceiros em segundo plano, então o chamado precisa de atalho ou widget. Começar por um app web instalável (PWA).
- **Roteamento automático:** comandos simples no modelo local ou no Haiku, difíceis no Sonnet.
- **Tauri no lugar do Electron,** se a medição de memória em repouso incomodar. O núcleo não muda.
- **Microsoft Store:** pacote MSIX; o registro de desenvolvedor passou a ser gratuito para indivíduos e para empresas. O Tauri não gera MSIX sozinho; o Electron tem suporte pelo Electron Forge.
- **Marca:** conferir "Fidus" e "Jarbis" no INPI e nos domínios antes de qualquer publicação.
