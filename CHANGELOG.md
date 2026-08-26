# Changelog

Every released version of Fragua, newest first. Dates are the day the change
landed.

To see which version you have installed, ask the agent `what version of fragua
is this?`, or read `version` in `.claude-plugin/plugin.json`.

---

## 1.14.2 — 2026-08-26

### Added
- El changelog se comprueba entero, no sólo su primera línea: entradas ordenadas
  de la más nueva a la más vieja, cada una con fecha ISO, y **ninguna versión
  etiquetada sin entrada**. Ese último es el fallo que ocurrió de verdad: 1.11.0
  llegó a etiquetarse sin subir la versión ni cerrar la documentación, y nada
  avisó. En un clon sin `git` la comprobación se salta en vez de fallar.
- Queda escrito en la skill lo que hasta ahora sólo era costumbre: el trabajo va
  en rama con git flow y conventional commits, y cada versión que llega a `main`
  lleva su tag. Sin tag no hay `install.sh --version`, así que una versión sin
  etiquetar es una a la que nadie puede volver.

---

## 1.14.1 — 2026-08-26

Los dos fallos de esta versión salieron editando un vídeo real con 1.14.0, no
leyendo el código: uno estaba en el log del render y el otro en el resultado.

### Fixed
- **Los subtítulos salían en Arial.** Los presets pedían `Roboto Black`, pero
  Roboto se vendoriza como fuente variable y libass no saca de ahí la instancia
  Black: resolvía a ArialMT sin decir nada. Medido con libass 0.17.5, tampoco
  cambia con `bold=1`. Los presets pasan a `Poppins ExtraBold`, que ya venía
  descargada como estática y sí resuelve. Un comentario del setup afirmaba lo
  contrario desde el principio; nunca se había comprobado.
- **`render.py` se comía las cards sin avisar.** Sin `--cards` devolvía la lista
  vacía y el vídeo salía sin las cards que `plan.json` pedía — y el comando de
  render que documentaba la skill **no llevaba `--cards`**, así que el fallo
  silencioso era el caso normal. Ahora, si el plan pide cards, se buscan en
  `cards/` junto al plan, y si falta alguna se aborta con el fichero que falta.
- El comando de render de la skill lleva `--cards` explícito, como el del
  README técnico, que sí lo tenía.

### Added
- Comprobación de que la fuente que pide cada preset es la que libass acaba
  dibujando. El fallback de fuente es silencioso por diseño, así que sin esto
  vuelve a pasar desapercibido.

---

## 1.14.0 — 2026-08-26

Una edición gastaba mucho más contexto del necesario en trabajo mecánico. Lo
mecánico se ha bajado a scripts; el criterio editorial —qué se corta, dónde va
un efecto, qué merece una card— sigue siendo del agente, sin tocar.

### Added
- **`measure.py`**: formato, brillo, saturación y sonoridad de un vídeo en una
  llamada y en unas pocas líneas. Antes eran unas quince invocaciones sueltas de
  `ffprobe` y `ffmpeg`, cada una devolviendo su log entero. `--at` mide un
  instante concreto y `--match` compara el color de un plano de recurso con el
  del vídeo.
- **`measure.py --card inicio fin`** monta una sola lámina con seis fotogramas de
  la ventana de una card y las guías de `y_frac` dibujadas encima, en vez de seis
  fotogramas sueltos que había que medir a ojo uno a uno. No decide nada: la
  detección automática de piel se probó y falla de forma que no se ve venir —una
  mano que sube al borde inferior cuenta como cara, y la barba, que es justo lo
  que no hay que tapar, no es piel para ningún umbral de color— así que esto se
  sigue mirando, que es el método que funciona.
- **`transcribe.py --digest`** escribe la transcripción frase a frase con los dos
  tiempos: el del montaje, que va a `plan.json`, y el de la grabación, que hace
  falta para borrar un segmento de `cuts.json`. Medido sobre un vídeo de 17
  minutos: `words.json` son 294 KB de andamiaje JSON y el digest 21 KB con
  exactamente las mismas palabras.
- `output_to_source()` en `common.py`, el inverso de `source_to_output()`.

### Changed
- **Se transcribe una vez, no dos.** El flujo hacía una pasada sobre el original
  para leerla y otra sobre el audio ya cortado para los subtítulos. Con los dos
  tiempos en el digest, la pasada sobre el cortado sirve para las dos cosas: se
  ahorra una transcripción entera de whisper y una lectura completa del texto.
- La documentación decía «lee `words.json`» en un punto del flujo en el que ese
  fichero todavía no existía —lo que existía era `draft.json`—. Ya no hay dos
  ficheros que confundir.

---

## 1.13.1 — 2026-08-26

