---
name: fragua
description: Edita vídeo bruto para YouTube, TikTok e Instagram — quita silencios, transcribe y quema subtítulos karaoke, aplica cambios de plano y efectos, cards gráficas, color y normalización de audio; y al terminar redacta el copy de publicación (título, descripción, tags y captions por red). Úsala cuando el usuario pase un vídeo para editar, pida un corto/short/reel a partir de uno largo, pida subtítulos quemados, quitar silencios, un look cinematográfico, o el texto para publicar el vídeo. Requiere ffmpeg y whisper.cpp local.
---

# Fragua

Convierte una grabación cruda en vídeo publicable. Los scripts hacen el trabajo
mecánico; tú (el modelo) tomas las decisiones editoriales leyendo la transcripción.

**Ningún script decide qué es viral.** Eso lo decides tú en `plan.json`.

## Antes de nada

`ffmpeg` en el PATH y whisper.cpp descargado:

```bash
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1   # Windows
./scripts/setup.sh                                           # Linux y macOS
```

Una vez por máquina (~1.6 GB). Comprueba que todo funciona:

```bash
python test_pipeline.py
```

## El flujo

Cada etapa escribe un JSON que puedes leer y editar antes de la siguiente. No se
renderiza nada hasta el final, así que iterar es gratis.

```
vídeo → analyze.py    → cuts.json    (segmentos a conservar, vía silencedetect)
      → transcribe.py --cuts cuts.json → words.json + digest.txt
      → [lees digest.txt, editas cuts.json si hace falta y escribes plan.json]
      → assets.py --auto → reindexa la biblioteca (SIEMPRE, antes de plan.json)
      → cards.py      → cards/*.png  (las anotaciones, rasterizadas)
      → subtitles.py  → subs.ass     (karaoke, ya en la línea de tiempo final)
      → render.py     → salida.mp4   (un solo pase de ffmpeg desde el original)
      → chapters.py    → capítulos     (obligatorio en vídeo largo)
      → [copy de publicación: título, descripción, tags y captions]

`assets.py --auto` se ejecuta en **cada edición**, sin que nadie lo pida: así
una imagen o una pista añadida esta mañana ya está disponible esta tarde. El
usuario no tiene que acordarse de reindexar nada.
```

El orden importa: los subtítulos se transcriben **después** de cortar, nunca
antes. Y el último paso no es opcional: el vídeo se entrega con su copy.

### 1. Cortar silencios

```bash
python scripts/analyze.py entrada.mp4 -o cuts.json
```

Sale `cuts.json` con los segmentos que se conservan. Ajusta si hace falta:

**Los finales de palabra se rescatan solos.** El corte se decide a
`--threshold`, pero la cola de una consonante sigue sonando por debajo de ese
nivel: si el segmento acaba ahí, se oye «có—» en vez de «código». Una segunda
pasada a −42 dB dice dónde para el sonido de verdad y alarga cada final hasta
ahí, sin llegar nunca a pisar el segmento siguiente. `analyze.py` te dice
cuántos ha rescatado.

Y el último segmento se queda además con 0.45 s de silencio del original,
porque `render.py` cierra con un fundido de audio de 0.35 s: sin ese hueco, el
fundido se come la última palabra.

`--pad-in` (0.06) y `--pad-out` (0.22) son **asimétricos a propósito**: las colas
de consonante y el decaimiento de la voz se prolongan más allá de donde el
detector declara silencio, así que recortar el final de un segmento se oye mucho
más que recortar el principio. Si una frase suena truncada, sube `--pad-out`.

- `--threshold -30` — dB por debajo de los cuales hay silencio. Audio ruidoso o
  micro flojo: prueba `-40`. Si el script avisa de que todo es silencio, ese es el motivo.
- `--min-silence 0.35` — silencio más corto que se recorta. Bájalo a `0.25` para
  un ritmo agresivo tipo TikTok; súbelo a `0.6` para vídeo largo que respire.
- `--min-keep 0.12` — descarta segmentos conservados más cortos que esto.

### 2. Transcribir, una sola vez

```bash
python scripts/transcribe.py entrada.mp4 --cuts cuts.json -o words.json \
       --digest digest.txt --lang es
```

`--cuts` monta el audio ya recortado y transcribe **eso**, así que los timestamps
nacen en la línea de tiempo de salida: no hay nada que remapear y la sincronía no
puede desviarse. El mismo `words.json` sirve para decidir el montaje y para los
subtítulos; no hay una segunda pasada sobre el original.

`--digest` escribe además `digest.txt`, que es **lo que tienes que leer**. Es la
transcripción frase a frase con los dos tiempos: el de salida, para `plan.json`,
y el del original, para `cuts.json`. Medido en un vídeo de 17 minutos:
`words.json` son 294 KB de andamiaje JSON y el digest son 21 KB con exactamente
las mismas palabras.

```
# [salida | original]
[0:20 | 0:23] Pero ¿por qué hago esto? Generalmente cuando tú entras al mundo…
```

Tarda aproximadamente lo que dura el vídeo cortado, en CPU.

**Comprueba que el último timestamp cabe en la duración de salida.** whisper.cpp
deriva en audio largo, sobre todo con puerta de ruido agresiva: se ha visto una
transcripción situando palabras en el segundo 108 de un vídeo de 80. Si deriva,
recorta el tramo que te interesa y transcríbelo suelto — en clips cortos no
ocurre — y súmale el desplazamiento:

```bash
ffmpeg -y -ss 58 -i entrada.mp4 -c copy cola.mp4
python scripts/transcribe.py cola.mp4 -o cola.json --lang es   # tiempos +58
```

También puede **saltarse tramos enteros** donde repites tomas casi idénticas.
Si un trozo de la transcripción falta, mira ahí: suele ser eso.

