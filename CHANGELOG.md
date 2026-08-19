# Changelog

Every released version of Fragua, newest first. Dates are the day the change
landed.

To see which version you have installed, ask the agent `what version of fragua
is this?`, or read `version` in `.claude-plugin/plugin.json`.

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