### Added
- **Install a specific version.** `./install.sh --version v1.12.0` (or
  `-Version` on PowerShell) checks out that tag before copying anything, so any
  released version can be reinstalled exactly as it shipped. It refuses to run
  on a dirty tree: copying local changes under a tag that does not have them
  would leave you believing you are on the version you asked for. If the tag
  does not exist it prints the ones that do.
- Documented the rollback path for Claude Code, which is different because the
  plugin is registered rather than copied: `plugin marketplace add` accepts a
  local folder, so cloning the repository at a tag and registering that folder
  pins the version. Verified end to end on v1.11.0.

### Fixed
- `install.ps1` could not install anything. A `\f` inside the literal
  `skills\fragua\SKILL.md` had been turned into a form feed, so the path never
  matched and the script died on its own sanity check. It now builds the path
  from `$SkillName`, which cannot break the same way.

---

## 1.13.0 — 2026-08-25

### Added
- **Chapters, and they are now required on anything long.** `chapters.py` reads
  them from `plan.json` and prints the block YouTube expects. The timings live on
  the output timeline like everything else in the plan, so they are right by
  construction — writing them against the raw recording is the classic mistake,
  and on a twenty-minute video the drift runs to minutes.
- The three rules YouTube enforces silently are checked before you paste
  anything: first chapter at 0:00, at least three, none under ten seconds. Miss
  one and YouTube shows no chapters at all without saying why. A chapter landing
  past the end of the edit is reported too, since that is the signature of
  uncut timings.
- `subtitles.py --srt` writes a plain subtitle track. On a wide long video that
  is what belongs: burnt captions cover the code and cannot be switched off,
  while an uploaded track is toggleable and gets indexed by YouTube.

### Fixed
- A cut with a couple of hundred segments could not be rendered on Windows: the
  filtergraph blew past the 32 KB command-line limit before ffmpeg started. It
  now goes to ffmpeg in a file, so the ceiling stops existing instead of being
  dodged with a segment threshold. Measured on a 17-minute edit with 277
  segments.

---

## 1.12.0 — 2026-08-25

### Fixed
- **Word tails were being clipped at every cut, not just the last one.** The cut
  is decided at the silence threshold, but the tail of a consonant keeps
  sounding below it — end the segment there and you hear «có—» instead of
  «código». A second, more sensitive pass now finds where the sound actually
  stops and extends each end to meet it, never past the next segment. On two
  real recordings it rescued six and seven endings.
- The render closes with a 0.35 s audio fade, and when the last segment ended
  exactly where the voice did, that fade swallowed the final word. The last
  segment now keeps enough of the original silence for the fade to land on
  nothing.

### Added
- `subtitles.py` takes `--fontsize` and `--margin-v` to override the preset for
  one render. Both exist for screen recordings, where the default position lands
  on top of the interface being demonstrated and neither text can be read.
  Lowering the size rescales the outline with it, so small captions do not end
  up with a border wider than the letters.

---

## 1.11.0 — 2026-08-21

### Added
- Cutaways fade in and out instead of cutting hard, and the guidance now says to
  land them in the real pauses between phrases — the gaps over a quarter of a
  second in `words.json`. A cutaway that arrives mid-syllable is noticed even
  when it is the right shot; the same shot arriving in the breath between two
  sentences is not.
- **`--no-polish`**: no denoise, no sharpening. Together with `--no-grade` it
  leaves the recorded pixel untouched — the chain collapses to
  `[prepolish]null[polished]` and the only things acting on the image are the
  crop, the framing of the effects, and whatever is composited on top.

### Notes
- Without polish the cutaways are not sharpened either, so a clip of lower
  resolution than the output arrives softer. That is the cost of touching
  nothing.
- Matching a cutaway's colour is still needed when filters are off: it is not a
  look applied to the recording, it is what makes footage from another camera
  belong to the same video. The reference is darker without a grade, so the
  numbers have to be measured again rather than reused.

---

## 1.10.0 — 2026-08-21

### Added
- **Cutaways.** Video clips of your own now cut in over the picture at full
  screen while the original audio carries on underneath — which is what makes
  them read as a second camera rather than an interruption. They land after the
  colour grade, so each clip keeps its own look, and before the captions, so the
  words keep running over them.
- Each cutaway takes a `grade` of its own for matching. Footage from another
  camera rarely lands on the same brightness: measured on a real set of three,
  the speaker sat at 58 brightness and 14 saturation while the clips came in at
  47/10, 86/19 and 93/34. Unmatched, all three read as a different video.
- The asset library catalogues video files under `clips`, with duration and
  size, so the agent knows they are there.

### Notes
- Two cutaways at once, one landing on a `pullback`, or one asking for more
  footage than the file holds are all refused with the timings rather than
  rendered as something wrong.

