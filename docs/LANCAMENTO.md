# Lançamento: gerar e validar o instalador do Fidus (Windows 10/11)

O instalador é um `Fidus-Setup-<versão>.exe` (NSIS, instalação por usuário, sem pedir administrador). Ele leva dentro o app
Electron e o núcleo Python empacotado (`resources\core\fidus-core.exe`, PyInstaller modo onedir).

## 1. Gerar

Pré-requisitos no PC de build: Windows 10/11 x64, [uv](https://docs.astral.sh/uv/), Node 20+ e Git.

```powershell
git clone https://github.com/tiagoluizrs/fidus; cd fidus
.\packaging\build_core.ps1          # gera app\resources-core\fidus-core\fidus-core.exe (uv sync --group build + PyInstaller)
cd app; npm install
npm run dist                        # gera app\release\Fidus-Setup-0.1.0.exe
```

- `build_core.ps1` falha se o `.exe` do núcleo não aparecer. O `.spec` está em `packaging/fidus-core.spec` e coleta o
  pacote `fidus` inteiro (os imports são preguiçosos), os personagens padrão (`fidus/defaults`) e os dados de
  `openwakeword`, `faster_whisper`, `googleapiclient` e `certifi`.
- Antes de instalar em outro PC, rode no PC de build: `app\resources-core\fidus-core\fidus-core.exe selftest`. Ele importa
  as bibliotecas pesadas (voz, wake word, SQLCipher, Google...) e confere os dados empacotados; sai com código 1 se
  faltar algo. **Esse teste só tem valor no Windows** (em Linux faltam PortAudio e X por natureza).
- `npm run pack:dir` gera só a pasta (`release\win-unpacked`), sem instalador, para testar rápido.
- Sem publicação: `build.publish` é `null`, então nada é enviado a lugar nenhum e não há atualização automática.

## 2. O que o instalador faz (e não faz)

- Instala em `%LOCALAPPDATA%\Programs\Fidus` (o usuário pode trocar a pasta), cria o atalho no Menu Iniciar (não cria na
  área de trabalho) e registra o desinstalador.
- **Não apaga os dados do usuário ao desinstalar** (`deleteAppDataOnUninstall: false`): memória, personagens,
  configurações e log ficam em `%APPDATA%\Fidus`. Quem quiser tudo apagado usa Configurações > Privacidade > Apagar tudo
  **antes** de desinstalar, ou apaga a pasta à mão. As credenciais (chave da API, tokens) ficam no Gerenciador de
  Credenciais do Windows; para removê-las: Configurações > Modelo de IA / Contas > Desconectar, ou `fidus secrets`.
- "Iniciar junto com o Windows" é uma configuração do app (Configurações > Geral), desligada por padrão; só vale no app
  instalado.

## 3. Dados do usuário

| O quê | Onde |
| --- | --- |
| Memória, personagens, configurações, log, banco | `%APPDATA%\Fidus` |
| Cache do Electron | `%APPDATA%\Fidus\app` |
| Chave da API, tokens do Google/Slack | Gerenciador de Credenciais do Windows |
| Modelos de palavra de ativação | `models\wakewords` (ao lado do app) ou como no `fidus.toml` |

Na primeira execução depois de atualizar de uma versão antiga, o núcleo **copia** `~\.fidus` para `%APPDATA%\Fidus`
(só se a nova ainda não tem dados). A pasta antiga **não é apagada**; o usuário decide quando removê-la.
`FIDUS_HOME` continua valendo para quem quiser outra pasta.

## 4. Checklist: instalação limpa (Windows 11 e 10, sem Python nem Node instalados)

Idealmente numa máquina virtual nova. Marque cada item e anote o que falhar.

- [ ] Rodar `Fidus-Setup-0.1.0.exe`: o SmartScreen avisa "editor desconhecido" (esperado, o instalador não é assinado,
      ver seção 6); "Mais informações > Executar assim mesmo".
- [ ] Instalar sem administrador; o Fidus abre sozinho no fim e o ícone aparece na bandeja.
- [ ] Nenhuma janela de console preta aparece (o núcleo roda escondido).
- [ ] Gerenciador de Tarefas: aparecem `Fidus` e `fidus-core`; nada de `python.exe`.
- [ ] Bandeja > Configurações abre; Voz lista as vozes e o microfone; o aviso de permissão do microfone aparece se estiver bloqueada.
- [ ] Colar a chave da Anthropic em Modelo de IA; "ei Alfred, que horas são" (ou o atalho) responde em voz.
- [ ] `%APPDATA%\Fidus` foi criada; com uma pasta `~\.fidus` antiga, os dados foram copiados.
- [ ] Ligar "Iniciar junto com o sistema", reiniciar o Windows: o Fidus volta sozinho, sem janela.
- [ ] Abrir o app duas vezes: a segunda instância não faz nada (uma só).
- [ ] Encerrar o Fidus pela bandeja: `fidus-core` some do Gerenciador de Tarefas (sem processo órfão).
- [ ] Encerrar o Fidus pelo Gerenciador de Tarefas: o núcleo também encerra em poucos segundos.
- [ ] Desinstalar (Configurações do Windows > Aplicativos): a pasta de instalação some, `%APPDATA%\Fidus` **permanece**.
- [ ] Reinstalar: memória e personagens continuam lá.
- [ ] Antivírus/Defender: nenhum alerta ao instalar nem ao abrir (PyInstaller às vezes gera falso positivo; ver seção 6).
- [ ] Rodar `fidus-core.exe selftest` na pasta instalada (`resources\core`): tudo "ok".

## 5. Alternativas ao Electron (sem executar nada aqui)

A interface hoje é só bandeja + anel + configurações, e o núcleo é separado. Isso permite trocar o casco depois:

| Opção | Ganho | Custo |
| --- | --- | --- |
| **Electron** (atual) | pronto, Canvas e React já funcionam, o mais testado | instalador grande (~100 MB só do Chromium) e ~250 MB de RAM em repouso (ver `MEDICOES.md`) |
| **Tauri 2** | instalador pequeno (WebView2 do Windows) e menos RAM | precisa de Rust; o processo principal (`electron/*.ts`) teria de ser reescrito em Rust; WebView2 muda o Canvas/CSP; janela do anel transparente exige ajuste |
| **Janela nativa mínima** (Python, Qt/pywebview) | um processo só | perde a bandeja e a janela do anel prontas |

Sugestão: manter Electron até haver motivo concreto (tamanho ou RAM). Se a RAM incomodar, o primeiro passo barato é
destruir também o processo de renderização das Configurações quando fechadas (já é assim) antes de pensar em Tauri.

## 6. Pendências de lançamento

- **Assinatura de código:** o instalador não é assinado, então o SmartScreen avisa. Para assinar é preciso um
  certificado (EV ou OV) e configurar `win.certificateFile`/`certificatePassword` (por variável de ambiente, nunca no
  repositório). Decisão do dono do projeto.
- **Falso positivo de antivírus:** executáveis PyInstaller às vezes são marcados. Mitigações: modo onedir (já usado),
  assinatura e enviar o arquivo à análise do Defender se acontecer.
- **MSIX (Microsoft Store / instalação corporativa):** fora do escopo do instalador NSIS. Quando fizer sentido, é um
  alvo separado do electron-builder (`win.target: appx`) que exige identidade de publisher e tem restrições (a pasta de
  instalação é somente leitura, o que combina com o `%APPDATA%`, mas o registro de início automático e o acesso ao
  microfone mudam). Deixar para uma etapa própria.
- **Ícone/logo final:** os ícones atuais são provisórios (`app/assets`, `app/scripts/make_icons.py`); trocar antes do
  lançamento público.
- **Tamanho:** o núcleo congelado ocupa ~550 MB descompactado em Linux (numpy, onnxruntime, ctranslate2, Google API).
  O instalador comprimido será menor; medir no Windows e, se preciso, cortar dependências (por exemplo, excluir
  bibliotecas que não são usadas em tempo de execução).
- **Modelos:** o modelo do Whisper baixa no primeiro uso (precisa de internet); os modelos de palavra de ativação não
  vão no instalador (são pessoais; ver `docs/WAKEWORDS.md`).
