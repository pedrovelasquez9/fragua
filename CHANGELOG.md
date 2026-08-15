# Changelog

Every released version of Fragua, newest first. Dates are the day the change
landed.

To see which version you have installed, ask the agent `what version of fragua
is this?`, or read `version` in `.claude-plugin/plugin.json`.

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