---

## 1.9.3 — 2026-08-19

### Fixed
- A pull-back below `scale` 0.75 was quietly clipped instead of refused. The
  black band it opens is shifted upward, and that shift has to fit inside the
  padding — with the current padding the real floor is 0.742, not the 0.70 the
  guard allowed. Measured at 0.72, the top band came out 346 px wide where the
  geometry called for 387. The guard now sits at 0.75.
- The test for it compares the constant against the derivation rather than
  against a number typed in by hand, which is how the wrong floor got in.

---

## 1.9.2 — 2026-08-19

### Documentation
- The technical reference had fallen behind the last four releases. It now
  documents `cut_in`, `dip`, `pullback` and the `title` card, the padding trick
  that lets zoompan pull back below 1:1 and why the factor has to be exactly
  1.5, the easing and the velocity-step measurement behind it, and the Remotion
  card renderer.
- Card placement guidance corrected there too: measure the face across the whole
  card window rather than eyeballing a frame, which puts cards at 0.66-0.68 on a
  vertical mid-shot rather than the 0.56 the old text suggested.
- Both READMEs now describe what shot changes and transitions actually look
  like. They are things a viewer sees, so leaving them out of the user-facing
  docs made the edit sound plainer than it is.

---

## 1.9.1 — 2026-08-19

### Changed
- Shot changes now read as a move rather than a push. What makes a zoom feel
  abrupt is not how long it takes but the **velocity step between two frames**:
  the previous easing went from standing still to full speed in a single frame.
  Every joint in the curve — in, creep, out — now leaves and arrives at zero
  velocity and zero acceleration. Measured across the whole move, the largest
  frame-to-frame velocity step fell from 7.78 to 0.24.
- The travel is close to a second instead of a third of one. A shot change that
  quick reads as a badly made jump however smooth the curve; when you want the
  jump, `cut_in` is the well made one.
- The pull-back's envelope got the same easing, so it leaves and returns without
  a trace of a start.

---

## 1.9.0 — 2026-08-19

### Added
- **`pullback`**: the video shrinks onto black, a headline animates into the
  space that opens above it, and it eases back to full size. This is now the way
  to change subject. A fade to black only covers the join; a pullback uses it —
  it puts the phrase you just said on screen, so it can be used three or four
  times in a video without tiring.
- **`title` card**: large text with no panel behind it, for that black band. A
  dark panel on black reads as a box floating in nothing. It sits above the
  shrunk video, so the captions carry on underneath undisturbed.

### Changed
- The dip-to-black and whip-pan transitions are still there for a hard beat, but
  they are no longer the default for a change of subject.

### Notes
- zoompan cannot pull back below 1:1, so the frame is padded first and the shot
  is composed inside it. The padding is an exact 1.5×, which means that at rest
  the crop lands 1:1 — measured, sharpness is identical with and without the
  effect (Laplacian variance 116.05 either way), and render time is unchanged.

---

## 1.8.1 — 2026-08-19

### Fixed
- Transitions were draining the colour out of the picture. A dip moved the
  brightness without touching the colour, so instead of going black the frame
  filled with dark coloured murk — measured, luma fell from 59 to 2 while
  saturation sat unmoved at 13.1. The colour now collapses in step with the
  brightness, as a real fade does.
- The whip pan blurred the colour planes as well as the picture, averaging
  neighbouring colours toward grey. It now smears the luma only, horizontally —
  a whip is a sideways move, and a round blur reads as out of focus rather than
  as speed — and only across the fast middle of the sweep, so the frames where
  the shot has barely moved stay sharp.

---

## 1.8.0 — 2026-08-19

### Added
- **`cut_in`**: a real cut to a tighter framing, with no ramp at all. A push
  that takes even a third of a second still reads as a zoom; landing on the new
  framing between one frame and the next reads as cutting to a second camera.
- **`dip`**: a quick dip to black. Put a `dip` and a `cut_in` at the same instant
  and the framing changes while the screen is dark, so the jump is never seen —
  that is a cut, rather than an effect laid over the video.

### Changed
- Shot changes no longer feel flat. The way in is an ease-out cubic instead of a
  symmetric cosine, the hold creeps a little further instead of freezing, and the
  way out is 1.6× longer than the way in — you land on a framing fast and leave
  it slowly, which is how it is cut.
- Guidance on **where** effects go: on the first word of a phrase that carries
  weight, never spaced by the clock. Spacing them evenly is exactly what reads as
  random and abrupt. And a transition belongs where the subject changes, not
  merely where the silence detector removed a pause.
- Cards are placed by measuring the face across the whole card window rather
  than eyeballing one frame. On a vertical mid-shot that puts them at 0.66-0.68,
  not 0.56 — at 0.56 the card eats the speaker's beard.