**Si editas `cuts.json`, repite este comando.** Es la única parte del flujo que
hay que rehacer, y sobre un vídeo ya recortado va más rápido que la primera vez.

### 3. Decidir la edición (esto lo haces tú)

Lee `digest.txt`. Es la transcripción completa frase a frase: ahí está todo lo
que necesitas para editar sin ver el vídeo. `words.json` es la misma información
palabra a palabra, y sirve para `subtitles.py`, no para leerla tú.

Los tiempos de `digest.txt` vienen en pares: el de la izquierda es el del montaje
y va a `plan.json`; el de la derecha es el de la grabación y es el que hace falta
para borrar un segmento de `cuts.json`.

**Para un corto**, busca el fragmento con mayor densidad de gancho: una
afirmación fuerte, una cifra concreta, una contradicción, una historia con
remate. Recorta `cuts.json` a esos segmentos. Un corto que funciona dura 20-45 s
y dice algo interesante en los tres primeros segundos.

**Para vídeo largo**, quita divagaciones y falsos arranques que el detector de
silencios no ve porque tienen audio: repeticiones, "a ver, déjame que", ramas que
no llevan a ningún sitio. Borra esos segmentos de `cuts.json`.

Después escribe `plan.json`. Los tiempos van en la **línea de tiempo de salida**
(la del vídeo ya cortado), que es la que ves al reproducir el resultado. Para
convertir un tiempo del original usa `source_to_output()` de `scripts/common.py`.

```json
{
  "effects": [
    {"t": 0.0,  "type": "letterbox",  "dur": 2.5, "amount": 0.12},
    {"t": 3.2,  "type": "zoom_punch", "hold": 2.0, "amount": 0.12},
    {"t": 8.7,  "type": "shake",      "dur": 0.3, "amount": 8},
    {"t": 12.0, "type": "flash",      "dur": 0.15},
    {"t": 15.4, "type": "whip_pan",   "dur": 0.2}
  ],
  "cards": [
    {"t": 0, "dur": 3.4, "y_frac": 0.07, "kind": "chip",
     "title": "Nadie te cuenta esto"},
    {"t": 14.6, "dur": 3.1, "y_frac": 0.66,
     "title": "En el vídeo",
     "body": "Cómo destacar\nTu rol con la IA\nConseguir clientes"}
  ],
  "stickers": [
    {"file": "assets/stickers/fuego.png", "t": 5, "dur": 2, "scale": 0.22,
     "x": "W*0.7", "y": "H*0.15"}
  ],
  "music": {"file": "assets/music/beat.mp3", "gain": -18, "duck": true}
}
```

Todas las claves son opcionales. Sin `plan.json` sale un corte limpio con
subtítulos y color, que ya es un vídeo entregable.

**`"grade"`** reemplaza el color por defecto, que asume material bien expuesto.
El look correcto depende del material, no de la plataforma, así que vive aquí y
no en `presets.json`. Mide antes de decidir:

```bash
python scripts/measure.py entrada.mp4
```

Formato, brillo, saturación y sonoridad en un bloque. `YAVG` es el brillo medio
(0-255) e `YHIGH` el percentil 90. **Por debajo de
YAVG 60 el grade por defecto hundirá el material**, así que levanta medios con
`curves` en vez de aplicarlo.

Ese umbral parece alto porque no lo marca la curva sino la **viñeta**. Medido en
un plano medio a YAVG 53: la curva por sí sola deja 44.7 (−15%), y la viñeta
sola deja 40.3 (−24%). Juntas, 34 — la cara se hunde en las sombras. En material
bien iluminado se compensa; en luz baja, no. Sube la curva hasta un YAVG de
50-55 y **cierra el techo en `1/0.95`** — lo que se percibe como "demasiado
brillante" casi nunca es la media, son las altas luces de la cara lavándose.

**No metas `hqdn3d` en `"grade"`.** `render.py` ya denoisa, y los dos últimos
parámetros de `hqdn3d` son temporales: aplicarlo dos veces deja estelas de
movimiento que se ven como pixelado y como falta de fluidez.

**`"deglare"`** atenúa reflejos especulares: gafas, brillo de sudor, superficies
pulidas. Baja los píxeles que son a la vez brillantes **y** casi neutros de
color; esa puerta de saturación es lo que lo mantiene fuera de la piel y de las
luces de colores, que sí son cromáticas.

```json
"deglare": true
"deglare": {"threshold": 160, "strength": 0.65, "sat_max": 50, "feather": 30}
```

**Atenúa, no elimina.** Donde un reflejo sustituyó lo que había detrás no queda
nada que recuperar: subir `strength` cambia una mancha blanca por una gris, que
se lee como fallo de render mientras que la blanca el ojo la interpreta como
reflejo y la ignora. Por encima de 0.75 empeora.

Comprueba antes si merece la pena. Mide el fotograma donde se ve el reflejo:

```bash
python scripts/measure.py entrada.mp4 --at 30
```

Si el reflejo está saturado a 255 no hay nada debajo y esto no sirve de nada.
Si llega a ~240 sin recortar, sí hay estructura que rescatar.

Cuesta **unas 4 veces más de render** (`geq` evalúa por píxel), así que va
desactivado por defecto. Y el arreglo de verdad está en la grabación: baja el
brillo del monitor, sácalo del eje de la cámara o inclina las patillas para que
el reflejo caiga por debajo del objetivo. Treinta segundos de ajuste dan un
resultado limpio que ningún filtro iguala.

**Efectos disponibles**

