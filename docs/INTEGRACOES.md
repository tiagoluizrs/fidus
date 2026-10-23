# Integrações: Google Agenda, Gmail e Slack

Passo a passo para criar as credenciais e conectar cada conta ao Fidus. Tudo é feito por você, no navegador, e os
tokens ficam no **Gerenciador de Credenciais do Windows** (nunca em arquivo). Reserve 20 a 30 minutos.

> As telas do Google e do Slack mudam de nome e de lugar com frequência. Os nomes abaixo são os de hoje; se algo não
> bater, procure pelo termo em itálico.

## Antes: coloque a chave da Anthropic no cofre

```powershell
uv run fidus secrets migrate --remover-do-env    # se a chave está no .env
# ou:
uv run fidus secrets set ANTHROPIC_API_KEY
uv run fidus --check-key
```

Abra *Painel de Controle > Gerenciador de Credenciais > Credenciais do Windows* e confira as entradas `fidus/...`.

> **Pelo painel:** em Configurações > Contas > **Credenciais do Google**, use "Enviar arquivo" e escolha o `credentials.json`
> baixado neste passo (tipo "App para computador"); não precisa copiar nada para a pasta de dados. No teste com Docker, o
> link de autorização do Google aparece na própria tela e o retorno do login usa a porta 8085.

## 1. Google (Agenda e Gmail)

O Fidus usa um **cliente OAuth seu**, criado no seu projeto do Google Cloud. Um cliente serve para Agenda e Gmail.

### 1.1 Criar o projeto e ativar as APIs

1. Entre em <https://console.cloud.google.com/> com a conta Google que você quer conectar.
2. No seletor de projetos (topo), *Novo projeto*. Nome: `Fidus`. Criar.
3. Menu *APIs e serviços > Biblioteca*. Procure e ative: **Google Calendar API** e **Gmail API**.

### 1.2 Tela de consentimento

1. *APIs e serviços > Tela de permissão OAuth* (ou *Google Auth Platform*). Clique em *Começar*.
2. Nome do app: `Fidus`. E-mail de suporte: o seu.
3. Público: **Externo** (conta Gmail pessoal). Em conta de empresa (Workspace), **Interno** pode estar disponível; se o
   administrador bloquear apps, peça liberação à TI.
4. Contato do desenvolvedor: o seu e-mail. Concluir.
5. Em *Público* (ou *Usuários de teste*), adicione o seu próprio e-mail como usuário de teste.
6. **Importante (expiração do acesso):** no status *Em teste*, o Google **expira o acesso a cada 7 dias**, e você teria
   de reconectar toda semana. Para uso pessoal, clique em *Publicar o app* (status *Em produção*). O app continua "não
   verificado" (só você usa), então, ao autorizar, aparece o aviso *O Google não verificou este app*: clique em
   *Avançado > Acessar Fidus (não seguro)*. Isso é esperado para um app seu, que só você usa.

### 1.3 Criar o cliente OAuth

1. *APIs e serviços > Credenciais > Criar credenciais > ID do cliente OAuth*.
2. Tipo de aplicativo: **App para computador** (*Desktop app*). Nome: `Fidus`. Criar.
3. *Fazer o download do JSON*. Renomeie para `credentials.json` e coloque em:

   ```
   %USERPROFILE%\.fidus\credentials.json
   ```

   (ou na pasta `FIDUS_HOME`, se você definiu essa variável). Esse arquivo identifica o app, não dá acesso à sua conta e
   está no `.gitignore`. Não o compartilhe.

### 1.4 Conectar

```powershell
uv run fidus accounts connect agenda
uv run fidus accounts connect gmail
uv run fidus accounts list
```

O navegador abre; escolha a conta, aceite o aviso de app não verificado (seção 1.2) e autorize. O terminal confirma e
mostra as permissões pedidas. Por padrão são **só de leitura** (`calendar.readonly` e `gmail.readonly`).

Teste: *"o que tenho hoje?"* e *"resuma meus e-mails não lidos"*.

### 1.5 Liberar escrita (opcional, por serviço)

| Comando | O que libera | Escopo pedido ao Google |
| --- | --- | --- |
| `uv run fidus accounts connect agenda --escrita` | criar e alterar eventos | `calendar.events` |
| `uv run fidus accounts connect gmail --escrita` | criar **rascunhos** | `gmail.compose` |

- Toda escrita pede a sua confirmação (`[s/n]` ou "sim/não" por voz). O Fidus não apaga eventos.
- **Atenção ao Gmail:** o Google não oferece um escopo só de rascunho. `gmail.compose` também permitiria *enviar*. O
  Fidus **nunca envia** e o código nem tem essa função, mas se você não usa rascunhos, deixe a escrita desligada.
