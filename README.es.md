# Fragua

*[Read this in English](README.md)*

Una skill para **Claude Code** y **OpenCode** que convierte una grabación en
bruto en un vídeo listo para publicar en TikTok, Reels o YouTube Shorts.

Le pasas el vídeo por el chat y el agente lo edita: quita los silencios, quema
subtítulos, añade cambios de plano y tarjetas gráficas, corrige el color,
normaliza el audio y, al terminar, te redacta el título, la descripción, las
etiquetas y los textos para cada red.

Todo ocurre **en tu ordenador**. No hay ninguna API key, ningún servicio de pago
y ningún archivo tuyo sale de la máquina.

---

## Instalación

### Claude Code

Se instala como cualquier otro plugin, desde dentro de Claude Code:

```
/plugin marketplace add pedrovelasquez9/fragua
/plugin install fragua@fragua
```

Después hay que preparar las dependencias una vez —ffmpeg, Python, el modelo de
transcripción y las fuentes—. Basta con pedírselo al agente:

```
/fragua:setup
```

O lanzarlo tú desde la carpeta instalada:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
```
```bash
./scripts/setup.sh                                            # macOS y Linux
```

El setup descarga unos 1,6 GB, instala con `winget`, `brew` o tu gestor de
paquetes lo que falte, y termina con una comprobación automática. Cuando veas
**`todo verde`**, ya está.

### OpenCode

OpenCode no tiene marketplace, así que se clona el repositorio y se ejecuta el
instalador:

```bash
git clone https://github.com/pedrovelasquez9/fragua
cd fragua
./install.sh --target opencode                                # macOS y Linux
```
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Target opencode   # Windows
```

El instalador copia la skill donde OpenCode la busca, resuelve todas las
dependencias y ejecuta la suite de verificación.

### Comandos

Dentro de Claude Code, Fragua añade dos comandos:

| Comando | Para qué |
|---|---|
| `/fragua:setup` | Instala y verifica todo lo que necesita. Se lanza una vez tras instalar |
| `/fragua:assets <carpeta>` | Apunta Fragua a tu música, efectos, stickers y fuentes, e indexa lo que haya |

Editar no necesita comando: basta con pedirlo.

### Opciones del instalador

| Opción | Para qué |
|---|---|
| `--target claude` / `--target opencode` | Instala solo para un agente (por defecto, ambos) |
| `--project` | Instala en la carpeta actual en vez de en todo el sistema |
| `--model ggml-medium` | Modelo más pequeño: 1,4 GB menos de descarga, más rápido y con algún fallo más |

En Windows las mismas opciones van con sintaxis de PowerShell: `-Target`,
`-Project`, `-Model`.

### Actualizar

```
/plugin marketplace update fragua        # Claude Code
```

```bash
git pull && ./install.sh                 # OpenCode
```

> No copies la carpeta `vendor/` entre máquinas. Son 1,5 GB que el setup vuelve
> a generar en cada ordenador.

### ¿Qué versión tengo?

Pregúntaselo al agente — `¿qué versión de fragua es esta?` — y te la dice, junto
con lo que ha cambiado desde la tuya.

En **[CHANGELOG.md](CHANGELOG.md)** está cada versión y lo que trajo, de la más
nueva a la más antigua. Merece un vistazo después de actualizar: casi todo lo
nuevo funciona sin que tengas que hacer nada, así que es fácil no enterarte de
que ya está ahí.

---

## Cómo se usa

No hay comandos que memorizar. Abre Claude Code u OpenCode y **pídelo en
lenguaje normal**, indicando la ruta del vídeo:

```
edita este vídeo para tiktok: C:\Users\yo\Videos\grabacion.mp4
```

El agente reconoce la skill y se pone a trabajar. Tarda entre cinco y quince
minutos según lo largo que sea, y va contándote lo que encuentra.

### Qué hace mientras tanto

1. **Mide el vídeo**: duración, brillo, ruido de fondo
2. **Detecta los silencios** y los recorta
3. **Transcribe lo que dices** para poder leerlo
4. **Decide el montaje**: aquí es donde te avisa si has grabado una toma dos
   veces, si te trabas, o si los primeros segundos son aire muerto