| tipo | qué hace | `amount` | cuándo |
|---|---|---|---|
| `cut_in` | **corte** a plano cerrado, sin rampa | 0.10–0.16 | sobre la primera palabra de una frase fuerte |
| `zoom_punch` | **cambio de plano** progresivo: entra, deriva, sale | 0.08–0.15 | al abrir una sección |
| `shake` | vibración con caída | 4–14 (px) | en un remate o un dato impactante |
| `whip_pan` | barrido lateral con desenfoque | — | entre dos ideas distintas |
| `pullback` | el vídeo se encoge sobre negro y vuelve | `scale` 0.72–0.82 | **donde cambia el tema** |
| `dip` | bajón a negro | −0.4 a −0.7 | un golpe seco, sin rótulo |
| `flash` | destello a blanco | 0.3–0.6 | en un corte duro o un beat |
| `letterbox` | barras negras cine | 0.08–0.15 | en el hook o un momento dramático |

### Dónde van los efectos (esto es lo que separa un montaje de un adorno)

**Cada efecto va sobre una frase concreta, no cada N segundos.** Repartirlos por
reloj es exactamente lo que se ve como «aleatorio y brusco»: el espectador nota
que el movimiento no responde a nada. Antes de colocar ninguno, busca en
`digest.txt` los instantes que de verdad cargan el vídeo —la vuelta de tuerca,
la cifra, la frase que el autor subraya con la voz, el «repito», el remate— y
pon el efecto **en la primera palabra** de esa frase, no en medio.

**`cut_in` es un corte de verdad.** Cambia de plano entre un fotograma y el
siguiente, sin rampa. Un empuje de un tercio de segundo se sigue leyendo como
zoom; el salto instantáneo se lee como segunda cámara, que es lo que quieres en
la frase importante. Sobre una palabra cualquiera, en cambio, se lee como un
fallo: sin frase que lo justifique, no lo pongas.

**`zoom_punch` es una transición, no un acercamiento.** Casi un segundo de
recorrido, y todas las juntas de la curva —entrada, deriva, salida— con
velocidad cero: el plano se pone en marcha desde parado y se detiene sin
frenazo. Lo que se ve como brusco no es la duración, es el **escalón de
velocidad entre dos fotogramas**; medido, la curva anterior pasaba de 0 a 7.78 en
un solo fotograma y esta no pasa de 0.24.

El plano sigue empujando un poco mientras aguanta: una cámara real nunca se para
en seco, y un plano perfectamente quieto es justo lo que se ve plano.

Si lo que quieres es el salto, **no acortes el `zoom_punch`**: un plano de un
tercio de segundo se lee como salto mal hecho. Usa `cut_in`, que es el salto
bien hecho.

**Las transiciones van donde cambia el tema, no donde había una pausa.** Que el
detector de silencios haya quitado cuatro segundos no significa que ahí empiece
una idea nueva: mira la transcripción y comprueba si la frase siguiente abre
algo («y por supuesto», «y es que», «y si quieres») o si sólo continúa una
enumeración. En una enumeración, ninguna transición.

**Para un cambio de tema, usa `pullback`, no un fundido.** El vídeo se encoge
sobre negro, en el hueco que se abre arriba entra un rótulo con lo que se está
diciendo en ese momento, y vuelve a su tamaño. Ese es el recurso que aguanta
tres o cuatro veces en un vídeo sin cansar, porque no interrumpe: **aporta**.
Un fundido a negro, por muy bien hecho que esté, sólo tapa.

```json
"effects": [{"t": 43.13, "type": "pullback", "dur": 3.1, "ramp": 0.5, "scale": 0.74}],
"cards":   [{"t": 43.55, "dur": 3.3, "y_frac": 0.045, "kind": "title",
             "title": "No se puede desperdiciar"}]
```

Las cuentas, para colocar el rótulo. Con `scale` s, el hueco liberado es
`1-s` del alto y el 72% de él va **arriba**: el vídeo ocupa de `(1-s)*0.72` a
`(1-s)*0.72+s`. Con s=0.76 son 332 px de banda negra arriba, así que un
`kind: "title"` en `y_frac` 0.045 cae centrado en ella.

El rótulo entra **0.4-0.5 s después** del inicio del efecto, mientras el plano
todavía se está encogiendo, y sale antes de que vuelva. Así el texto acompaña al
movimiento en vez de aparecer sobre una imagen ya quieta.

`kind: "title"` es texto grande sin panel detrás, porque sobre negro un panel
oscuro se ve como una caja flotando en la nada. Convive con los subtítulos: está
arriba y ellos siguen sobre el vídeo encogido.

**No bajes de `scale` 0.75**: por debajo el desplazamiento del hueco no cabe en
el relleno y el render aborta diciéndolo. El límite no es de gusto, es
aritmética: `s ≥ (1+2b)/(PAD+2b)` con `b = PULLBACK_TOP-0.5`, que con el relleno
actual da 0.742. Y sepáralos bien — dos retrocesos seguidos cansan.

`dip` y `cut_in` **en el mismo instante** siguen siendo válidos para un golpe
seco sin rótulo: el plano cambia mientras la pantalla está oscura, así que el
salto no se ve. Pero para cambiar de tema, el retroceso dice algo y el fundido
no.

**`zoom_punch` no es un tirón de zoom**: hace un push in con easing, **se queda
en el plano cerrado** `hold` segundos y vuelve. Simula el corte a una segunda
cámara. Un pico que sube y baja de inmediato se lee como un temblor; sostener el
encuadre se lee como montaje.

Se dimensiona con `ramp` (0.35 s por defecto) y `hold` (2.0 s), **no con `dur`**.
Por defecto ocupa 2.7 s, así que sirve para abrir secciones, no para puntuar cada
frase. Para el tirón rápido de antes: `{"hold": 0, "ramp": 0.25}`.

**Los zooms no pueden solaparse.** Sus contribuciones se suman en el filtro, así
que dos a la vez dan un zoom doble. `render.py` aborta con los tiempos exactos si
ocurre; `zoom_punch`, `shake` y `whip_pan` cuentan todos como zoom.