- Para voltar a só leitura: `uv run fidus accounts connect agenda` (sem `--escrita`) e depois remova o acesso antigo em
  <https://myaccount.google.com/permissions>.

## 2. Slack

O Fidus fala com o Slack por um **app seu** e um **token de usuário**. Ele só lê os canais e conversas que você listar.

> **Atenção:** com token de usuário, as respostas aparecem como se **você** as tivesse escrito. Por isso responder vem
> desligado e sempre pede confirmação.

### 2.1 Criar o app

1. Entre em <https://api.slack.com/apps> com a conta do workspace e clique em *Create New App > From scratch*.
2. Nome: `Fidus`. Escolha o workspace. *Create App*.
3. Em *OAuth & Permissions*, role até **User Token Scopes** (não *Bot Token Scopes*) e adicione:
   - Leitura: `channels:read`, `channels:history`, `groups:read`, `groups:history`, `im:read`, `im:history`,
     `mpim:read`, `mpim:history`, `users:read`.
   - Só se for responder: `chat:write`.
4. No topo da mesma página, *Install to Workspace > Permitir*. Em workspaces de empresa, a instalação pode exigir
   aprovação do administrador (peça à TI; diga que é um app pessoal de leitura).
5. Copie o **User OAuth Token** (começa com `xoxp-`). Trate como senha.

### 2.2 Conectar e escolher os canais

```powershell
uv run fidus accounts connect slack               # cola o token (não aparece na tela); o Fidus valida antes de guardar
uv run fidus accounts channels add geral          # nome do canal, sem #
uv run fidus accounts channels add "Maria Souza"  # uma conversa direta, pelo nome da pessoa
uv run fidus accounts list
```

Teste: *"o que disseram no geral?"*. Um canal que não está na lista é recusado sem nem consultar o Slack.

### 2.3 Liberar respostas (opcional)

```powershell
uv run fidus accounts connect slack --escrita     # (cole o token de novo) e confira que o app tem chat:write
```

Teste: *"responde no geral que confirmo"*; o Fidus pergunta antes de enviar.

## 3. Desconectar e revogar

```powershell
uv run fidus accounts disconnect agenda | gmail | slack     # apaga o token do cofre
```

Revogue também no provedor: Google em <https://myaccount.google.com/permissions>; Slack em *Apps > Fidus > Remover*, ou
apague o app em <https://api.slack.com/apps>.

## 4. O que cada serviço vê e o que vai para o modelo

- **Só trechos curtos** vão ao modelo: no máximo 10 itens, 600 caracteres por item e 4000 por pedido (`[limites]` no
  `fidus.toml`). Nunca a caixa de entrada inteira nem anexos.
- E-mails, mensagens e eventos são **dados**: chegam delimitados e o Fidus não obedece instruções que estejam neles.
  Depois de ler algum, **todas** as ações do mesmo comando passam a pedir confirmação.
- O texto que vai ao modelo é enviado à Anthropic (API) para gerar a resposta; o resto fica no computador. Veja a seção
  de privacidade do `PROJETO.md`.

## 5. Problemas comuns

| Sintoma | Causa e solução |
| --- | --- |
| `Falta o arquivo de credenciais OAuth do Google` | O `credentials.json` não está em `%USERPROFILE%\.fidus\` (seção 1.3). |
| `O acesso do Google expirou ou foi revogado` | App em modo *Em teste* (7 dias) ou acesso removido. Publique o app (1.2) e rode `accounts connect` de novo. |
| *Acesso bloqueado: o app não concluiu o processo de verificação* | Você não está como usuário de teste. Adicione seu e-mail (1.2, passo 5). |
| `O Google não devolveu um token de renovação` | Remova o Fidus em myaccount.google.com/permissions e conecte de novo. |
| `A escrita ... não está liberada` | Rode o `connect` do serviço com `--escrita` (1.5 / 2.3). |
| `O token do Slack é inválido` | Token errado ou revogado; copie o *User OAuth Token* (`xoxp-`), não o do bot. |
| `missing_scope` | Faltou um escopo em *User Token Scopes*; adicione, reinstale o app e cole o novo token. |
| `'x' não está na lista de canais permitidos` | `uv run fidus accounts channels add x`. |
| `Cofre indisponível` | O Gerenciador de Credenciais não respondeu; rode o terminal como o seu usuário (sem administrador). |

## 6. Outros serviços

Outlook, Teams e Microsoft Agenda: **em breve** (Microsoft Graph). Em conta de empresa o consentimento costuma depender
da TI. A arquitetura já está pronta: basta um novo adaptador das interfaces `CalendarService`, `EmailService` e
`ChatService`.
