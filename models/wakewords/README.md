# Modelos de palavra de ativação

Coloque aqui os arquivos `.onnx` treinados (veja `docs/WAKEWORDS.md`):

```
ei_alfred.onnx
ei_donna.onnx
ei_jarbis.onnx
```

Os `.onnx` não vão para o Git (são seus). Se um modelo não existir, só aquela palavra fica desativada e o
push-to-talk continua funcionando; o aviso aparece no terminal e no `actions.log`.