Ritmo: un `zoom_punch` cada 8-15 segundos, y flashes o shakes entre medias para
lo puntual. Efecto continuo marea y el espectador se va, que es exactamente lo
contrario de lo que buscas.

**Cards**: anotaciones gráficas que resumen o estructuran lo que se dice.
Mientras una card está en pantalla **los subtítulos se ocultan solos** — dos
bloques de texto compitiendo es lo que hace que una edición parezca amateur.

Se dibujan con Pillow en `scripts/cards.py` y se componen como PNG, no como
texto ASS. Un rectángulo detrás de una línea de texto es lo que hace que una
anotación parezca el título de un PowerPoint; estas tienen cabecera separada del
cuerpo, viñetas alineadas, conectores y esquinas redondeadas.

```bash
python scripts/cards.py plan.json --preset tiktok --outdir cards
python scripts/cards.py plan.json --preset tiktok --outdir cards --animated
python scripts/render.py ... --cards cards
```

**`--animated`** las dibuja con Remotion en vez de con Pillow: las viñetas
entran una a una, el filete se traza, la espina del flujo se dibuja de arriba
abajo y la cifra de una `stat` cuenta hasta su valor. Mismo `plan.json`, mismos
colores del preset; los componentes de React leen el spec directamente, así que
no hay nada que mantener sincronizado entre Python y TypeScript.

Salen `cardNN.mov` (ProRes 4444 con alfa) en vez de `cardNN.png`, y `render.py`
prefiere el `.mov` cuando existe. Eso significa que puedes reanimar una edición
ya hecha volviendo a lanzar sólo este comando.

Cuesta unos **30 s por vídeo** (un bundle de 3.7 s más ~6 s por card) y necesita
Node con las dependencias de `remotion/` instaladas. Si no están, el comando
falla diciéndolo y las cards quietas siguen funcionando: **usa `--animated` por
defecto y cae a las estáticas sólo si no hay Node.**

| `kind` | forma | para qué |
|---|---|---|
| `chip` | píldora compacta con una línea | títulos y rótulos |
| `title` | texto grande, sin panel | en la banda negra que abre un `pullback` |
| `panel` | cabecera de acento + párrafo | una idea con desarrollo |
| `bullets` | cabecera + lista con viñetas | enumerar lo que se dice de corrido |
| `flow` | nodo raíz + espina con nodos conectados | estructura o relación entre partes |
| `stat` | cifra grande + etiqueta | un dato que merece pantalla |

**Los títulos son cards de kind `chip`**, no texto ASS sobre el fotograma: un
rótulo suelto encima del vídeo se lee como encabezado de diapositiva. El `chip`
es la única card que **no** silencia los subtítulos, porque es una etiqueta y no
un bloque de mensaje: convive con ellos sin competir.

**Nada va en mayúsculas.** Ni subtítulos ni títulos ni cabeceras de card. El
texto en caja y en versalitas es exactamente lo que da aspecto de plantilla.

**Varía el tipo.** Repetir el mismo en todas las cards es exactamente lo que las
hace parecer una plantilla. Elige por la forma del contenido: si enumeras, lista;
si hay jerarquía o dependencia, flujo; si es una cifra, stat.

Dónde colocarlas: en los tramos donde el habla es de relleno o enumera algo sin
enseñarlo. Una card que repite palabra por palabra el subtítulo no aporta nada;
una que convierte una frase larga en tres viñetas, sí. En el gancho y en el
remate deja los subtítulos y no pongas card: ahí las palabras exactas importan.

Ritmo: una cada 10-15 segundos como mucho, y **nunca sobre la cara**.

`y_frac` es el borde superior. **No lo estimes de un fotograma: míralo.**

```bash
python scripts/measure.py entrada.mp4 --card 14.6 17.7
```

Sale una lámina con seis fotogramas de esa ventana y las guías de `y_frac`
dibujadas encima. Ábrela y elige la primera línea que quede por debajo de la
barbilla **en los seis**, no en el mejor: una cara quieta engaña, porque al
hablar se gesticula, se inclina y la barba baja.

Esto se mira, no se calcula. La detección automática de piel se probó y falla de
una forma que no se ve venir: una mano que sube al borde inferior cuenta como
cara, y la barba —que es justo lo que no hay que tapar— no es piel para ningún
umbral de color.

Medido así en un plano medio vertical sale **0.68-0.80**, no 0.56: con 0.56 la
card se come la barba, que es el fallo que más se nota. Por abajo, no pases de
**0.85**: TikTok e Instagram ponen ahí su propia interfaz.

La clave `text` ya no existe. `subtitles.py` aborta si la encuentra en vez de
ignorarla en silencio.

`cuts.json` también admite `"speed"` por segmento (`0.5` cámara lenta, `1.5`
acelerado) — útil para comprimir una parte aburrida sin cortarla.

### 4. Subtítulos — siempre después de cortar

```bash
python scripts/subtitles.py words.json -o subs.ass --preset tiktok --plan plan.json
```

`words.json` ya está en la línea de tiempo de salida, del paso 2. `subtitles.py`
rechaza un `words.json` sin cortar, precisamente para que no se cuele una
transcripción del original — si lo hace, es que has editado `cuts.json` y no has
repetido el paso 2.

**En vídeo largo horizontal, no los quemes.** Tapan el código y el espectador
no puede quitarlos. Genera `--srt salida.srt` y que se suba a YouTube como
pista: se activa y se desactiva, y además YouTube **indexa** ese texto, así que
el vídeo aparece en búsquedas por lo que se dice dentro.