5. **Diseña las tarjetas** que resumen tus ideas en pantalla
6. **Renderiza** y te devuelve el archivo
7. **Escribe el copy** de publicación para YouTube, Instagram y TikTok

### Qué le puedes pedir

Todo esto funciona tal cual, escrito en el chat:

```
edita este vídeo y dame tu opinión del contenido
```
```
edítalo para reels en vez de tiktok
```
```
los subtítulos están muy grandes, bájalos y vuelve a renderizar
```
```
quita la segunda tarjeta, tapa lo que estoy enseñando
```
```
genera solo el título y la descripción para youtube
```
```
usa la toma del final, no la primera
```

Si algo no te convence, **díselo y lo rehace**. No hace falta que sepas qué
parámetro tocar: describe lo que ves («se ve pixelado en la camiseta», «el audio
se corta al final») y él localiza la causa.

### Qué te devuelve

- El vídeo editado, junto al original y con `-EDIT` en el nombre
- Una carpeta con los archivos del proyecto, por si quieres retocar algo después
  sin repetir todo el proceso
- El texto de publicación: título, descripción, 15 etiquetas y los pies para
  Instagram y TikTok

---

## Tus propios assets

Fragua puede sacar música, efectos de sonido, stickers, imágenes y fuentes de una
carpeta tuya. Apúntala una vez:

```
/fragua:assets D:/mis-assets
```

En OpenCode no hay slash commands, así que basta con decirlo:
`usa D:/mis-assets como mi carpeta de assets`.

Organízala como quieras —la clasificación mira los archivos, no el nombre de las
carpetas—, pero esta es la estructura que espera:

```
mis-assets/
  music/     pistas largas de fondo
  sfx/       golpes cortos: whoosh, pop, riser
  stickers/  PNG con transparencia
  images/    capturas, logos, fondos
  fonts/     tus .ttf u .otf
```

No tienes que reindexar nunca. Cada edición refresca el catálogo antes de
empezar, así que lo que metas en la carpeta por la mañana ya está disponible por
la tarde. `/fragua:assets` sigue ahí si quieres ver el inventario.

A partir de ahí el agente sabe qué tienes y lo usa por su cuenta: un whoosh sobre
un barrido, un pop cuando entra una tarjeta, tu pista bajo la voz —con ducking
automático para que nunca compita con la narración—. También puedes pedírselo
directamente: `mete la pista lofi de fondo y un pop en cada tarjeta`.

El catálogo se guarda en `~/.fragua/assets.json`, fuera del plugin, así que
sobrevive a las actualizaciones.

Si no configuras nada, Fragua usa su propia carpeta `assets/` vacía y todo lo
demás funciona igual.

> La música de CapCut o TikTok está licenciada solo para esas apps y genera
> reclamaciones de copyright en YouTube. Usa fuentes CC0 como Pixabay, Mixkit o
> Freesound.

### Imágenes que aparecen cuando mencionas algo

Mete en tu carpeta de assets una imagen con el nombre de una palabra
—`youtube.png`, `claude-code.png`, `github.png`— y cuando el vídeo diga esa
palabra, la imagen sale un par de segundos en una esquina.

No hay nada que configurar ni que ejecutar: el nombre del archivo **es** la
palabra que la dispara, y cada edición reindexa la carpeta antes de empezar.

Nunca te tapa la cara ni ocupa la pantalla: sólo esquinas, con el tamaño topado
al 40% del ancho y una imagen cada ocho segundos como máximo. El sonido de
entrada, si se lo pones, cede ante tu voz para no competir con lo que dices.

### Cambios de plano y transiciones

Donde cambia el tema, el vídeo se encoge sobre negro y en el hueco que se abre
arriba entra un rótulo con lo que acabas de decir, y luego vuelve a su tamaño.
Un fundido a negro sólo tapa la junta; esto la aprovecha, así que se puede usar
tres o cuatro veces en un vídeo sin cansar.

Los cambios de plano son movimientos, no saltos: casi un segundo de recorrido,
saliendo de parado y frenando sin tirón. Y cuando una frase pide un salto de
verdad, el encuadre cambia entre un fotograma y el siguiente, como quien corta a
una segunda cámara.

