# Protocolo núcleo <-> interface (versão 1)

O núcleo Python e a interface (Electron) conversam por **WebSocket em `127.0.0.1`**. Quem fala com o núcleo é o
**processo principal** do Electron; as janelas (renderers) só falam com o processo principal por IPC. O token nunca
chega a uma página.

Implementação: `fidus/core/bridge/` (núcleo) e `app/electron/bridge.ts` + `app/src/shared/protocol.ts` (interface).

## 1. Como a conexão começa

1. O Electron inicia o núcleo (`fidus daemon --stdin-watch`). O núcleo sobe o servidor **antes** de carregar o Whisper e
   escreve **uma linha** na saída padrão:

   ```
   FIDUS_READY {"port": 51234, "token": "<43 caracteres aleatórios>", "protocol": 1}
   ```

   A porta é aleatória e o **token é novo a cada inicialização** (`secrets.token_urlsafe(32)`). Só o processo pai lê essa
   saída: o token não vai para arquivo, log nem variável de ambiente.
2. O Electron abre `ws://127.0.0.1:<porta>/` e manda, como **primeiro quadro**, `{"type":"auth","token":"..."}`.
3. O núcleo responde `{"type":"ready","protocol":1,"snapshot":{...}}`. Se o token estiver errado, ou nenhum quadro de
   autenticação chegar em **5 s**, a conexão é fechada com o código **4401**. Nenhum comando é aceito antes da autenticação.

O servidor ainda: escuta **só em 127.0.0.1**; **recusa qualquer conexão com cabeçalho `Origin`** (páginas web não
conseguem se conectar, mesmo adivinhando a porta); aceita mensagens de até **1 MB**; não usa compressão.

Se o Electron morrer, o `stdin` do núcleo fecha e ele encerra sozinho (`--stdin-watch`), sem deixar processo órfão.

## 2. Formato

Todas as mensagens são JSON de um quadro de texto, um objeto com o campo `type`.

| Direção | `type` | Descrição |
| --- | --- | --- |
| UI -> núcleo | `auth` | primeiro quadro: `{"type":"auth","token":"..."}` |
| UI -> núcleo | `cmd` | comando: `{"type":"cmd","id":"7","name":"mute","args":{"value":true}}` |
| núcleo -> UI | `reply` | resposta a um comando: `{"type":"reply","id":"7","ok":true,"data":{...}}` ou `{"ok":false,"error":"..."}` |
| núcleo -> UI | `ready`, `state`, `level`... | eventos (seção 3); o nome do evento é o próprio `type` |

Mensagem inválida (JSON ruim, comando desconhecido, `args` que não é objeto) recebe `{"type":"reply","id":null,"ok":false,"error":"..."}`
e **a conexão continua**. Um comando que lança erro recebe `ok:false` com o motivo; nunca derruba a conexão.

## 3. Eventos (núcleo -> interface)

| Evento | Campos | Quando |
| --- | --- | --- |
| `ready` | `protocol`, `snapshot` | logo após autenticar |
| `status` | `core`: `starting`\|`ready`\|`error`, `message` | o núcleo terminou de carregar ou falhou |
| `state` | `state`: `idle`\|`listening`\|`thinking`\|`speaking`\|`muted`, `mic`: `passive`\|`recording`\|`paused`\|`muted`\|`off` | a cada mudança (parado, ouvindo, pensando, falando, silenciado) |
| `level` | `values`: 3 números de 0 a 1 | nível do microfone, **3 valores por bloco de 80 ms, ~37 por segundo**; só enquanto há interface conectada |
| `caption` | `role`: `user`\|`assistant`, `text`, `final` | legendas. O texto do assistente chega **em pedaços** (`final:false`) e fecha com `final:true` (texto vazio = "fechou o que já chegou") |
| `character` | `id`, `name`, `call`, `ring: {dark:[3 cores], light:[3 cores]}` | personagem ativo mudou |
| `confirm` | `id`, `text` | **confirmação pendente**; a interface mostra Sim/Não e responde com `confirm_reply` |
| `confirm_done` | `id` | a confirmação foi resolvida (pela tela ou por voz) |
| `model` | `provider`, `name`, `where` | modelo de IA em uso (ex.: `claude`, `claude-sonnet-5-5`, `Nuvem`) |
| `calls` | `enabled`, `until` (timestamp em segundos ou `null`) | "Escutar chamados" ligado/desligado ou pausado por um tempo |
| `settings` | `changed`: lista de chaves | configurações foram gravadas |
| `error` | `message` | erro que a interface pode mostrar |