**Sobre una grabación de pantalla, encógelos y bájalos.** El sitio por defecto
cae justo encima del contenido que se está enseñando, y dos textos superpuestos
no se leen ninguno. `--fontsize 44 --margin-v 250 --max-chars 40` deja una línea
compacta abajo; mide antes dónde acaba el contenido de la interfaz y dónde
empieza la zona segura de la plataforma, porque el hueco limpio rara vez existe
y hay que elegir el menos malo.

Revisa la transcripción antes de renderizar: whisper confunde palabras poco
frecuentes, nombres propios y muletillas personales. Corrígelas en `words.json`,
que es texto plano.

### 5. Renderizar

```bash
python scripts/render.py entrada.mp4 --cuts cuts.json --subs subs.ass --plan plan.json --preset tiktok -o corto.mp4
```

Un solo pase de ffmpeg desde el original: sin pérdida por recodificaciones
encadenadas. Con más de 300 segmentos pasa automáticamente a dos pases.

`--no-grade` desactiva el color cinematográfico y `--no-polish` el denoise y
el afilado. Los dos juntos son «la imagen original»: lo único que queda sobre el
píxel grabado es el recorte, el encuadre de los efectos y lo que se compone
encima. Con `--no-polish` los cutaways tampoco se afilan, así que un clip de
menos resolución que la salida entra más blando — es el precio de no tocar nada.

Cuando se pide sin filtros, **el igualado de los cutaways sigue haciendo falta**:
no es un look sobre la grabación, es lo que hace que material de otra cámara
pertenezca al mismo vídeo. Y sin grade la referencia es más oscura, así que los
números cambian: mídelos de nuevo contra el original, no reutilices los de una
edición con color. `--print-cmd` imprime el
comando de ffmpeg, que es por donde empezar cuando algo sale raro.

### 5 bis. Capítulos — obligatorios en vídeo largo

Un vídeo de más de cinco minutos se entrega **con capítulos**. No son un extra:
en YouTube son navegación, son retención y salen en el buscador como enlaces
propios.

```json
"chapters": [
  {"t": 0.0,   "title": "Por qué esto casi nadie lo explica"},
  {"t": 80.9,  "title": "El proyecto: Immich, clonado y sin abrir"},
  {"t": 175.3, "title": "Prompt 1 · El mapa de la infraestructura"}
]
```

```bash
python scripts/chapters.py plan.json --cuts cuts.json
```

**Los tiempos van en la línea de salida**, la del vídeo ya cortado, igual que
los efectos y las cards. Este es el error que hay que impedir: escribirlos
mirando la grabación original deja **todos** corridos por lo que quitó el
detector de silencios, y en un vídeo de veinte minutos el desfase llega a varios
minutos. Si has editado `cuts.json` a mano después de escribir los capítulos,
vuelve a pasar el script: los tiempos han cambiado.

`chapters.py` comprueba lo que YouTube exige y que, si falta, hace que descarte
la lista entera **sin decir nada**: el primero en 0:00, un mínimo de tres, y
ninguno de menos de diez segundos. También avisa si alguno cae más allá del
final del montaje, que es la firma de haber usado tiempos sin cortar.

Que un capítulo coincida con un rótulo en pantalla no es obligatorio, pero ayuda:
quien hace scrub ve dónde ha caído.

### 6. Copy de publicación — siempre, sin que lo pidan

Un vídeo sin texto de publicación no está entregado. En cuanto el render
termina, redacta el kit completo a partir de `digest.txt`, que es lo que
de verdad se oye en el vídeo:

- **YouTube**: un título principal + 2 alternativas para testear, descripción y
  **15 tags** separadas por coma
- **Instagram**: caption
- **TikTok**: caption

**El título y las 15 tags no son opcionales.** Van siempre, incluso si el
usuario pide «sólo las descripciones» o «sólo el copy»: sin título no se puede
publicar en YouTube y sin tags se pierde descubrimiento. Entrégalos igual.

Máximo **5 hashtags** por red. En YouTube Shorts uno de ellos es `#Shorts`.

**Los tres objetivos, y qué implica cada uno**

*Descubrimiento.* El término que la gente teclea va **delante** en el título, y
el gancho después. «Trabajo remoto programador» se busca; «reflexión sobre
modelos de trabajo» no lo busca nadie. Las mismas palabras clave tienen que
aparecer en las dos primeras líneas de la descripción, que es lo que indexa y lo
único que se ve antes del «más».

*Retención.* La descripción no resume el vídeo, lo **abre**: plantea la tensión
y deja la resolución dentro. Si cuentas la conclusión en el primer párrafo, ya
no hay motivo para ver.

*Audiencia nueva del nicho.* Nombra explícitamente a quién va dirigido —
freelance, junior, quien busca trabajo— para que el que no te conoce se
reconozca. Y el CTA pide **una anécdota concreta, no una opinión**: «¿te ha
pasado X?» genera hilos entre comentaristas; «¿qué opinas?» genera emojis.

**Reglas que ya costaron un error**

- **No inventes datos, enlaces ni cifras.** Si el vídeo no da una URL, no la
  pongas. Si no estás seguro de un repositorio o un handle, dilo en vez de
  rellenar.
- Usa **las palabras del autor** para los conceptos que ha acuñado: son su marca
  y además son lo que la gente buscará después.
- Si el vídeo aporta un dato personal (años de experiencia, un número), llévalo
  al título o a la primera línea: es lo que separa una opinión de una posición.
- Los hashtags con **ñ** se trocean en Instagram y TikTok: escribe
  `#programacionenespanol`.
- Avisa al usuario de cualquier término que hayas corregido de la transcripción
  y de cualquier afirmación del vídeo que sea atacable sin datos.

## Biblioteca de assets

El usuario puede tener su propia carpeta de música, efectos, stickers, imágenes
y fuentes. **Consúltala antes de escribir `plan.json`**: si no miras el catálogo,
no sabes qué hay y el vídeo sale sin nada de eso.