Nada de esto lo eliges tú por su nombre. El agente lee tu transcripción, busca
las frases que pesan y pone el movimiento en su primera palabra — nunca
repartido por reloj, que es lo que hace que una edición parezca aleatoria.

### Cards animadas

Las cards pueden dibujarse con movimiento en vez de quietas: las viñetas entran
una a una, el filete bajo el título se traza solo y una cifra cuenta hasta su
valor. Se piden hablando — `edítalo con cards animadas` — y ya está.

Son componentes de React renderizados con [Remotion](https://remotion.dev), y
eso implica dos cosas que conviene saber. Añade alrededor de medio minuto a cada
edición. Y si escribes React, inventarte un tipo de card nuevo es escribir un
componente en `remotion/src/Card.tsx`, sin tocar nada de Python.

Remotion es opcional y **no** se instala por defecto, porque arrastra Node y su
propio Chrome. Si ya tienes Node, `/fragua:setup` te lo deja listo. Sin él, todo
funciona igual que antes con las cards quietas.

### Recuerda lo que te ha recomendado

Después de cada edición, Fragua anota qué recomendaciones sobre el contenido
aplicaste y cuáles no. La siguiente vez consulta ese historial antes de opinar.

Así, si algo lleva tres vídeos pendiente, deja de mencionarlo de pasada y lo
convierte en el tema principal. Y cuando corriges algo, te lo dice en vez de
repetirte la misma nota para siempre.

Puedes pedir el informe cuando quieras: `¿estoy mejorando?`

---

## Consejos para grabar

La skill arregla mucho, pero hay cosas que se ganan mejor en la grabación. Estas
tres son las que más han salido en la práctica:

**Cuida el reflejo de las gafas.** Si el monitor se refleja en los cristales,
tapa tus ojos y ningún filtro lo recupera del todo. Baja el brillo de la
pantalla, muévela fuera del eje de la cámara o inclina un poco las patillas.

**No pasa nada por repetir una toma.** El agente detecta las repeticiones y se
queda con la buena. Si te trabas, para y repite la frase entera.

**Deja el gancho al principio.** La frase más fuerte del vídeo debería estar en
los primeros cinco segundos, no en el segundo cuarenta. Si te sale al final, el
agente te lo dirá, pero no puede reordenarte el discurso sin que se note.

---

## Si algo va mal

| Lo que ves | Qué hacer |
|---|---|
| El agente dice que no encuentra ffmpeg | Vuelve a lanzar el setup y abre un terminal nuevo para que refresque el PATH |
| «falta whisper.cpp» o similar | Vuelve a lanzar el setup; se puede repetir tantas veces como quieras |
| Los subtítulos no coinciden con lo que dices | Pídele que revise la transcripción, que es un archivo de texto que puede corregir |
| El vídeo tarda muchísimo | Normal en grabaciones largas. Con `--model ggml-medium` va bastante más rápido |
| Se instaló pero el agente no la usa | Comprueba que la carpeta se llama exactamente `fragua` |

Para cualquier otra cosa, pregúntale directamente al agente: tiene la
documentación técnica completa y sabe diagnosticar sus propios fallos.

---

## Para desarrolladores

Si quieres entender el pipeline por dentro, ejecutar los scripts a mano o
modificar los parámetros de color, efectos y tipografía, todo está en
**[TECHNICAL_README.md](TECHNICAL_README.md)**.

---

## Licencia

Fragua se publica bajo licencia **MIT**: úsala, modifícala y distribúyela como
quieras. Ver [LICENSE](LICENSE).

Lo que descarga el setup trae sus propias licencias, todas permisivas:
whisper.cpp y el modelo Whisper bajo MIT, y las fuentes Roboto, Anton y Poppins
bajo SIL Open Font License.

Si añades música o stickers propios en `assets/`, la licencia corre de tu cuenta.
**No uses material de CapCut o TikTok**: está licenciado solo para esas apps y su
música genera reclamaciones de copyright en YouTube.

---

Hecho por **[Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)**
