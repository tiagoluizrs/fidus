# Palavras de ativação: treinar e instalar "ei Alfred", "ei Donna" e "ei Jarbis"

Este guia leva você de zero até os três modelos funcionando no Fidus. Você vai treinar **3 modelos** (um por
palavra) fora do código, no Google Colab, e copiar os arquivos `.onnx` para `models/wakewords/`.

> **Antes de treinar:** valide o encanamento com o modelo pronto "hey jarvis" (seção 1). Assim, se algo falhar
> depois, você sabe que o problema está no modelo treinado, não no Fidus.

## Como funciona (em 5 linhas)

- O Fidus usa o **openWakeWord** (código Apache 2.0), local e com runtime ONNX no Windows.
- Cada palavra é um modelo pequeno (~200 KB a 1 MB) que recebe o áudio do microfone em blocos de 80 ms e devolve
  uma pontuação de 0 a 1. Passou do **limiar** da palavra = chamado.
- O áudio da escuta passiva fica só na memória (buffer de ~2 s) e **nunca** é gravado em disco nem enviado.
  Só depois do chamado a gravação começa e vai para o Whisper local.
- Os modelos prontos do openWakeWord têm licença **CC BY-NC-SA 4.0** (só uso não comercial). Para uso pessoal serve.
  Para modelos treinados por você, confira a licença dos dados que o notebook baixa.
- Treinar **não exige gravar a sua voz**: o treino usa fala sintética gerada por TTS.

## 1. Validar o encanamento com o modelo de teste ("somente teste")

```powershell
uv sync
uv run fidus wake-test --somente-teste
```

Na primeira vez baixa os modelos auxiliares e o "hey jarvis" (alguns MB, do GitHub). Diga **"hey Jarvis"** perto do
microfone: a pontuação sobe e aparece `>>> ATIVOU: hey_jarvis_teste -> jarbis`. Depois:

```powershell
uv run fidus listen --somente-teste     # o laço completo, chamando com "hey Jarvis"
```

O modelo de teste está rotulado `somente_teste = true` e mapeado para o personagem Jarbis. É só para teste.

## 2. Treinar os modelos (no Google Colab)

**O que você precisa:** uma conta Google (grátis) e um navegador. Não precisa de GPU própria.

**Onde rodar:** o notebook de treino automático do projeto, linkado no README do openWakeWord:
<https://github.com/dscripka/openWakeWord> (procure por *"automatic_model_training"* / *"Google Colab"*).

**Quanto tempo leva (estimativa, não verifiquei):** o projeto diz que um modelo básico sai em menos de 1 hora; relatos
da comunidade falam em 1 a 1,5 h por modelo, mais um download grande de dados na primeira execução (vários GB, dentro
do Colab, não no seu PC). Reserve uma tarde para os três. O Colab grátis pode limitar o uso da GPU; se cortar, retome
no dia seguinte.

**Passo a passo:**

1. Abra o notebook no Colab e escolha *Ambiente de execução > Alterar tipo > GPU (T4)*.
2. Na célula de configuração, defina a frase em `target_phrase` e um nome em `model_name`:
   - `target_phrase`: `"ei alfred"`, com `model_name`: `"ei_alfred"`.
   - Depois repita para `"ei donna"` (`ei_donna`) e `"ei jarbis"` (`ei_jarbis`).
3. Execute as células em ordem. Cada modelo gera os áudios sintéticos, treina e exporta.
4. No fim, baixe o arquivo **`.onnx`** (o Fidus usa ONNX; o `.tflite` não serve no Windows).
5. Repita para cada palavra.

**Cuidados importantes**

- **Pronúncia em português.** As vozes sintéticas do notebook costumam ser em inglês. "Ei" e os nomes podem sair
  com sotaque errado e o modelo reconhecer pior a sua fala. Se o resultado for ruim, tente: (a) escrever a frase
  como soa em inglês ou foneticamente (ex.: `"ei alfred"` -> `"ay alfred"`); (b) treinar mais amostras; ou
  (c) usar o **plano B: `"hey alfred"`, `"hey donna"`, `"hey jarbis"`** (seção 5). A palavra é só configuração.
- **O notebook muda.** Há relatos de que o notebook oficial quebrou com versões novas das bibliotecas. Se der erro de
  instalação, procure o aviso no README do projeto ou use um notebook mantido pela comunidade (por exemplo
  <https://github.com/alfiedennen/openwakeword-colab-2026>). Confira se ele gera `.onnx`.
- Nomes parecidos entre si ("alfred"/"jarbis") não confundem, mas "donna" é curta: espere mais alarmes falsos nela.

## 3. Instalar os arquivos

Copie os três arquivos para a pasta do projeto, com estes nomes:

```
fidus\models\wakewords\ei_alfred.onnx
fidus\models\wakewords\ei_donna.onnx
fidus\models\wakewords\ei_jarbis.onnx
```

Eles não vão para o Git (estão no `.gitignore`). Se usar outro nome de arquivo, indique no `fidus.toml`:

```toml
[chamados.palavras.ei_alfred]
modelo = "meu_alfred_v2.onnx"
```

Se um arquivo não existir, só aquela palavra fica desativada (aviso no terminal e no `actions.log`) e o push-to-talk
continua funcionando.

## 4. Ajustar o limiar

```powershell
uv run fidus wake-test
```

Mostra, em tempo real, `palavra pontuação/limiar` e um `*` quando passa do limiar. Ao apertar `Ctrl+C` vem o resumo
com o **pico** de cada palavra. Faça assim:

1. Fique em silêncio e depois deixe a TV ou uma conversa tocando por 1 a 2 minutos: anote o pico de cada palavra
   (o "pico do ruído").
2. Chame cada palavra 10 vezes, normalmente, a 1 m do microfone: anote os picos (o "pico da sua voz").
3. Escolha um limiar **acima do pico do ruído** e **abaixo da maioria dos picos da sua voz**.
4. Grave no `fidus.toml`:

```toml
[chamados.palavras.ei_alfred]
limiar = 0.65
```

Regra prática: começa em 0,5. **Alarmes falsos** (ativa sozinho): suba para 0,6 a 0,8. **Não te ouve**: baixe para
0,3 a 0,4. Também ajuda aumentar `intervalo_s` (mínimo entre ativações) e testar outro microfone.

Teste final de alarmes falsos: deixe `uv run fidus listen` por **15 minutos** com TV ou conversa de fundo e conte as
ativações indevidas no `actions.log` (eventos `chamado`). O alvo é nenhuma, ou no máximo uma.

## 5. Plano B: "hey" em vez de "ei"

Se "ei ..." não treinar bem, treine `hey_alfred`, `hey_donna` e `hey_jarbis` e troque no `fidus.toml`:

```toml
[chamados.palavras.hey_alfred]
modelo = "hey_alfred.onnx"
personagem = "alfred"

[chamados.palavras.ei_alfred]
ativa = false
```

(Repita para Donna e Jarbis.) O personagem chamado vem do campo `personagem`, então nada mais muda.

## Resumo dos arquivos e comandos

| O quê | Onde |
| --- | --- |
| Modelos treinados | `models/wakewords/*.onnx` |
| Palavras ativas, limiares, intervalo | `fidus.toml`, seção `[chamados]` |
| Ver pontuações em tempo real | `uv run fidus wake-test` |
| Medir CPU e memória em repouso | `uv run fidus wake-bench` |
| Usar o laço completo | `uv run fidus listen` |