```bash
python scripts/assets.py --auto                # en CADA edición, antes de plan.json
python scripts/assets.py --set D:/mis-assets   # una vez, para configurarla
```

**`--auto` es obligatorio antes de escribir `plan.json`.** Reindexa y te
devuelve el inventario actualizado, y si el usuario todavía no ha configurado
ninguna biblioteca no falla: avisa y la edición continúa sin música ni
imágenes. Cuesta menos de un segundo con una biblioteca normal, así que no hay
motivo para saltárselo.

Escribe `~/.fragua/assets.json` —fuera del plugin, para que sobreviva a las
actualizaciones— con el inventario clasificado: `music`, `sfx`,
`stickers`, `images` y `fonts`, cada uno con su ruta relativa y sus datos —
duración de los audios, dimensiones y transparencia de las imágenes, familia
tipográfica de las fuentes.

La clasificación es por contenido, no por confianza en el nombre de la carpeta:
un audio de más de 6 segundos es música y por debajo es efecto puntual; una
imagen con canal alfa es sticker y sin él es imagen de fondo.

En `plan.json`, las rutas se escriben **relativas a la biblioteca**:

```json
"music": {"file": "music/lofi.mp3", "gain": -18, "duck": true},
"sfx": [
  {"t": 5.66, "file": "sfx/whoosh.wav"},
  {"t": 11.4, "file": "sfx/pop.wav", "gain": -3}
],
"stickers": [{"file": "stickers/fuego.png", "t": 5, "dur": 2, "scale": 0.22}]
```

**`sfx`** son golpes puntuales que se mezclan sobre la voz sin bajarla. Úsalos
para acompañar lo que ya hace la imagen: un whoosh en un `whip_pan`, un pop
cuando entra una card, un riser antes de un dato. Un efecto que no coincide con
nada de lo que pasa en pantalla se nota como ruido. `gain` por defecto es −6 dB.

**La música sí baja con la voz** (`duck`), y se repite en bucle hasta cubrir el
vídeo. −18 dB es un punto de partida razonable bajo narración.

**Fuentes propias**: si la biblioteca tiene una carpeta `fonts/`, libass usa esa
en vez de las de `vendor/`. Pon en `presets.json` el nombre de familia que el
catálogo reporta, no el nombre del archivo.

Si el usuario no ha configurado nada, la biblioteca es la carpeta `assets/` de la
propia skill y todo funciona igual, solo que vacía.

## Imágenes de apoyo por palabra clave

Si la biblioteca tiene una imagen llamada `youtube.png` y en algún momento el
vídeo dice «YouTube», esa imagen aparece unos segundos en una esquina. Es la
forma más barata de que un vídeo hablado deje de ser sólo una cara.

**Cómo montarlo**, después del paso 2:

1. Lee `~/.fragua/assets.json`. Cada entrada de `images` **y de `stickers`**
   trae un campo `keyword` derivado del nombre del archivo: `claude-code.png` →
   «claude code». Los logos suelen tener alfa, así que caen en `stickers`: si
   sólo miras `images` te pierdes justo los que más sentido tienen.
   Las palabras genéricas se descartan al indexar (`Youtube_logo.png` →
   «youtube»), porque nadie dice «logo de youtube» al hablar.
2. Busca esas palabras en la transcripción, sin distinguir mayúsculas ni tildes.
3. Por cada coincidencia que merezca la pena, añade una entrada a `broll`.

```json
"broll": [
  {"t": 12.4, "dur": 2.5, "file": "images/youtube.png",
   "corner": "top-right", "sfx": "sfx/pop.wav"}
]
```

`t` es el instante en que se dice la palabra, en la línea de tiempo de salida.

**Las reglas que no se negocian**, porque el vídeo es la persona hablando:

- **Nunca a pantalla completa ni sobre la cara.** Sólo esquinas: `top-right`,
  `top-left`, `bottom-right`, `bottom-left`. En vertical la cara ocupa la franja
  central, así que las esquinas superiores suelen ser fondo.
- **El tamaño está topado** al 40% del ancho por código. Por defecto va al 28%.
- **Una imagen cada 8 segundos como mínimo**, y nunca mientras hay una card en
  pantalla: dos elementos gráficos a la vez es ruido.
- **No la pongas en cada mención.** Si dice «YouTube» seis veces, va una. Elige
  la primera o la más enfática, no todas.
- **Sólo si aporta.** Un logo cuando se nombra la marca ayuda a fijar la idea;
  una foto genérica cuando dice «trabajo» es relleno y se nota.

**El sonido de entrada** (`sfx`) es opcional y va con las mismas reglas que
cualquier efecto: corto, sutil y **cede ante la voz**. Bajar la ganancia no
basta —dos señales se suman, así que el pico de voz+efecto siempre supera al de
la voz sola por mucho que se atenúe—, por eso el efecto pasa por un
`sidechaincompress` con la voz de llave. Medido: el nivel percibido no sube
(−13.1 dB con y sin efecto) y el pico sólo sube 1.4 dB, que es el mínimo de
cualquier capa aditiva.

## Planos de recurso

Un `cutaway` es un clip de vídeo tuyo que **tapa la imagen mientras el audio
original sigue corriendo**. Eso es lo que lo hace leerse como un cambio de
cámara y no como un corte: la voz no se interrumpe, sólo cambia lo que se ve.

```json
"cutaways": [
  {"t": 41.0, "dur": 3.6, "file": "clip 2.mp4", "start": 1.2,
   "grade": "eq=brightness=-0.075:saturation=0.80"}
]
```

`start` es desde dónde empieza a leerse el clip; si pides más metraje del que
queda, el render aborta diciéndolo en vez de sacar negro. `fade` (0.35 s por
defecto, 0 para corte seco) funde la entrada y la salida en alfa.