O `snapshot` do `ready` tem: `status`, `message`, `state`, `mic`, `character` (ativo), `default_character`,
`characters` (os três, com `ring`), `model`, `calls`, `muted`. A interface pode ligar a qualquer momento e já recebe o
estado certo.

O nível de áudio **da voz do assistente** não existe no núcleo (a voz do sistema não expõe isso): a interface anima o
anel com um envelope sintético no estado `speaking`.

## 4. Comandos (interface -> núcleo)

| `name` | `args` | Efeito |
| --- | --- | --- |
| `get_state` | | devolve o snapshot |
| `mute` | `{value: bool}` | silencia (fecha o microfone de verdade) ou reativa |
| `pause` | `{minutes: 0..1440}` | pausa os chamados por um tempo; `0` retoma |
| `calls` | `{value: bool}` | "Escutar chamados" liga/desliga (o atalho de teclado continua) |
| `set_default_character` | `{id}` | personagem que responde ao atalho |
| `confirm_reply` | `{id, answer: bool}` | responde a uma confirmação pendente; `accepted:false` se o `id` já expirou |
| `get_settings` | | `settings.json` atual e a lista de chaves permitidas |
| `set_settings` | `{patch: {"chave.ponto": valor}}` | grava e aplica; **tudo ou nada**: se um valor for inválido, nada é gravado |
| `ping` | | `{pong:true}` |
| `quit` | | encerra o núcleo (o processo principal usa ao sair; **as páginas não podem enviá-lo**) |
| `simulate` | | só no modo `--simulado`: encena uma conversa (desenvolvimento) |

`set_settings` só aceita as chaves da tabela `fidus/core/bridge/settings_schema.py`, com tipo e faixa validados
(uma chave fora da tabela é recusada). A interface **não** consegue gravar chaves de API: segredos vão pelo
Gerenciador de Credenciais (`fidus secrets`).

## 5. Confirmações

Quando uma ação pede confirmação, o núcleo **fala a pergunta e envia o evento `confirm` ao mesmo tempo**. Vale a
**primeira** resposta: um clique (`confirm_reply`) ou o "sim/não" falado. A outra é cancelada e o núcleo envia
`confirm_done`. Sem interface conectada, só a voz (ou o teclado, se o núcleo roda em um terminal) responde. Ausência
de resposta, resposta confusa ou erro **nunca** aprovam: o padrão é negar.

## 6. Limites e segurança resumidos

- Só `127.0.0.1`, porta aleatória, token aleatório por inicialização, sem `Origin`, 5 s para autenticar, 1 MB por mensagem.
- O renderer não tem Node, não vê o token e só envia, por IPC, comandos de uma lista permitida (`quit` fora dela); o processo
  principal ainda confere que o pedido veio de uma página do próprio app.
- Conteúdo de e-mail, mensagem e evento **não** viaja por este canal como ordem: as legendas são só texto exibido.

## 7. Testar

```powershell
uv run pytest tests/test_bridge.py                      # servidor, autenticação, protocolo, núcleo simulado
cd app; npm test                                        # cliente, modelo, tela e protocolo contra o núcleo simulado real
uv run fidus daemon --simulado                          # sobe o núcleo simulado (imprime a linha FIDUS_READY)
```