---

## 1.7.0 — 2026-08-19

### Added
- **Animated cards, drawn with Remotion.** The bullets arrive one at a time, the
  rule under a heading draws itself, the flow card's spine grows top-down, and a
  stat card counts up to its figure — none of which a still image can do.
  Same `plan.json`, same preset colours: the React components read the card spec
  directly, so there is nothing to keep in sync between Python and TypeScript.
- Ask for them with `--animated`; an edit that already exists can be upgraded by
  re-running the card step alone, without re-planning anything.

### Changed
- Remotion is optional. It pulls in Node and its own headless Chrome, so the
  setup installs it only when Node is already on the machine, and says so when
  it is not. Without it, everything works exactly as before with still cards.

---

## 1.6.2 — 2026-08-15

### Fixed
- A recording that starts with silence — which is every recording, since you hit
  record and *then* start talking — produced a fraction of a second of dead video
  at the head of the edit.
- The colour grade was crushing dimly lit footage. The guidance said to write a
  custom grade below an average brightness of 45; measured on real material, the
  vignette alone costs 24% and the threshold had to be 60. Low-key setups were
  coming out with the face sunk in the shadows.
- `subtitles.py` reported every card as hiding the captions, when chips do not.

---

## 1.6.1 — 2026-08-15

### Fixed
- A logo saved as `Youtube_logo.png` never triggered, because the word searched
  for was «youtube logo» and nobody says that out loud. Generic words (`logo`,
  `icon`, `imagen`…) are now dropped from the trigger.
- Logos are PNGs with transparency, so they are catalogued as stickers — and the
  keyword feature was only looking at images, missing exactly the files it is
  most useful for.

---

## 1.6.0 — 2026-08-15

### Added
- The asset library now **reindexes itself before every edit**. Drop an image
  into your folder and it is available in the next video, with nothing to run.

### Changed
- `/fragua:assets` is no longer needed for routine use — it stays as the way to
  point at a different folder or to review the inventory.
- A missing or unconfigured asset folder no longer stops an edit: assets are
  optional, so Fragua warns and carries on.

---

## 1.5.0 — 2026-08-15

### Added
- **Images that appear when you mention something.** An image named
  `youtube.png` or `claude-code.png` in your assets folder pops into a corner
  whenever the video says that word. The filename is the trigger — nothing to
  configure. It never covers your face, never fills the screen, and its entry
  sound ducks under your voice.
- **Memory of the advice it gives you.** After each edit Fragua records which
  content recommendations you applied and which you did not, and reads that
  history before giving its next opinion. Ask `how am I improving?` for the
  report.

---

## 1.4.0 — 2026-08-13

### Changed
- The **title and the 15 tags are no longer optional**. Every edit ends with the
  full publishing kit, even when you only ask for the descriptions.

---

## 1.3.1 — 2026-08-13

### Fixed
- The asset library was stored inside the plugin folder, so a plugin update wiped
  it. It now lives in `~/.fragua/assets.json` and survives updates.

---

## 1.3.0 — 2026-08-13

### Added
- Slash commands `/fragua:setup` and `/fragua:assets`, so nobody has to run
  Python by hand.

---

## 1.2.0 — 2026-08-13

### Added
- **Your own asset library**: music, sound effects, stickers, images and fonts
  from a folder you own, classified by reading the files rather than the folder
  names.
- Sound effects sit under the narration automatically, ducked against the voice
  instead of merely turned down.

### Fixed
- Python was not detected on Windows, because the 0-byte Store aliases answer as
  if an interpreter were installed. Detection now runs the interpreter and reads
  what it says.

---

## 1.1.0 — 2026-08-13

### Added
- Installable as a **plugin** in Claude Code and through an installer script in
  OpenCode, instead of copying folders by hand.
- The setup resolves its own prerequisites — ffmpeg, Python, whisper.cpp, the
  transcription model and the fonts — through `winget`, `brew` or the system
  package manager.
- English README, with the Spanish one alongside it.

---

## 1.0.0 — 2026-08-13

First release. A raw recording in, a video ready to publish out:

- Silences detected and trimmed
- Karaoke captions burnt in, transcribed **after** the cut so they stay in sync
- Rasterised graphic cards in five styles: panel, bullets, flow, stat and chip
- Sustained shot changes, cinematic grade, denoise and masked sharpening
- Loudness-normalised audio
- Presets for TikTok, Reels, Shorts and YouTube
- Publishing copy: title, description, 15 tags and captions per network
- Everything local — no API keys, no uploads

---

Versions 1.0.0 through 1.5.0 are reconstructed from the commit history: the
manifest carried `1.0.0` until 1.6.0, so they were never published as separate
releases. Each one is tagged at its commit, so the diffs are real.