**Entra en una pausa, no en mitad de una palabra.** Busca los huecos reales
entre palabras de `words.json` —los mayores de 0.25 s— y pon el `t` justo antes
de uno, para que el fundido caiga sobre el silencio. Un plano de recurso que
aparece mientras se pronuncia una sílaba se nota aunque esté bien elegido; el
mismo plano entrando en la respiración entre dos frases, no.

```bash
python - <<'PY'
import json
w = json.load(open("words.json", encoding="utf-8"))["words"]
for a, b in zip(w, w[1:]):
    if b["start"] - a["end"] > 0.25:
        print(f'{a["end"]:.2f} -> {b["start"]:.2f}   ...{a["text"]} | {b["text"]}...')
PY
```

**Iguala el color, siempre.** Un clip de otra cámara casi nunca cae en el mismo
brillo ni en la misma saturación, y el salto se lee como «otro vídeo» en vez de
«otro plano». Mide los dos lados y escribe el ajuste en `grade`:

```bash
python scripts/measure.py entrada.mp4 --match clip1.mp4 clip2.mp4 clip3.mp4
```

Medido en un caso real: la persona estaba en YAVG 58 y SATAVG 14, y los tres
clips en 47/10, 86/19 y 93/34. Sin igualar, los tres cantaban.

**Dónde ponerlos.** Donde la cara no aporte nada: un tramo explicativo largo,
una enumeración, una idea abstracta. Nunca sobre el gancho ni sobre el remate —
ahí la expresión es el contenido. Tres o cuatro segundos cada uno: menos no da
tiempo a leerlos, más y se pierde a quien habla.

No pueden solaparse entre sí ni caer sobre un `pullback` —taparían el vídeo
encogido y su rótulo— y `render.py` aborta con los tiempos si ocurre.

Van **después del color y antes de los subtítulos**: cada clip conserva su look
y los subtítulos siguen corriendo por encima, porque la persona sigue hablando.

`assets.py` los cataloga bajo `clips`, con su duración y su tamaño.

## Memoria de recomendaciones

Las sugerencias sobre el contenido no sirven de nada si nadie lleva la cuenta de
si se aplican. `scripts/coach.py` guarda esa memoria en
`~/.fragua/coaching.json`, fuera del plugin.

**Antes de opinar sobre un vídeo**, lee el historial:

```bash
python <skill>/scripts/coach.py
```

Te dice qué recomendaciones se han aplicado, cuáles se repiten sin aplicarse y
cuáles se corrigieron después de señalarlas. Úsalo para no repetir mecánicamente
lo mismo: si algo lleva tres vídeos pendiente, deja de mencionarlo de pasada y
conviértelo en el tema principal de tu opinión, con una propuesta concreta de
cómo resolverlo en la próxima grabación. Y si algo se ha corregido, **dilo**:
reconocer la mejora es la mitad del valor de este registro.

**Después de editar**, registra la evaluación:

```bash
python <skill>/scripts/coach.py log --file "salida.mp4" --topic "de qué va"   --applied hook-al-inicio,dato-concreto --pending anecdota-personal
```

Los criterios son un catálogo cerrado (`coach.py checks`), y eso es
deliberado: una sugerencia en texto libre no se puede comparar entre vídeos,
porque «mejora el gancho» dicho en marzo y en agosto son cadenas distintas.
Evalúa **todos** los criterios que apliquen, no sólo los que fallan: sin los
cumplidos no hay forma de detectar una mejora.

Sé honesto al evaluar. Marcar como cumplido algo que no lo está rompe el
historial y hace inútil el registro entero.

## Presets

`youtube_long` (1920×1080), `tiktok`, `reels`, `youtube_short` (1080×1920). Todos
normalizan a −14 LUFS, que es lo que las tres plataformas esperan.

Edita `presets.json` para cambiar fuente, tamaño o colores de subtítulo. Los
colores van en formato ASS `&HAABBGGRR` — azul y rojo invertidos respecto a HTML.

Un mismo vídeo se exporta a varias plataformas cambiando `--preset`, pero
regenera `subs.ass` con el mismo preset: el tamaño de letra y el número de
caracteres por línea cambian entre vertical y horizontal.

El recorte a vertical es **centrado**. Si el sujeto no está en el centro del
encuadre original, quedará descuadrado; graba centrado o recorta a mano antes.

## Lo que hace el render siempre

**Imagen**: denoise suave y `cas` (sharpening adaptativo al contraste)
**enmascarado por luma**. El look cinematográfico por defecto son sombras hacia
el azul, luces hacia el cálido, contraste suave, viñeta y grano fino.

La máscara no es un adorno. `cas` afila el contraste local que encuentre, y en
una zona plana y oscura —una camiseta negra, un fondo en penumbra— el único
contraste local que hay son los bloques que dejó el códec del original. Sin
máscara los convierte en textura nítida, y eso se percibe como pixelado. Medido
sobre el mismo fotograma:

| | camiseta (plano oscuro) | cara (detalle real) |
|---|---|---|
| sin afilar | referencia | referencia |
| `cas` suelto | **+121%** | +104% |
| `cas` enmascarado | **+15%** | +38% |

Se pierde algo de nitidez en la cara a cambio de multiplicar por ocho la mejora
en las sombras. `SHARPEN_FLOOR` (45) es la luma por debajo de la cual no se
afila nada, y `SHARPEN_RAMP` (50) el ancho de la transición.

**Audio**, cadena de voz en este orden — limpiar antes de realzar, o el EQ
amplifica justo el ruido que el denoiser debía quitar:

`highpass` 85 Hz (retumbe y plosivas) → `afftdn` (ruido de sala) → −2.5 dB en
280 Hz (quita el "cartón") → +3 dB en 3.2 kHz (presencia: ahí vive la
inteligibilidad) → +1.5 dB en 8 kHz (aire) → `deesser` → compresor →
`loudnorm` a −14 LUFS → fundido de 0.35 s.

Ese fundido final no es decorativo: evita que un corte seco sobre la última
palabra se perciba como una frase truncada.

## Fuentes y estilo

`setup.ps1` descarga a `vendor/fonts/` **Roboto** (variable), **Poppins
ExtraBold** y **Anton**, todas OFL con su licencia. `render.py` se las pasa a
libass por `fontsdir`, sin instalarlas en el sistema.

Dos trampas al cambiar de fuente:

**Roboto sólo existe como fuente variable.** libass no sintetiza negrita: pedir
`"fontname": "Roboto"` con `bold: -1` da Regular, demasiado fina. Hay que pedir
la **instancia nombrada**: `"fontname": "Roboto Black"` con `bold: 0`.

**Recalibra `fontsize`.** La altura de mayúscula varía mucho entre familias, así
que el mismo tamaño nominal rinde distinto. Renderiza un fotograma antes de
lanzar el vídeo entero.

Campos de estilo en `presets.json`:

| campo | qué hace |
|---|---|
| `border_style` | 1 = contorno, 3 = caja de fondo |
| `box` | color de la caja cuando `border_style` es 3 |
| `outline` | con `border_style` 3 es el **relleno interior**, no el grosor del contorno |
| `primary` / `secondary` | color de palabra ya dicha / pendiente, en el barrido karaoke |
| `title_scale`, `card_scale` | tamaño de títulos y cards relativo al subtítulo |

Los colores van en formato ASS `&HAABBGGRR`: azul y rojo invertidos respecto a
HTML, y **el alfa es al revés de lo intuitivo** — `00` es opaco y `FF`
transparente. Una caja casi negra sobre fondo oscuro apenas se ve por mucha
opacidad que le pongas; si la quieres visible, súbele también la luminosidad.

## Cuando algo falla

| síntoma | causa |
|---|---|
| "todo el vídeo se detectó como silencio" | `--threshold` demasiado alto; prueba `-40` |
| "words.json viene del vídeo sin cortar" | falta `--cuts` en `transcribe.py` |
| timestamps más allá del final del vídeo | deriva de whisper; transcribe el tramo suelto |
| falta un trozo de la transcripción | whisper salta zonas con tomas repetidas; transcríbelas aparte |
| "plan.json usa 'text'" | los títulos son cards de kind `chip` |
| subtítulos desincronizados | tocaste `cuts.json` sin rehacer los pasos 4 |
| se ve pixelado | `crf` alto, o `hqdn3d` duplicado en `"grade"` |
| pixelado en camiseta o zonas negras | el afilado entra en las sombras: sube `SHARPEN_FLOOR` |
| medir artefactos da cifras absurdas | el recorte pilla la caja del subtítulo; mide por encima de `margin_v` |
| el audio se corta sobre la última palabra | no debería pasar: `analyze.py` alarga los finales solo. Si pasa, mira si el segmento lo editaste tú a mano |
| subtítulos diminutos tras cambiar de fuente | `fontsize` no recalibrado; cada familia tiene otra altura de mayúscula |
| la fuente sale fina pese a `bold: -1` | es variable; pide la instancia (`Roboto Black`), libass no sintetiza negrita |
| no se ve la caja de fondo | es casi negra sobre fondo oscuro; sube luminosidad, no sólo opacidad |
| card tapando la cara | ajusta `y_frac` (~0.56-0.64) y compruébalo en un fotograma |
| el reflejo queda como mancha gris | `deglare.strength` demasiado alto; baja de 0.75 |
| `deglare` apaga brillos de la piel | sube `sat_max`, la piel es más cromática que un especular |
| "faltan cards: ..." | ejecuta `cards.py` antes de `render.py`, o pasa `--cards` |
| las cards parecen plantilla | estás repitiendo `kind`; varíalo según la forma del contenido |
| "efectos de zoom solapados" | dos zooms a la vez se suman; sepáralos o baja `hold` |
| el zoom parece un tirón | estás usando `dur`; `zoom_punch` se dimensiona con `ramp` y `hold` |
| el movimiento parece lento o con estelas | denoise temporal doble; quita `hqdn3d` de `"grade"` |
| se ve lavado o demasiado brillante | la curva no cierra el techo; baja el último punto a `1/0.95` |
| letra minúscula o gigante | preset de `subtitles.py` distinto al de `render.py` |
| ffmpeg peta al parsear el filtro | ejecuta con `--print-cmd` y mira el filtergraph |
| whisper.cpp no encontrado | falta `scripts/setup.ps1` |

Lo que no se arregla en post: si grabas a 30 fps con obturador lento, los gestos
rápidos salen movidos en el original y ahí se quedan. Sube la velocidad de
obturación al grabar.

## Assets

`assets/` está vacío y todo funciona sin él. Si metes música o stickers, los usas
desde `plan.json`. Ver `assets/README.md` para la estructura y el aviso de licencias.

## Versión

Si te preguntan qué versión es, léela de `.claude-plugin/plugin.json` (campo
`version`) y resume lo que trae desde `CHANGELOG.md`, que está ordenado de más
nueva a más antigua.

Al añadir una funcionalidad, sube la versión en **los dos** manifiestos y abre
una entrada nueva en el changelog escrita para quien usa la skill, no para quien
la programa: qué puede hacer ahora que antes no. `test_pipeline.py` comprueba
que los tres números coinciden.

## Instalación como skill

Copia esta carpeta a `~/.claude/skills/fragua/` para que se active sola al
pedir una edición.

---

Fragua · MIT · [Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)
