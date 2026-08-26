# Fragua — documentación técnica

Por [Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)

Skill de edición de vídeo vertical para YouTube, TikTok e Instagram. Toma una
grabación en bruto y devuelve un corto publicable: silencios recortados,
subtítulos karaoke quemados, cambios de plano, cards gráficas, color corregido y
audio normalizado a −14 LUFS.

Funciona **en local y sin ninguna API**: ffmpeg para el vídeo, whisper.cpp para
la transcripción y Pillow para dibujar las cards. No hay claves que configurar ni
datos que salgan de tu máquina.

---

## Índice

1. [Qué hace exactamente](#qué-hace-exactamente)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Comprobar que funciona](#comprobar-que-funciona)
5. [Uso paso a paso](#uso-paso-a-paso)
6. [Referencia de `plan.json`](#referencia-de-planjson)
6b. [Biblioteca de assets](#biblioteca-de-assets)
7. [Referencia de `presets.json`](#referencia-de-presetsjson)
8. [Instalar como skill de agente](#instalar-como-skill-de-agente)
9. [Problemas frecuentes](#problemas-frecuentes)
10. [Estructura del proyecto](#estructura-del-proyecto)
11. [Licencias](#licencias)

---

## Qué hace exactamente

| | |
|---|---|
| **Corte** | Detecta silencios y los elimina, con padding asimétrico para no cortar colas de palabra |
| **Subtítulos** | Transcribe con whisper.cpp y genera karaoke palabra por palabra, sincronizado al corte |
| **Cards** | Cinco plantillas gráficas (chip, panel, lista, flujo, dato) rasterizadas con Pillow |
| **Movimiento** | Cambios de plano sostenidos, shake, whip pan, flash y letterbox |
| **Imagen** | Denoise, afilado enmascarado por luma, color corregible por vídeo, atenuación de reflejos |
| **Audio** | Paso alto, denoise, EQ de presencia, de-esser, compresor, `loudnorm` y fundido final |
| **Salida** | Un solo pase de ffmpeg desde el original, sin recodificaciones encadenadas |

El diseño separa el trabajo mecánico (los scripts) de las decisiones editoriales
(qué tomas conservar, dónde va cada card). Los scripts no deciden nada creativo:
eso lo defines tú, o el agente, editando dos ficheros JSON.

---

## Requisitos

| Requisito | Comprobación | Cómo instalarlo |
|---|---|---|
| **ffmpeg** y **ffprobe** en el PATH | `ffmpeg -version` | `winget install Gyan.FFmpeg` · `brew install ffmpeg` · `apt install ffmpeg` |
| **Python 3.9+** | `python --version` | [python.org](https://www.python.org/downloads/) |
| **Pillow** | `python -c "import PIL"` | Lo instala `setup.ps1`, o `pip install pillow` |
| **~2 GB de disco** | | Para el modelo de whisper y las fuentes |
| **PowerShell** para el setup | `pwsh -v` o `powershell -v` | Ya viene en Windows; en Linux/macOS es opcional (ver abajo) |

No hace falta GPU. La transcripción va por CPU y tarda aproximadamente lo que
dura el vídeo.

---

## Instalación

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Eso hace cuatro cosas, y es idempotente: si vuelves a ejecutarlo, no redescarga
nada.

1. Instala ffmpeg y Python con `winget` si faltan, y refresca el PATH de la sesión
2. Instala Pillow si falta
3. Descarga el binario de whisper.cpp y el modelo `ggml-large-v3-turbo` (~1.6 GB)
4. Descarga tres fuentes OFL (Roboto, Anton, Poppins) con sus licencias

La detección de Python no se fía de que el comando exista: Windows trae alias de
ejecución de 0 bytes en `WindowsApps` para `python`, `python3` y `py` que están
siempre, aunque no haya Python, y al lanzarlos abren el Microsoft Store. La única
comprobación fiable es ejecutarlos y mirar qué contestan.

Para un modelo más pequeño y rápido, a costa de precisión:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Model ggml-medium
```

### Linux y macOS

```bash
./scripts/setup.sh                  # o: ./scripts/setup.sh ggml-medium
```

Mismos cuatro pasos. Instala lo que falte con `brew`, `apt`, `dnf`, `pacman` o
`zypper`, y compila whisper.cpp desde el repositorio oficial porque no publica
binario para estas plataformas: necesitas `git`, `cmake` y un compilador.

`transcribe.py` busca el binario como `whisper-cli`, `whisper-cli.exe`, `main` o
`main.exe` en cualquier subcarpeta de `vendor/`, así que la ruta exacta da igual.

> **No copies `vendor/` entre máquinas.** Son 1.5 GB y se regenera con el setup.

---

## Comprobar que funciona

```bash
python test_pipeline.py
```

Genera clips sintéticos, ejecuta el pipeline entero y verifica once propiedades:
el mapeo de tiempos, la forma del cambio de plano, el rechazo de zooms
solapados, que el atenuador de reflejos no toque la piel, que el afilado respete
las sombras planas, el corte de silencios, las cinco plantillas de card, la
supresión de subtítulos bajo card, el karaoke y el render completo.

Tarda menos de un minuto. Si sale **`todo verde`**, la instalación está bien.

---

## Uso paso a paso

El pipeline tiene seis pasos. Los ficheros intermedios son JSON legibles, así que
puedes revisar y corregir entre uno y otro sin renderizar nada.

```
vídeo → analyze.py    → cuts.json    segmentos a conservar
      → transcribe.py → draft.json   para leer y decidir el montaje
      → [editas cuts.json y escribes plan.json]
      → transcribe.py --cuts → words.json   transcripción del audio YA cortado
      → cards.py      → cards/*.png  las anotaciones
      → subtitles.py  → subs.ass     el karaoke
      → render.py     → salida.mp4
```

### Paso 1 · Cortar silencios

```bash
python scripts/analyze.py entrada.mp4 -o cuts.json
```

Produce `cuts.json` con los segmentos que se conservan, en tiempo del original.

| Opción | Por defecto | Para qué |
|---|---|---|
| `--threshold` | `-30` | dB por debajo de los cuales hay silencio. Micro flojo o sala ruidosa: prueba `-40` |
| `--min-silence` | `0.35` | Silencio más corto que se recorta. `0.25` para ritmo agresivo |
| `--pad-in` | `0.06` | Aire antes de que empiece la voz |
| `--pad-out` | `0.22` | Aire después. **Más alto a propósito**: las colas de consonante se oyen si las cortas |

Después de invertir los silencios, `analyze.py` hace una **segunda pasada a
−42 dB** para saber dónde para el sonido de verdad y alarga hasta ahí cualquier
final que cayera con la palabra todavía sonando, sin pisar el segmento
siguiente. Imprime cuántos ha rescatado. Y al último le deja 0.45 s de silencio
del original, que es donde tiene que caer el fundido de salida de `render.py`
(0.35 s) para no comerse la última palabra.
| `--min-keep` | `0.12` | Descarta segmentos más cortos que esto |

### Paso 2 · Transcribir para leer

```bash
python scripts/transcribe.py entrada.mp4 -o draft.json --lang es
```

Esta pasada es **solo para decidir el montaje**. Léela para localizar tomas
repetidas, tropiezos y el gancho real del vídeo.

> **Comprueba que el último timestamp cabe en la duración del vídeo.** whisper
> deriva en audio largo con puerta de ruido agresiva. Si ves palabras más allá
> del final, transcribe el tramo suelto (`ffmpeg -ss 60 -i entrada.mp4 -c copy
> cola.mp4`) y súmale el desplazamiento.

### Paso 3 · Decidir el montaje

Edita `cuts.json` a mano para quitar tomas malas: borra o recorta segmentos. Y
escribe `plan.json` con el color, los efectos y las cards (ver la referencia más
abajo).

Para pasar un tiempo del original a la línea de salida:

```python
import sys; sys.path.insert(0, "scripts")
from common import read_json, source_to_output
segments = read_json("cuts.json")["segments"]
print(source_to_output(42.5, segments))   # None si cae en un hueco cortado
```

### Paso 4 · Transcribir de nuevo, ya cortado

```bash
python scripts/transcribe.py entrada.mp4 --cuts cuts.json -o words.json --lang es
```

**Este orden no es negociable.** `--cuts` monta el audio recortado y transcribe
*eso*, así que los tiempos nacen ya en la línea de salida y no hay nada que
remapear. `subtitles.py` rechaza un `words.json` sin cortar precisamente para
que no se cuele el del paso 2.

Repite este paso cada vez que toques `cuts.json`.

Revisa el resultado: whisper falla con jerga técnica, nombres propios y
muletillas. `words.json` es texto plano, corrígelo ahí.

### Paso 5 · Cards y subtítulos

```bash
python scripts/cards.py plan.json --preset tiktok --outdir cards
python scripts/subtitles.py words.json -o subs.ass --preset tiktok --plan plan.json
```

`cards.py` rasteriza un PNG por card, numerados `card00.png`, `card01.png`… en
orden del plan. Ese número es el contrato con `render.py`: si reordenas las cards
en `plan.json`, vuelve a ejecutarlo.

`subtitles.py` lee `plan.json` solo para saber cuándo hay una card en pantalla y
apartar los subtítulos.

### Paso 6 · Renderizar

```bash
python scripts/render.py entrada.mp4 \
  --cuts cuts.json --subs subs.ass --plan plan.json --cards cards \
  --preset tiktok -o salida.mp4
```

| Opción | Para qué |
|---|---|
| `--preset` | `tiktok`, `reels`, `youtube_short` o `youtube_long` |
| `--no-grade` | Salta el color cinematográfico |
| `--no-polish` | Salta el denoise y el afilado enmascarado |

Los dos juntos dejan el píxel de la grabación intacto: la cadena se queda en
`[prepolish]null[polished]` y sobre la imagen sólo actúan el recorte, el
encuadre de los efectos y lo que se compone encima. Los cutaways tampoco se
afilan entonces, así que un clip de menos resolución que la salida entra más
blando — es el precio de no tocar nada.
| `--print-cmd` | Imprime el comando de ffmpeg antes de lanzarlo. Por aquí se empieza a depurar |

Todo es opcional salvo `--cuts`: sin subtítulos, plan ni cards obtienes el corte
limpio con el color por defecto.

---

## Referencia de `plan.json`

Todas las claves son opcionales. **Los tiempos van en la línea de salida**, la
del vídeo ya cortado, que es la que ves al reproducir el resultado.

```json
{
  "grade": "curves=all='0/0.01 0.15/0.19 0.4/0.45 0.75/0.77 1/0.96',eq=contrast=1.05:saturation=1.08",

  "deglare": {"threshold": 160, "strength": 0.65},

  "effects": [
    {"t": 4.2,  "type": "zoom_punch", "hold": 1.8, "amount": 0.11},
    {"t": 9.0,  "type": "cut_in",     "dur": 2.4,  "amount": 0.14},
    {"t": 15.0, "type": "pullback",   "dur": 3.0,  "ramp": 0.55, "scale": 0.76},
    {"t": 22.5, "type": "shake",      "dur": 0.35, "amount": 6},
    {"t": 31.0, "type": "whip_pan",   "dur": 0.20},
    {"t": 36.0, "type": "dip",        "dur": 0.22},
    {"t": 44.0, "type": "flash",      "dur": 0.12, "amount": 0.20},
    {"t": 0.0,  "type": "letterbox",  "dur": 2.50, "amount": 0.12}
  ],

  "cutaways": [
    {"t": 41.0, "dur": 3.6, "file": "clip 2.mp4", "start": 1.2,
     "grade": "eq=brightness=-0.075:saturation=0.80"}
  ],

  "cards": [
    {"t": 0.0,  "dur": 3.6, "y_frac": 0.07, "kind": "chip",
     "title": "El gancho en una línea"},

    {"t": 12.0, "dur": 3.4, "y_frac": 0.60, "kind": "bullets",
     "title": "Cabecera", "items": ["Uno", "Dos", "Tres"]},

    {"t": 25.0, "dur": 3.6, "y_frac": 0.56, "kind": "flow",
     "root": "Idea raíz", "nodes": ["Consecuencia", "Otra", "La tercera"]},

    {"t": 38.0, "dur": 3.0, "y_frac": 0.62, "kind": "panel",
     "title": "Cabecera", "body": "Un párrafo que se ajusta solo al ancho."},

    {"t": 50.0, "dur": 3.2, "y_frac": 0.60, "kind": "stat",
     "value": "2015", "label": "la cifra que sostiene el argumento"},

    {"t": 15.5, "dur": 3.1, "y_frac": 0.045, "kind": "title",
     "title": "El rótulo del pullback de arriba"}
  ],

  "stickers": [
    {"file": "assets/stickers/fuego.png", "t": 5, "dur": 2, "scale": 0.22,
     "x": "W*0.7", "y": "H*0.15"}
  ],

  "music": {"file": "assets/music/beat.mp3", "gain": -18, "duck": true}
}
```

### Biblioteca de assets

`scripts/assets.py` configura de dónde salen música, efectos, stickers, imágenes
y fuentes, y escribe `assets.json` con el catálogo que el agente consulta.

```bash
python scripts/assets.py --set D:/mis-assets   # configura la carpeta
python scripts/assets.py                       # reindexa y muestra el inventario
python scripts/assets.py --show                # sólo dice a dónde apunta
```

La clasificación es por contenido, no por el nombre de la carpeta: un audio de
más de 6 s es `music` y por debajo es `sfx`; una imagen con canal alfa es
`stickers` y sin él es `images`. De cada archivo guarda lo que hace falta para
decidir: duración, dimensiones, transparencia y familia tipográfica.

Las rutas de `plan.json` se resuelven en este orden: absoluta, relativa a la
biblioteca, relativa a la raíz de la skill. Si la biblioteca tiene `fonts/`,
libass la usa en lugar de `vendor/fonts` — sólo acepta un directorio, así que
gana la del usuario.

### Efectos de sonido

`sfx` son golpes puntuales que se mezclan sobre la voz **sin** hacer ducking,
al contrario que `music`. Cada uno se coloca con `adelay` y se rellena con
`apad` hasta la duración total, porque `amix` corta la mezcla en cuanto termina
la rama más corta.

```json
"sfx": [
  {"t": 5.66, "file": "sfx/whoosh.wav"},
  {"t": 11.4, "file": "sfx/pop.wav", "gain": -3}
]
```

`gain` por defecto es −6 dB.

### Efectos

| `type` | Se dimensiona con | `amount` | Cuándo usarlo |
|---|---|---|---|
| `pullback` | `ramp` (0.55) + `dur` | `scale` 0.72–0.82 | **Cambio de tema.** El vídeo se encoge sobre negro y vuelve |
| `zoom_punch` | `ramp` (0.9) + `hold` (1.8) | 0.08–0.15 | Cambio de plano progresivo. Ocupa ~3.7 s, marca secciones |
| `cut_in` | `dur` (2.4) | 0.10–0.16 | El salto: cambia de plano en un fotograma, sin rampa |
| `shake` | `dur` | 4–14 px | Un remate, un dato que golpea |
| `whip_pan` | `dur` | — | Transición entre dos ideas distintas |
| `dip` | `dur` | −0.4 a −0.7 | Bajón a negro, un golpe seco sin rótulo |
| `flash` | `dur` | 0.3–0.6 | Un corte duro, un cambio de bloque |
| `letterbox` | `dur` | 0.08–0.15 | Momento dramático. Ojo si la cara va alta en el encuadre |

**Los zooms no pueden solaparse**: sus contribuciones se suman y darían un zoom
doble. `render.py` aborta con los tiempos exactos si ocurre. Cuentan como zoom
`zoom_punch`, `cut_in`, `shake`, `whip_pan` y `pullback`.

#### `pullback`: encoger sobre negro

`zoompan` no sabe alejarse por debajo de 1:1, así que el cuadro se rellena antes
a **1.5×** y se encuadra dentro: con `z=1.5` se ve el vídeo a tamaño natural y
bajando `z` aparece el relleno negro alrededor. El 1.5 es exacto para que en
reposo el recorte caiga justo 1:1 — medida la varianza laplaciana con y sin el
efecto, 116.05 en ambos casos, y el render tarda lo mismo.

Del hueco que se abre, el **72% va arriba**: ahí se lee el rótulo y ahí no están
los subtítulos. Con `scale` s el vídeo ocupa de `(1-s)*0.72` a `(1-s)*0.72+s`;
con s=0.76 son 332 px de banda negra arriba, y un `kind: "title"` en `y_frac`
0.045 cae centrado en ella.

El suelo de `scale` es **0.75**, y no es una preferencia. Desplazar el hueco
hacia arriba cuesta `(TOP-0.5)*(1-s)/s` del alto y sólo hay `(PAD-1/s)/2` de
margen, así que la condición es `s ≥ (1+2b)/(PAD+2b)` con `b = TOP-0.5`: con
PAD 1.5 y TOP 0.72, eso son 0.742. Por debajo `zoompan` recorta el
desplazamiento sin avisar — medido a 0.72, la banda de arriba sale de 346 px
cuando tocarían 387. El render aborta antes de llegar ahí.

#### Curvas

`zoom_punch` y `pullback` usan `6u⁵-15u⁴+10u³` en todas sus juntas: velocidad y
aceleración cero al entrar y al salir de cada tramo. Lo que se ve como brusco no
es lo que dura el movimiento sino el **escalón de velocidad entre dos
fotogramas** — la curva anterior pasaba de 0 a 7.78 en un solo fotograma, y esta
no pasa de 0.24.

Por eso `zoom_punch` **no se acorta** para conseguir un tirón: un cambio de plano
de un tercio de segundo se lee como salto mal hecho. Para el salto está `cut_in`,
que es instantáneo a propósito y no debe suavizarse nunca.

Los dos derivan mientras aguantan (`SHOT_DRIFT`, 22% del pico): una cámara real
nunca se para en seco y un plano perfectamente quieto es lo que se ve plano.

#### `dip` y `flash`

Los dos mueven el brillo **y la saturación a la vez**. Mover la luma sin tocar el
croma deja píxeles casi negros conservando toda su amplitud de color: en vez de
negro sale suciedad de color. El `whip_pan` desenfoca sólo la luma, sólo en
horizontal y sólo en el tramo central del barrido, por lo mismo.

### Planos de recurso

| Clave | Para qué |
|---|---|
| `t`, `dur` | Cuándo tapa la imagen y cuánto, en la línea de salida |
| `file` | Ruta relativa a la biblioteca de assets |
| `start` | Desde dónde se lee el clip (0 por defecto) |
| `grade` | Cadena de filtros para igualar su color al del vídeo |
| `fade` | Fundido de entrada y salida en segundos (0.35; 0 = corte seco) |

El clip se lleva a la resolución de salida con lanczos y un `unsharp` suave —el
`polish` del vídeo principal queda antes en la cadena y no le llega— y se compone
**después del color y antes de los subtítulos**: conserva su propio look y las
palabras siguen corriendo por encima. **Su audio no se usa**: el del vídeo
original sigue sonando, que es lo que lo hace leerse como otra cámara.

`render.py` rechaza dos cutaways solapados, uno que caiga sobre un `pullback`, y
uno que pida más metraje del que queda en el archivo.

### Capítulos

```json
"chapters": [{"t": 0.0, "title": "..."}, {"t": 80.9, "title": "..."}]
```

```bash
python scripts/chapters.py plan.json --cuts cuts.json
```

Imprime los capítulos en el formato que YouTube reconoce en la descripción.
Los `t` viven en la línea de salida como todo lo demás de `plan.json`, así que
son correctos por construcción: el error clásico es escribirlos mirando la
grabación sin cortar y que queden todos corridos por lo que quitó el detector de
silencios.

Se validan los tres requisitos que YouTube no perdona y que, incumplidos, hacen
que descarte la lista sin avisar: primero en 0:00, mínimo tres, y ninguno de
menos de diez segundos. Y se avisa si alguno se sale del montaje, que delata
tiempos de la grabación original.

### Cards

| `kind` | Forma | Para qué |
|---|---|---|
| `chip` | Píldora compacta de una línea | Títulos y rótulos |
| `panel` | Cabecera de acento + párrafo | Una idea con desarrollo |
| `bullets` | Cabecera + lista con viñetas | Enumerar lo que se dice de corrido |
| `flow` | Nodo raíz + espina con nodos conectados | Estructura o dependencia |
| `stat` | Cifra grande + etiqueta | Un dato que merece pantalla |
| `title` | Texto grande, sin panel detrás | La banda negra que abre un `pullback` |

`y_frac` es el borde superior de la card como fracción de la altura. **No lo
estimes de un fotograma: mídelo.** Una cara quieta engaña, porque al hablar se
gesticula y se inclina. Saca seis fotogramas repartidos por la ventana de la
card, busca en cada uno la fila más baja con piel en la banda central —rojo por
encima del azul, que separa cara y manos de una camiseta negra y de un fondo
frío— y quédate con la peor. En un plano medio vertical eso sale **0.66–0.68**,
no 0.56: con 0.56 la card se come la barba. Por abajo no pases de **0.85**,
donde TikTok e Instagram ponen su interfaz.

Mientras una card está en pantalla, **los subtítulos se ocultan solos** — salvo
`chip`, que es una etiqueta, y `title`, que vive por encima del vídeo encogido.

#### Cards animadas

```bash
python scripts/cards.py plan.json --preset tiktok --outdir cards --animated
```

Las dibuja con **Remotion** (`remotion/src/Card.tsx`) en vez de con Pillow: las
viñetas entran una a una, el filete se traza, la espina del flujo se dibuja de
arriba abajo y la cifra de una `stat` cuenta hasta su valor. Mismo `plan.json`
—los componentes de React leen el spec tal cual—, mismos colores del preset.

Salen `cardNN.mov` (ProRes 4444 con alfa) en vez de `cardNN.png`, y `render.py`
prefiere el `.mov` cuando existe, así que una edición ya hecha se reanima
volviendo a lanzar sólo este comando. Cuesta unos 30 s por vídeo: un bundle de
3.7 s más ~6 s por card.

Necesita Node con las dependencias de `remotion/` instaladas. **Es opcional a
propósito**: Remotion arrastra Node y su propio Chrome, así que el setup sólo lo
prepara si Node ya está en la máquina. Sin él las cards salen quietas y todo lo
demás funciona igual.

Para inventarse un `kind` nuevo basta con un componente en `Card.tsx` y su
equivalente en `cards.py` para quien no tenga Node.

Varía el `kind`: repetir el mismo en todas es lo que las hace parecer plantilla.

### Color

`grade` reemplaza el color por defecto, que asume material bien expuesto. Mide
antes de decidir:

```bash
ffmpeg -hide_banner -nostats -ss 30 -i entrada.mp4 -frames:v 1 \
  -vf signalstats,metadata=print -f null -
```

`YAVG` es el brillo medio (0–255) e `YHIGH` el percentil 90. Por debajo de
YAVG 45 el material está subexpuesto: levanta medios con `curves` en vez de
aplicar el grade por defecto. Y **cierra el techo en `1/0.96`**: lo que se
percibe como «demasiado brillante» casi nunca es la media, son las altas luces
lavándose.

> No metas `hqdn3d` en `grade`. `render.py` ya denoisa, y sus dos últimos
> parámetros son temporales: duplicarlo deja estelas de movimiento.

### Reflejos

`deglare` atenúa reflejos especulares (gafas, brillo de sudor). Baja los píxeles
que son a la vez brillantes **y** casi neutros de color; esa puerta de saturación
lo mantiene fuera de la piel.

**Atenúa, no elimina**: donde un reflejo sustituyó lo que había detrás no queda
nada que recuperar. Por encima de `strength` 0.75 cambias una mancha blanca por
una gris, que se ve peor. Cuesta unas 4× el tiempo de render, así que va
desactivado por defecto.

El arreglo de verdad está al grabar: baja el brillo del monitor, sácalo del eje
de la cámara o inclina las patillas de las gafas.

---

## Referencia de `presets.json`

Cuatro presets: `youtube_long` (1920×1080), `tiktok`, `reels` y `youtube_short`
(1080×1920). Todos normalizan a −14 LUFS.

| Campo | Qué controla |
|---|---|
| `crf` | Calidad. Menor = mejor y más pesado. 15–16 deja margen para la recompresión de la plataforma |
| `subtitle.fontname` | **Nombre de la instancia**, no de la familia: `Roboto Black`, no `Roboto` |
| `subtitle.border_style` | `1` contorno, `3` caja de fondo |
| `subtitle.box` | Color de la caja cuando `border_style` es 3 |
| `subtitle.outline` | Con `border_style` 3 es el **relleno interior**, no el grosor |
| `subtitle.primary` / `secondary` | Color de palabra dicha / pendiente en el barrido karaoke |
| `subtitle.margin_v` | Distancia al borde inferior. En vertical, 380–480 evita la UI de la app |

`--srt fichero.srt` escribe además una pista de subtítulos en texto plano, para
subir a YouTube en vez de quemarlos. Es lo que corresponde en horizontal y en
vídeo largo: quemados tapan el código y no se pueden desactivar, y como pista
YouTube los indexa.

`subtitles.py` acepta `--fontsize`, `--margin-v` y `--max-chars` para saltarse el
preset sin tocarlo. Se usan sobre todo en grabaciones de pantalla, donde el sitio
por defecto cae encima de lo que se está enseñando: `--fontsize 44 --margin-v 250
--max-chars 40` deja una línea compacta abajo. Al bajar la fuente, el contorno se
reescala con ella, porque si no un texto pequeño queda con un borde que ocupa más
que las letras.
| `card.accent` | Un solo color de acento gobierna texto, borde y cabecera de todas las cards |
| `card.base_size` | Tamaño base del que derivan título, cuerpo y nodos |

Los colores de subtítulo van en formato ASS `&HAABBGGRR`: azul y rojo invertidos
respecto a HTML, y **el alfa al revés de lo intuitivo** — `00` es opaco y `FF`
transparente.

Si cambias de fuente, **recalibra `fontsize`**: la altura de mayúscula varía
mucho entre familias y el mismo tamaño nominal rinde distinto.

---

## Instalar como skill de agente

Lo normal es dejar que el instalador lo haga:

```bash
git clone https://github.com/pedrovelasquez9/fragua
cd fragua
./install.sh                                                     # macOS y Linux
powershell -ExecutionPolicy Bypass -File install.ps1             # Windows
```

Copia los archivos al destino, enlaza `vendor/` si instalas para varios agentes,
ejecuta el setup y lanza la suite de comprobación. Acepta `--target claude` o
`--target opencode`, `--project` para instalar solo en la carpeta actual y
`--model` para elegir otro modelo de whisper.

### A mano

Si prefieres controlarlo tú, los destinos son estos:

| Agente | Global | Por proyecto |
|---|---|---|
| Claude Code | `~/.claude/skills/fragua/` | `.claude/skills/fragua/` |
| OpenCode | `~/.config/opencode/skills/fragua/` | `.opencode/skills/fragua/` |

OpenCode también lee `~/.claude/skills/`, así que una sola copia puede servir
para ambos.

La carpeta **debe llamarse `fragua`**, igual que el campo `name` del frontmatter
de `SKILL.md`: OpenCode lo valida contra `^[a-z0-9]+(-[a-z0-9]+)*$` y rechaza la
skill si no coincide.

Después ejecuta el setup **dentro de la carpeta ya copiada**, para que `vendor/`
quede donde los scripts lo buscan.

El agente necesita permiso para ejecutar `python` y `ffmpeg` desde su herramienta
de shell.

---

## Problemas frecuentes

| Síntoma | Causa |
|---|---|
| `todo el vídeo se detectó como silencio` | `--threshold` demasiado alto; prueba `-40` |
| `words.json viene del vídeo sin cortar` | Falta `--cuts` en `transcribe.py` |
| `faltan cards: ...` | Ejecuta `cards.py` antes de `render.py`, o pasa `--cards` |
| `efectos de zoom solapados` | Dos zooms a la vez se suman; sepáralos o baja `hold` |
| `plan.json usa 'text'` | Los títulos son cards de `kind: chip` |
| Subtítulos desincronizados | Tocaste `cuts.json` sin rehacer los pasos 4 y 5 |
| Timestamps más allá del final | Deriva de whisper; transcribe el tramo suelto |
| Falta un trozo de la transcripción | whisper salta zonas con tomas casi idénticas |
| Se ve pixelado en la camiseta | El afilado entra en sombras; sube `SHARPEN_FLOOR` en `render.py` |
| Movimiento con estelas | `hqdn3d` duplicado en `grade` |
| Se ve lavado | La curva no cierra el techo; baja el último punto a `1/0.96` |
| La fuente sale fina pese a `bold: -1` | Es variable; pide la instancia (`Roboto Black`) |
| No se ve la caja de fondo | Es casi negra sobre fondo oscuro: sube luminosidad, no solo opacidad |
| El audio se corta sobre la última palabra | No debería pasar: los finales se alargan solos. Si ocurre, revisa si editaste ese segmento a mano |

Lo que no se arregla en post: si grabas a 30 fps con obturador lento, los gestos
rápidos salen movidos en el original.

---

## Estructura del proyecto

```
fragua/
├── README.md              este fichero
├── SKILL.md               instrucciones para el agente
├── presets.json           parámetros por plataforma
├── test_pipeline.py       suite de verificación
├── scripts/
│   ├── setup.ps1          descarga whisper.cpp, el modelo y las fuentes
│   ├── common.py          rutas, JSON, ffmpeg y mapeo de la línea de tiempo
│   ├── analyze.py         silencios → cuts.json
│   ├── transcribe.py      whisper.cpp → words.json
│   ├── cards.py           plan.json → cards/*.png
│   ├── subtitles.py       words.json → subs.ass
│   └── render.py          todo junto → salida.mp4
├── assets/                tu música, stickers y SFX (opcional)
└── vendor/                whisper.cpp, modelo y fuentes (lo crea el setup)
```

---

## Licencias

Fragua se publica bajo licencia **MIT**, ver [LICENSE](LICENSE). Las descargas del setup traen sus propias
licencias, todas permisivas:

- **whisper.cpp** — MIT
- **ggml-large-v3-turbo** — modelo Whisper de OpenAI, MIT
- **Roboto**, **Anton**, **Poppins** — SIL Open Font License, con el texto de la
  licencia en `vendor/fonts/OFL-*.txt`

Si añades música o stickers en `assets/`, la licencia es cosa tuya. Lee
`assets/README.md`: **no metas material de CapCut o TikTok**, está licenciado
para usarse dentro de esas apps y su música dispara Content ID en YouTube.

---

Hecho por **[Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)**
