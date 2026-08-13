---
name: assets
description: Configura la carpeta de assets de Fragua (música, efectos, stickers, imágenes y fuentes) e indexa lo que hay dentro para que las ediciones puedan usarla.
disable-model-invocation: true
---

# Configurar la biblioteca de assets

El usuario ha escrito `/fragua:assets` y puede haber pasado una ruta en
`$ARGUMENTS`.

## Qué hacer

**Si `$ARGUMENTS` trae una ruta**, configúrala y muestra el inventario:

```bash
python <skill>/scripts/assets.py --set "$ARGUMENTS"
```

**Si no trae nada**, reindexa la carpeta ya configurada y muestra qué hay:

```bash
python <skill>/scripts/assets.py
```

Si el script responde que no existe la carpeta, es que nadie la ha configurado
todavía: dile al usuario que vuelva a lanzarlo con la ruta, por ejemplo
`/fragua:assets D:/mis-assets`.

`<skill>` es la raíz de Fragua: **dos niveles por encima de este archivo**
(`../../` desde `skills/<nombre>/SKILL.md`). Es la carpeta que contiene
`presets.json`, `test_pipeline.py` y `scripts/`. Resuélvela antes de nada; si la
instalación es plana, en vez de en `skills/`, es la carpeta que contiene este
mismo archivo.

## Qué contarle al usuario después

Resume el inventario en una frase por categoría, con lo que de verdad importa
para decidir: cuántas pistas de música y de qué duración, cuántos efectos,
cuántos stickers y si tienen transparencia, y qué fuentes con su nombre de
familia.

Si alguna categoría está vacía, dilo y sugiere qué meter, ciñéndote a lo que la
skill sabe usar:

- `music/` — pistas largas de fondo, que bajan solas cuando hay voz
- `sfx/` — golpes cortos: whoosh para un barrido, pop cuando entra una tarjeta,
  riser antes de un dato
- `stickers/` — PNG **con transparencia**, o quedarán como un recuadro opaco
- `images/` — capturas, logos y fondos
- `fonts/` — `.ttf` u `.otf` propios, que tendrán prioridad sobre las de la skill

Recuérdale que fuentes de música con licencia libre son Pixabay, Mixkit y
Freesound, y que el material de CapCut o TikTok está licenciado sólo para esas
apps y dispara reclamaciones de copyright en YouTube.

Termina diciéndole que a partir de ahora las ediciones tirarán de ahí solas, y
que vuelva a lanzar `/fragua:assets` cada vez que añada material nuevo.
