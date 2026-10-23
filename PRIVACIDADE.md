# Política de Privacidade do Fidus

Última atualização: 23/10/2026

O Fidus é um assistente de voz de código aberto que roda **no seu computador**. Esta página explica quais dados ele usa
e para onde vão. O projeto é pessoal e sem fins comerciais. Contato: abra uma *issue* em
<https://github.com/tiagoluizrs/fidus/issues>.

## O que fica só no seu computador
- Memória, histórico de conversas, personagens, configurações e o registro de ações.
- A sua voz e a transcrição (o reconhecimento de fala roda localmente).
- Chaves e tokens (Anthropic, Slack, Google, ElevenLabs): guardados no Gerenciador de Credenciais do Windows.
- O Fidus **não tem telemetria**: não envia estatísticas de uso nem relatórios de erro a ninguém.

## O que sai do computador, e só quando você usa
- **Modelo de IA na nuvem (Claude, da Anthropic):** o seu pedido e os trechos necessários para respondê-lo (por exemplo, o
  conteúdo de um e-mail que você pediu para resumir). Com o modelo **local (Ollama)** nada sai da máquina.
- **Modelo de IA na nuvem (Gemini, do Google), opcional:** o mesmo conteúdo, se você escolher o Gemini. No plano grátis do
  Gemini, o Google pode usar o conteúdo enviado para melhorar os produtos dele; leia a política do Google antes de escolher.
- **Voz na nuvem (ElevenLabs), opcional:** o texto que o assistente fala e, se você criar a "sua própria voz", a gravação
  que você fez com o seu consentimento. A conta é sua.
- **Google (Gmail e Agenda), opcional:** o Fidus pede acesso à **sua** conta por meio do login do Google (OAuth) e guarda só um
  token de renovação no seu computador. Ele lê e-mails e eventos para responder aos seus pedidos e só cria rascunhos ou
  altera eventos se você liberar, com confirmação a cada ação. O Fidus **nunca envia e-mails sozinho**.
- **Slack, opcional:** usa o token que você fornece, para ler os canais que você permitir e responder, com a sua confirmação.

## Uso das informações da sua conta Google
O uso e a transferência das informações recebidas das APIs do Google seguem a
[Política de Dados do Usuário dos Serviços de API do Google](https://developers.google.com/terms/api-services-user-data-policy),
incluindo os requisitos de Uso Limitado. Os dados do Gmail e da Agenda são usados apenas para atender aos seus pedidos
dentro do Fidus; não são vendidos, compartilhados com terceiros nem usados para publicidade ou para treinar modelos.
Quando você pede algo que envolve um e-mail ou evento, o conteúdo necessário é enviado ao modelo de IA que você escolheu
(seção acima) apenas para produzir a resposta.

## Seus direitos (LGPD)
Em Configurações > Privacidade e Memória você pode ver, editar, exportar e apagar o que o Fidus guarda, e desconectar
qualquer conta. Desconectar o Google remove o token do seu computador; para revogar também no Google, use
<https://myaccount.google.com/permissions>. Desinstalar o Fidus **não** apaga os seus dados (ficam em `%APPDATA%\Fidus`);
use "Apagar tudo" antes, se quiser.

## Segurança
Conteúdo de e-mails e mensagens é tratado sempre como dado, nunca como ordem. Ações de risco pedem a sua confirmação, e
as regras de permissão ficam fora do modelo de IA.

## Mudanças
Esta política pode mudar junto com o projeto; a versão vigente é sempre a deste arquivo no repositório.
