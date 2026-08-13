---
name: setup
description: Prepara las dependencias de Fragua — ffmpeg, Python, whisper.cpp, el modelo de transcripción y las fuentes — y verifica que el pipeline funciona.
disable-model-invocation: true
---

# Preparar Fragua

El usuario ha escrito `/fragua:setup`. Deja la skill lista para editar vídeo.

`<skill>` es la raíz de Fragua: **dos niveles por encima de este archivo**
(`../../` desde `skills/<nombre>/SKILL.md`). Es la carpeta que contiene
`presets.json`, `test_pipeline.py` y `scripts/`. Resuélvela antes de nada; si la
instalación es plana, en vez de en `skills/`, es la carpeta que contiene este
mismo archivo.

## Qué hacer

Lanza el setup de la plataforma correspondiente **desde la carpeta de la skill**:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/setup.ps1
```
```bash
bash <skill>/scripts/setup.sh
```

Si el usuario pasó un modelo en `$ARGUMENTS` (por ejemplo `ggml-medium`),
añádelo: `-Model ggml-medium` en Windows, o como primer argumento en el resto.

Descarga alrededor de 1,6 GB, así que **puede tardar varios minutos**. Avisa
antes de empezar y no lo interrumpas.

Después verifica:

```bash
python <skill>/test_pipeline.py
```

Tiene que terminar en `todo verde`.

## Si algo falla

**ffmpeg o Python no aparecen tras instalarse.** Es el PATH de la sesión. El
script ya lo refresca, pero si persiste, dile al usuario que abra un terminal
nuevo y repita.

**En Windows dice que Python no arranca.** Windows trae alias de ejecución de
0 bytes en `WindowsApps` para `python`, `python3` y `py` que existen aunque no
haya Python y abren el Microsoft Store. Comprueba cuál funciona de verdad
ejecutando `--version` con cada uno, no dando por buena su existencia.

**En Linux o macOS falla la compilación de whisper.cpp.** No publica binario
para esas plataformas, así que hacen falta `git`, `cmake` y un compilador.
Dile cuál falta.

**El setup es idempotente**: si algo quedó a medias, se puede relanzar tantas
veces como haga falta y no redescarga lo que ya está.

## Al terminar

Dile al usuario que ya puede pedirte una edición pasándote la ruta de un vídeo,
y que si tiene música, efectos o stickers propios los configure con
`/fragua:assets <carpeta>`.
