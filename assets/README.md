# assets

Opcional. El pipeline funciona con esta carpeta vacía; lo que metas aquí se
referencia desde `plan.json` con rutas relativas a la raíz del proyecto.

```
assets/
  music/      mp3/wav de fondo   -> {"music": {"file": "assets/music/x.mp3"}}
  stickers/   png con alpha      -> {"stickers": [{"file": "assets/stickers/x.png"}]}
  sfx/        whoosh, pop, riser -> mézclalos en la pista de música o añádelos aparte
```

La música se repite en bucle hasta cubrir el vídeo y baja de volumen sola cuando
hay voz (`"duck": true`, por defecto). `gain` en dB, `-18` es un punto de partida
razonable para música bajo narración.

Los stickers son PNG con transparencia. WebM con alpha también funciona en
ffmpeg pero necesita `-c:v libvpx` en la entrada; usa PNG salvo que necesites
animación.

## Licencias

**No metas aquí assets de CapCut, TikTok o similares.** Están licenciados para
usarse dentro de esas apps; extraerlos para un pipeline externo viola sus
términos, y su música dispara Content ID en YouTube.

Fuentes utilizables: Pixabay Music, Mixkit, Freesound (filtra por CC0), YouTube
Audio Library. Guarda la licencia de cada pista en `music/LICENSES.txt` — dentro
de seis meses no vas a acordarte de dónde salió cada archivo, y es justo lo que
te van a pedir si llega un claim.
