# Fragua

Una skill para **Claude Code** y **OpenCode** que convierte una grabación en
bruto en un vídeo listo para publicar en TikTok, Reels o YouTube Shorts.

Por [Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)

Le pasas el vídeo por el chat, y el agente lo edita: quita los silencios, quema
subtítulos, añade cambios de plano y tarjetas gráficas, corrige el color,
normaliza el audio y, al terminar, te redacta el título, la descripción, las
etiquetas y los textos para cada red.

Todo ocurre **en tu ordenador**. No hay ninguna API key, ningún servicio de pago
y ningún archivo tuyo sale de la máquina.

---

## Instalación

### 1. Requisitos previos

Necesitas dos cosas instaladas antes de empezar:

**ffmpeg**

```bash
winget install Gyan.FFmpeg     # Windows
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Linux
```

**Python 3.9 o superior** — desde [python.org](https://www.python.org/downloads/)
o el gestor de paquetes de tu sistema.

Para comprobar que están:

```bash
ffmpeg -version
python --version
```

### 2. Instalar la skill

Un solo comando desde la carpeta de la skill. Copia los archivos donde los
agentes los buscan, descarga lo que necesita y verifica que todo funciona.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

**macOS y Linux**

```bash
chmod +x install.sh && ./install.sh
```

Tarda unos minutos: descarga el modelo de transcripción, que ocupa 1,6 GB. Al
acabar ejecuta una comprobación automática; si ves **`todo verde`**, ya está.

Por defecto instala para Claude Code y OpenCode a la vez. Si solo usas uno:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Target claude
powershell -ExecutionPolicy Bypass -File install.ps1 -Target opencode
```

```bash
./install.sh --target claude
./install.sh --target opencode
```

Otras opciones:

| Opción | Para qué |
|---|---|
| `-Project` / `--project` | Instala solo para la carpeta actual, no para todo el sistema |
| `-Model ggml-medium` / `--model ggml-medium` | Modelo más pequeño: descarga 1,4 GB menos y transcribe más rápido, con algún fallo más |

> **Ordenador nuevo**: repite estos dos pasos. No copies la carpeta `vendor/`
> entre máquinas, son 1,5 GB que el instalador vuelve a descargar solo.

---

## Cómo se usa

No hay comandos que memorizar. Abre Claude Code u OpenCode y **pídelo en lenguaje
normal**, indicando la ruta del vídeo:

```
edita este vídeo para tiktok: C:\Users\yo\Videos\grabacion.mp4
```

El agente reconoce la skill y se pone a trabajar. Tarda entre cinco y quince
minutos según lo largo que sea el vídeo, y va contándote lo que encuentra.

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
| El agente dice que no encuentra ffmpeg | Instálalo (arriba) y reinicia el terminal para que actualice el PATH |
| «falta whisper.cpp» o similar | Vuelve a lanzar el instalador; se puede ejecutar tantas veces como quieras |
| Los subtítulos no coinciden con lo que dices | Pídele que revise la transcripción, que es un archivo de texto que puede corregir |
| El vídeo tarda muchísimo | Normal en grabaciones largas. Con `-Model ggml-medium` va bastante más rápido |
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

Lo que descarga el instalador trae sus propias licencias, todas permisivas:
whisper.cpp y el modelo Whisper bajo MIT, y las fuentes Roboto, Anton y Poppins
bajo SIL Open Font License.

Si añades música o stickers propios en `assets/`, la licencia corre de tu cuenta.
**No uses material de CapCut o TikTok**: está licenciado solo para esas apps y su
música genera reclamaciones de copyright en YouTube.

---

Hecho por **[Pedro Plasencia - Programación en español](https://programacion-es.dev/redes)**
