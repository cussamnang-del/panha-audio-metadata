# Training Manual — Panha Audio Meta Data

> **Chapter 1 — Overview**

---

## 1.1 What is this project?

**Panha Audio Meta Data** is a cross-platform **PyQt6 + ffmpeg** desktop
application for **batch editing audio metadata** (ID3v2 tags) and optionally
running a 13-slider mastering chain over the same files. The UI is modelled on
the **X-MIXM** reference design (dark blue/cyan theme, batch queue, File
Information dialog, animated waveform footer).

What end users get out of it:

- Drop a folder of MP3 / WAV / FLAC / M4A / OGG / AAC files into a **Batch
  Queue**, then write **Artist / Album / Year / Genre / Cover art / Comment /
  Engineer / Copyright / Software / Source / Comment** to every file in one
  click.
- **Zero-loss tagging by default** — when the mastering chain is off, ffmpeg
  is invoked with `-c:a copy`, so audio bytes are not re-encoded and quality
  is preserved bit-for-bit.
- Adjust 13 mastering sliders (EQ / Compressor / Limiter / Saturator /
  Reverb / Echo / Width / Gain) — turning any slider up automatically switches
  ffmpeg into **re-encode** mode using the appropriate codec for the output
  format (`libmp3lame -q:a 2` for `.mp3`, `aac -b:a 192k` for `.m4a`,
  `flac` for `.flac`, etc.).
- **Preview** the currently-selected queue row in-app with Prev / Play /
  Next / **BYPASS** / scrubber controls backed by `QMediaPlayer`.
- Save the entire console state (metadata + tracklist options + mastering
  sliders) as a named **Template** stored in `~/.panha_templates.json`, then
  reload it from the Setting Console template combo.
- **Export Settings** dialog to override output format, sample rate, bit
  depth, thread count and an optional LUFS loudness target (powered by
  ffmpeg `loudnorm`).
- **AI Music Detector** dialog (UI scaffolding only — backend analyser is not
  implemented yet; rows surface `—` placeholders).
- **CPU / RAM** indicator in the status bar (1 Hz, powered by `psutil`).

> **About this manual**: It targets **end users / operators** who want to use
> the app to retag a catalogue of audio files. Internals chapters (6–8) are
> useful for developers and integrators, but the day-to-day operator only
> needs Chapters 1–5.

## 1.2 Technology Stack

| Layer | Technology |
|---|---|
| Language | **Python 3.10+** (3.10 / 3.11 / 3.12 tested in CI) |
| GUI framework | **PyQt6 ≥ 6.6** (Widgets + Multimedia) |
| Audio backend | **ffmpeg** + **ffprobe** invoked via `subprocess` |
| System stats | **psutil ≥ 5.9** |
| Packaging | **setuptools** (PEP 621 `pyproject.toml`) |
| Lint | **ruff ≥ 0.5** (`select = ["E","F","I","B","UP","N"]`, line-length 110) |
| Tests | **pytest ≥ 7** + **pytest-qt ≥ 4.4** |
| CI | GitHub Actions on `ubuntu-latest` × Python 3.10 / 3.11 / 3.12 |
| Templates store | Plain JSON at `~/.panha_templates.json` |

> **Important**: there is **no native audio DSP** in this app. Every effect
> (EQ, comp, limit, sat, reverb, echo, width, gain, loudnorm) is implemented
> as an **ffmpeg `-af` filter chain**. The mapping from sliders → ffmpeg
> filters lives in [`panha/mastering.py`](panha/mastering.py); see
> Chapter 6 for the full table.

## 1.3 Project Structure

```
panha-audio-metadata/
├── panha/                              # Main Python package
│   ├── __init__.py                     # __version__ / __app_name__
│   ├── __main__.py                     # `python -m panha` entrypoint
│   ├── app.py                          # QApplication bootstrap
│   ├── main_window.py                  # The X-MIXM main window
│   ├── mastering.py                    # Sliders → ffmpeg `-af` chain
│   ├── templates.py                    # JSON template store
│   ├── dialogs/
│   │   ├── ai_detector_dialog.py       # AI Music Detector (UI only)
│   │   ├── config_dialog.py            # Batch actions launcher
│   │   ├── export_settings_dialog.py   # Format / SR / bit-depth / LUFS / threads
│   │   └── file_info_dialog.py         # Metadata editor + tracklist options
│   ├── metadata/
│   │   ├── __init__.py                 # Public surface for write/read/probe
│   │   └── ffmpeg_writer.py            # Stream-copy and re-encode writer
│   ├── ui/styles.py                    # Dark Qt stylesheet
│   └── widgets/
│       ├── mastering.py                # MasteringPanel (13 sliders + badges)
│       ├── system_stats.py             # CPU / RAM status bar widget
│       ├── transport.py                # Prev / Play / Next / BYPASS / scrubber
│       ├── waveform.py                 # Decorative animated waveform footer
│       └── worker.py                   # BatchWorker + BatchItem + probe pool
├── tests/                              # pytest + pytest-qt suite
├── docs/                               # Screenshots + test plan
├── .github/workflows/ci.yml            # Lint + test matrix
├── pyproject.toml                      # PEP 621 project metadata
└── requirements.txt                    # Runtime deps only (mirror of project)
```

---

> **Chapter 2 — Installation & Setup**

---

## 2.1 System Requirements

- **Python** **3.10** or higher.
- **ffmpeg** **and** **ffprobe** on `PATH`, **or** the environment variables
  `PANHA_FFMPEG` / `PANHA_FFPROBE` pointing at the binaries.
- **Qt 6 runtime libraries** (`libegl1`, `libxcb-*`, `libxkbcommon-*`, ...
  on Linux — see the CI workflow for the exact list).
- A working audio output (only required if you want to use the in-app
  Play / Pause preview).
- ~120 MB disk space for the virtualenv (PyQt6 wheel is the bulk).

## 2.2 Installing ffmpeg

```bash
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg
```

Verify ffmpeg is reachable from the same shell you will launch the app from:

```bash
ffmpeg -version
ffprobe -version
```

If you cannot install ffmpeg system-wide (e.g. portable USB build), point
the app at it explicitly:

```bash
export PANHA_FFMPEG=/path/to/ffmpeg
export PANHA_FFPROBE=/path/to/ffprobe
```

## 2.3 Step-by-Step Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/samnangoudampanha-star/panha-audio-metadata.git
cd panha-audio-metadata
```

### Step 2 — Create and activate a virtualenv

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
```

### Step 3 — Install the package (editable, with dev extras)

```bash
pip install --upgrade pip
pip install -e .[dev]
```

This installs:

- Runtime: **PyQt6**, **PyQt6-Qt6**, **psutil**.
- Dev extras: **pytest**, **pytest-qt**, **ruff**.

### Step 4 — Verify the install

```bash
ruff check panha tests
QT_QPA_PLATFORM=offscreen pytest -v
```

> On a CI / headless machine you **must** set `QT_QPA_PLATFORM=offscreen`
> (or `QT_QPA_PLATFORM_PLUGIN_PATH`) for the test suite to run without a
> live display.

## 2.4 Running the App

Two equivalent entry points:

```bash
# 1. As a module — useful while developing
python -m panha

# 2. As the installed console script
panha
```

Both invoke `panha.app.main()`, which boots a `QApplication`, applies the
dark stylesheet from `panha/ui/styles.py`, then shows the `MainWindow`.

The app does not need any network access and does not write anywhere
outside:

- `~/.panha_templates.json` — saved console templates.
- `~/PanhaExports/` — default output folder when you have not picked one
  yet (the **Output Folder** picker in the Config dialog overrides this).
- Whatever destination folder the export run is pointed at.

---

> **Chapter 3 — The Main Window**

---

## 3.1 Layout at a Glance

The window is divided into five horizontal bands, top to bottom:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ♫  Panha Audio Meta Data                                            │  Header
├─────────────────────────────────────────────────────────────────────┤
│  Batch Queue                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Filename             │ Duration │ Type │ Status              │   │
│  │ 01_track_one.mp3     │ 3:42     │ MP3  │ Pending             │   │  Queue
│  │ 02_track_two.flac    │ 4:10     │ FLAC │ Done   (green)      │   │
│  │ 03_track_three.wav   │ 2:55     │ WAV  │ Error: ...  (red)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  [████████░░░░░░░░░░░░░░░░░░░] 28%                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Setting Console                                                    │
│  Template: [ Default        ▾] [Save As][Update][Remove][Reset all] │
│                                              [Config][✎ Analyze AI] │  Console
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ EQ VOC EQ VOC EQ EQ │ DYN DYN DYN │ FX FX │ OUT OUT          │   │
│  │ Bass Deep Mid Clear │ Comp Limit  │ Verb  │ Width  Gain      │   │
│  │  Treble Pres        │   Sat       │ Echo  │                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│  ~~~~~ animated waveform footer (only spins during export) ~~~~~~   │  Waveform
├─────────────────────────────────────────────────────────────────────┤
│  ⏮  ▶  ⏭   [BYPASS]   0:00  ──────────────────────  3:42            │  Transport
├─────────────────────────────────────────────────────────────────────┤
│  Status: Active                  © 2026 Panha • v0.1.0    CPU: 4%   │
│                                                           RAM: 23%  │  Status
└─────────────────────────────────────────────────────────────────────┘
```

Operational actions (Add Files / Add Folder / Output Folder / File
Information / Export Settings / Start / Stop) live **behind the Config
button** in the Setting Console and the queue's right-click context menu
— this keeps the main surface focused on mixing.

## 3.2 The Batch Queue

| Column | Source |
|---|---|
| Filename | `os.path.basename(path)` |
| Duration | `ffprobe -show_entries format=duration` (computed on a background `QThreadPool`, so adding a 500-file folder never freezes the UI) |
| Type | Uppercase file suffix (`MP3`, `WAV`, `FLAC`, ...) |
| Status | `Pending` → `Processing` (cyan) → `Done` (green) **or** `Error: ...` (red) **or** `Cancelled` |

Notes:

- Supported extensions: `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`, `.aac`.
  Other files dropped onto the queue are silently skipped.
- Duplicate paths are automatically de-duplicated when added.
- The queue uses extended row selection — Shift / Ctrl-click work as
  expected and the right-click menu's **Remove selected** acts on the
  current selection.
- The currently-selected row is what the **Transport** bar loads for
  preview (so clicking a row immediately makes Play / scrubber preview
  that file).

### Queue right-click menu

| Action | Behaviour |
|---|---|
| Select all | Selects every row in the queue. |
| Add files | Opens a file picker (multi-select). |
| Add folder | Opens a folder picker; recursively adds every supported file. |
| Remove selected | Removes the selected rows. |
| Clear all | Empties the queue and resets the progress bar. |
| ▶  START EXPORT | Same as the Config dialog's **Start Export** button. |
| ■  STOP EXPORT | Cancels the in-flight worker (current ffmpeg child is terminated cooperatively). |
| Open output folder | Opens the current output folder in the system file manager (Explorer / Finder / `xdg-open`). |

## 3.3 The Setting Console

The Setting Console is the heart of the app and has two rows.

### Row 1 — Template controls

| Button | Behaviour |
|---|---|
| **Template:** combo | Shows `Default` plus every saved template name. Selecting a saved template **loads** the whole state (metadata + tracklist + mastering sliders) into the UI. |
| **Save As** | Prompts for a name and persists the current state to `~/.panha_templates.json`. The combo is refreshed and the new name becomes the current selection. |
| **Update** | Overwrites the currently-selected template with the current state. Disabled when no saved template is selected. |
| **Remove** | Deletes the currently-selected template (with confirmation). Disabled when no saved template is selected. |
| **Reset all** | Resets metadata, tracklist options, and all 13 mastering sliders back to zero, and clears the template selection. |
| **Config** | Opens the **Config** action launcher (non-modal). See §3.4. |
| **✎ Analyze AI** | Opens the **AI Music Detector** dialog seeded with the current queue's files. See §4.3. |

> Templates are stored as a single JSON object keyed by name in
> `~/.panha_templates.json`. The file is plain text — feel free to back it
> up, copy it between machines, or hand-edit it.

### Row 2 — The 13-Slider Mastering Grid

13 vertical sliders, each labelled with a badge above (EQ / VOCAL / DYN /
FX / OUT) and the slider's name below. Range is `0..99`; the readout above
the slider mirrors the current value in real time.

| # | Badge | Name | Effect |
|---|---|---|---|
| 1 | EQ | Bass | Peaking EQ @ 80 Hz, 0..+12 dB |
| 2 | VOCAL | Deep | Peaking EQ @ 180 Hz, 0..+12 dB |
| 3 | EQ | Mid | Peaking EQ @ 500 Hz, 0..+12 dB |
| 4 | VOCAL | Clear | Peaking EQ @ 1.5 kHz, 0..+12 dB |
| 5 | EQ | Treble | Peaking EQ @ 5 kHz, 0..+12 dB |
| 6 | EQ | Pres | Peaking EQ @ 10 kHz, 0..+12 dB |
| 7 | DYN | Comp | Compressor (`acompressor`), ratio 1..8, threshold -10..-30 dB |
| 8 | DYN | Limit | Brick-wall limiter (`alimiter`), ceiling 1.0..0.5 |
| 9 | DYN | Sat | Saturator / exciter (`aexciter`), amount + drive |
| 10 | FX | Verb | Multi-tap reverb (`aecho`, 4 taps) |
| 11 | FX | Echo | Single-tap echo (`aecho 500 ms`) |
| 12 | OUT | Width | Stereo width (`extrastereo m=1..2.5`) |
| 13 | OUT | Gain | Output gain 0..+12 dB (`volume`) |

See Chapter 6 for the exact ffmpeg expressions.

## 3.4 The Config Dialog (Batch Actions)

Opened by the Setting Console's **Config** button (or by right-clicking the
Batch Queue). It is **non-modal** so you can keep it open while you click
back into the main window — handy when you want to Add Files → File
Information → Start Export without re-opening it three times.

Layout:

```
┌──────────── Batch Actions ────────────┐
│ [ Add Files     ] [ Add Folder      ] │
│ [ Output Folder ] [ File Information ] │
│ [ Export Settings ]                   │
│ [ Start Export  ] [ Stop Export     ] │
│                              [Close]  │
└───────────────────────────────────────┘
```

| Button | Behaviour |
|---|---|
| Add Files | Multi-select file picker; only files with supported extensions are added. |
| Add Folder | Folder picker; recursively walks the folder and adds every supported file. |
| Output Folder | Folder picker for the export destination. Stored on `MainWindow._output_dir` and pushed into `ExportSettings.output_dir`. Defaults to `~/PanhaExports`. |
| File Information | Opens the metadata editor — see §4.1. |
| Export Settings | Opens the format / SR / bit-depth / LUFS / threads dialog — see §4.2. |
| **Start Export** | Builds `BatchItem`s and starts the worker thread. Disabled while a run is in progress. |
| **Stop Export** | Cancels the worker — the currently-running ffmpeg child is `terminate()`d cooperatively. Disabled while idle. |

## 3.5 The Transport Bar (Preview)

A compact playback bar backed by `QMediaPlayer` so you can audition the
currently-selected queue row **before** committing to a batch export.

| Control | Behaviour |
|---|---|
| ⏮ Prev | Selects the previous queue row (does not auto-play). |
| ▶ / ⏸ Play | Plays / pauses the currently-loaded source. Icon flips when the player state changes. |
| ⏭ Next | Selects the next queue row. |
| **BYPASS** | Toggle. When pressed, the mastering chain is disabled for the export run **and** the slider panel is dimmed. Mirrors `MasteringSettings.bypass`. |
| Position label | Current playback position (`m:ss`). |
| Scrubber | Draggable position. Press to start seeking, release to commit. |
| Duration label | Total source duration (`m:ss`). |

> Preview always plays the **original** source — it does **not** apply the
> mastering chain in real time. To hear the mastering chain, run an export
> to a scratch folder and play the result.

## 3.6 The Waveform Footer

Purely decorative animated sine-wave. It starts spinning when an export
run begins and stops when the worker finishes. It does **not** show any
real audio analysis of the queued files.

## 3.7 The Status Bar

| Slot | What it shows |
|---|---|
| Left | `Status: Active` (constant — there's no idle/error state). |
| Center (permanent) | `© <year> Panha • v<__version__>`. |
| Right (permanent) | `CPU: NN%` and `RAM: NN%` updated every 1 s by `psutil`. |

The CPU/RAM widget polls `psutil` via a single `QTimer` so it stays cheap
even when many windows / dialogs are open.

---

> **Chapter 4 — Dialogs in Detail**

---

## 4.1 The File Information Dialog

Opened from **Config → File Information**. This is where the **metadata
that will be injected** into every queued file is configured.

```
┌────────────────── File Information ──────────────────┐
│  [✓] Enable Info Injection                            │
│  ┌─ Templates ──────────────────────────────────────┐ │
│  │ Preset:  [ Lo-fi Master  ▾]   [Save As] [Delete] │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌─ Basic Info ─────────────────────────────────────┐ │
│  │ Artist  [..........]   Year   [....]             │ │
│  │ Album   [..........]   Rating [None ▾]           │ │
│  │ Genre   [Lo-fi  ▾]     Cover  [path...] [...][Folder]
│  └──────────────────────────────────────────────────┘ │
│  ┌─ Studio Metadata ────────────────────────────────┐ │
│  │ Engineer [...]    Copyright [...]                │ │
│  │ Software [...]    Source    [...]                │ │
│  │ Comment  [................................]     │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌─ Tracklist ──────────────────────────────────────┐ │
│  │ [ ] UPPERCASE   [✓] Remove Track Number          │ │
│  │ Cover Size: [1600] x [1600]                      │ │
│  └──────────────────────────────────────────────────┘ │
│                                  [Cancel] [Apply...] │
└──────────────────────────────────────────────────────┘
```

### 4.1.1 Fields

| Field | Maps to ffmpeg `-metadata` key | Notes |
|---|---|---|
| Artist | `artist` | |
| Album | `album` | |
| Year | `date` | Free text — `"2026"` or `"2026-05"` both work. |
| Rating | `rating` | Combo: `None / 1 / 2 / 3 / 4 / 5`. `None` writes nothing. |
| Genre | `genre` | Editable combo seeded with common genres (Pop, Rock, Hip-Hop, Khmer, Lo-fi, ...). |
| Cover | `attached_pic` JPEG/PNG stream | See §4.1.2. |
| Engineer | `engineer` | |
| Copyright | `copyright` | |
| Software | `encoder` **and** `encoded_by` | Same value written twice so both ffprobe-visible keys are populated. |
| Source | `source` | |
| Comment | `comment` | |

The per-track **Title** falls back to the source file's **stem** when no
explicit title is provided on the metadata template, after applying the
Tracklist options below. (The Title field itself is not surfaced in the
dialog — it lives on the underlying `FileInformationState` and is
populated automatically by `build_items()`.)

### 4.1.2 Cover Art

Two ways to specify a cover:

1. **`...`** button — pick a single image file (`.png`, `.jpg`, `.jpeg`,
   `.webp`).
2. **Folder** button — pick a folder; the first image in that folder
   (alphabetical) is used. Useful when each album lives in its own
   directory and you don't want to manually pick the cover every time.

The Tracklist row's **Cover Size W × H** controls let you keep the cover
image's intended pixel dimensions (used as metadata only; ffmpeg embeds
the image at its native resolution).

### 4.1.3 Tracklist Options

| Option | Effect |
|---|---|
| UPPERCASE | After computing the track title from the filename stem, uppercase it. |
| Remove Track Number | Strip a leading `01.`, `02 -`, `03_` etc. from the filename stem before using it as the title. |

### 4.1.4 Templates within this dialog

The Templates row at the top is a **shortcut** that talks to the same
`~/.panha_templates.json` store as the Setting Console template combo —
saving a template here makes it available in the Setting Console combo
and vice versa.

### 4.1.5 Enable Info Injection

If this checkbox is unchecked, **no `-metadata` flags are passed to
ffmpeg** when the export runs. You can still re-encode and re-format
files (Export Settings, mastering chain) — only the metadata write is
skipped. Starting an export with Info Injection disabled prompts a
confirmation dialog ("Continue without writing metadata?").

## 4.2 The Export Settings Dialog

Opened from **Config → Export Settings**.

```
┌────────────── Export Settings ──────────────┐
│  Format       [ Same as source ▾]            │
│  Sample Rate  [ Same as source ▾]            │
│  Bit Depth    [ 24-bit          ▾]           │
│  Max Threads  [ 4               ↕]           │
│  ─── Processing Options ────────────────     │
│   [ ] SUNO Bypass                            │
│   [ ] Vocal Clarity Boost                    │
│   [ ] Soft Clip Ceiling                      │
│  ─── Mastering Target ──────────────────     │
│   LUFS Target  [ Off  ▾]                     │
│   [▶  Start Export]                          │
│   [Cancel]                                   │
└──────────────────────────────────────────────┘
```

| Setting | Values | Effect |
|---|---|---|
| Format | `Same as source` / `MP3` / `WAV` / `FLAC` / `M4A` / `OGG` | Output extension. Different from source ⇒ re-encode. |
| Sample Rate | `Same as source` / `22050 Hz` / `44100 Hz` / `48000 Hz` / `96000 Hz` | Different from source ⇒ re-encode (`-ar <hz>`). |
| Bit Depth | `16-bit` / `24-bit` / `32-bit` | **Only consulted for WAV output**, where it picks the `pcm_s*le` codec. Ignored for every other format. |
| Max Threads | `1..32` | Number of parallel ffmpeg subprocesses the batch worker is allowed to run. |
| SUNO Bypass / Vocal Clarity Boost / Soft Clip Ceiling | checkboxes | Reserved processing flags; persisted on `ExportSettings` but **not currently wired to the writer** (placeholder UI for upcoming features). |
| LUFS Target | `Off` / `-23` / `-16` / `-14` / `-9` LUFS | When non-`Off`, the writer prepends `loudnorm=I=<n>:TP=-1.5:LRA=11` to the filter chain. Forces re-encode. The TP/LRA values mirror EBU R128 broadcast defaults. |

### 4.2.1 When does Export Settings force a re-encode?

The batch builder (`build_items` in `panha/widgets/worker.py`) flags
re-encode when **any** of the following holds:

- Output format differs from the source format.
- Sample rate is not `Same as source`.
- LUFS target is not `Off`.
- A codec override is supplied (currently only WAV bit-depth selection).
- Any mastering slider is non-zero **and** BYPASS is off.

Otherwise, ffmpeg runs with `-c:a copy` and audio is **not** re-encoded.

## 4.3 The AI Music Detector Dialog

Opened from the Setting Console's **✎ Analyze AI** button. It is
**non-modal** and supports **drag-and-drop** onto the table.

```
┌── AI Music Detector ───────────────────────────┐
│ AI Music Detector                              │
│ Drop audio files — analyzes AI automatically   │
│                                                │
│ [Add Files]  [Clear]                           │
│ ┌────────────────────────────────────────────┐ │
│ │ Filename       │ Platform │ Confidence │..│ │
│ │ track_01.mp3   │    —     │    —       │..│ │
│ │ ...            │    —     │    —       │..│ │
│ └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────┘
```

> **State of the feature**: the dialog scaffolding (table, drag-drop, file
> picker, public `set_row_result()` API) is in place, but **no detection
> backend is wired up yet**. Rows surface `—` placeholders and an
> *"AI detection is not implemented yet."* tooltip on the analysis
> columns. A future PR can drop in a real analyser without restructuring
> the UI.

When you open the dialog from the main window, it is seeded with the
current Batch Queue files so you do not have to re-pick them.

---

> **Chapter 5 — Daily Workflows**

---

## 5.1 Workflow A — Zero-Loss Tagging (the common case)

**Goal**: rewrite ID3v2 tags + embed cover art on a batch of MP3s without
touching the audio bytes.

1. Launch the app: `python -m panha`.
2. Click **Config** → **Add Folder** → pick the album folder.
   - The queue populates. Duration probes happen in the background.
3. Click **Config** → **File Information**:
   - Tick **Enable Info Injection**.
   - Fill in Artist / Album / Year / Genre / Cover (`...` button) /
     Engineer / Copyright / Software / Source / Comment.
   - Tick **Remove Track Number** so `01_track.mp3` becomes title `track`.
   - Click **Apply setting**.
4. (Optional) Click **Save As** on the Setting Console template row →
   give it a memorable name (e.g. `Album X 2026`). It is now reusable.
5. Click **Config** → **Output Folder** → pick a clean folder.
6. **Leave all mastering sliders at 0** and **leave BYPASS off**. The
   writer will use `-c:a copy`.
7. Click **Config** → **Start Export**.
   - Progress bar climbs 0 → 100 %.
   - Each row turns green (`Done`) when its ffmpeg child exits.
8. Verify a sample output with `ffprobe`:

   ```bash
   ffprobe -v error -show_format -show_streams -of json out/track_01.mp3
   ```

   You should see `format.tags.artist`, `format.tags.album`, ...
   matching exactly what you typed, plus an `mjpeg` video stream with
   `disposition.attached_pic == 1`.

## 5.2 Workflow B — Mastering + Tagging (re-encode)

**Goal**: apply gentle EQ + a compressor + a final loudness target to a
podcast batch, and tag the result.

1. Add the files (Config → Add Files / Add Folder).
2. **File Information** → fill in metadata as in Workflow A.
3. **Setting Console mastering grid**:
   - Push **Comp** to ~25 (gentle compression).
   - Push **Pres** to ~10 (a touch of presence).
   - Push **Gain** to ~6 (catch up loudness).
4. **Export Settings** → **LUFS Target** = `-16 LUFS`.
   - Re-encode is now forced (LUFS target + mastering chain).
5. **Output Folder** → pick a folder.
6. **Start Export**.
7. Verify with `ffprobe` (as in 5.1) **and** with a loudness meter — the
   integrated LUFS of the output should land within ±1 LU of -16.

## 5.3 Workflow C — Format Conversion in Bulk

**Goal**: convert a folder of WAVs to 44.1 kHz / MP3, tagged.

1. Add the WAV folder.
2. **Export Settings**:
   - Format = `MP3`.
   - Sample Rate = `44100 Hz`.
   - Bit Depth — irrelevant for MP3, leave as is.
   - LUFS Target = `Off` (unless you want loudness normalisation too).
3. **File Information** → fill in tags.
4. **Output Folder** → pick a folder.
5. **Start Export**.
6. The writer picks `libmp3lame -q:a 2` automatically (see Chapter 7 for
   the per-suffix codec table).

## 5.4 Workflow D — Reusable Templates Across Sessions

1. Configure File Information + mastering sliders the way you want.
2. Click **Save As** on the Setting Console template row → e.g.
   `Khmer Lo-fi Master`.
3. Quit the app. Re-launch.
4. The template combo in the Setting Console now lists
   `Khmer Lo-fi Master`. Selecting it reapplies everything (metadata +
   tracklist options + 13 slider values + BYPASS flag).
5. To tweak the template, change the sliders, then click **Update**. To
   delete it, click **Remove**.

> Behind the scenes: the template is one entry in
> `~/.panha_templates.json`. The file is human-readable JSON — feel free
> to back it up or version it with your project.

## 5.5 Cancelling a Run

Click **Config → Stop Export** (or the queue's **■ STOP EXPORT** menu
item). The worker sets its cancel flag and the in-flight ffmpeg child is
`terminate()`d cooperatively. Each pending row goes to `Cancelled`.

> ffmpeg child processes are run with `subprocess.Popen` (not
> `subprocess.run`) specifically so cancellation can interrupt them
> mid-encode rather than only between files.

---

> **Chapter 6 — The Mastering Chain (Sliders → ffmpeg)**

---

The slider→filter mapping lives in
[`panha/mastering.py`](panha/mastering.py). Every slider value is mapped
linearly from `[0, 99]` to its target range via `_scale(value, lo, hi)`,
then formatted into one ffmpeg filter expression. Zero-valued sliders
contribute **nothing** to the chain (the writer does not even emit the
filter).

| Slider | Target range | ffmpeg expression |
|---|---|---|
| Bass | 0..+12 dB @ 80 Hz | `equalizer=f=80:width_type=q:w=1:g=<dB>` |
| Deep | 0..+12 dB @ 180 Hz | `equalizer=f=180:width_type=q:w=1:g=<dB>` |
| Mid | 0..+12 dB @ 500 Hz | `equalizer=f=500:width_type=q:w=1:g=<dB>` |
| Clear | 0..+12 dB @ 1.5 kHz | `equalizer=f=1500:width_type=q:w=1:g=<dB>` |
| Treble | 0..+12 dB @ 5 kHz | `equalizer=f=5000:width_type=q:w=1:g=<dB>` |
| Pres | 0..+12 dB @ 10 kHz | `equalizer=f=10000:width_type=q:w=1:g=<dB>` |
| Comp | ratio 1..8, threshold -10..-30 dB | `acompressor=threshold=<lin>:ratio=<r>:attack=20:release=250:makeup=2` |
| Limit | ceiling 1.0..0.5 | `alimiter=level_in=1:limit=<c>:attack=5:release=50` |
| Sat | amount 0..1, drive 1..8.5 | `aexciter=amount=<a>:drive=<d>:blend=0:freq=7500` |
| Verb | wet 0..1 | `aecho=<in>:<out>:60\|120\|180\|240:0.4\|0.3\|0.2\|0.1` |
| Echo | decay 0.2..0.7 @ 500 ms | `aecho=0.8:0.6:500:<decay>` |
| Width | m 1..2.5 | `extrastereo=m=<m>` |
| Gain | 0..+12 dB | `volume=<dB>dB` |

All active filters are joined with `,` and passed to ffmpeg as a single
`-af` argument. The order is **fixed** (EQ → DYN → FX → OUT) so the chain
is deterministic for a given set of slider values.

### 6.1 BYPASS flag

The transport bar's **BYPASS** button toggles
`MasteringSettings.bypass`. When `bypass=True`, `to_filter_chain()`
returns the empty string regardless of slider values — the writer falls
back to stream-copy (assuming no other re-encode trigger is active).

This is also the toggle the Setting Console honours when **Reset all**
is pressed: every slider goes back to 0 and BYPASS is cleared.

### 6.2 LUFS target (loudnorm)

Configured via **Export Settings → LUFS Target**. When set (anything
other than `Off`), the writer **prepends** `loudnorm=I=<lufs>:TP=-1.5:LRA=11`
to the filter chain — so the mastering chain runs **into** loudnorm.
Forces re-encode.

---

> **Chapter 7 — The ffmpeg Writer**

---

## 7.1 Public API

The writer is decoupled from the UI. Importable directly:

```python
from panha.mastering import MasteringSettings
from panha.metadata import Metadata, write_metadata

meta = Metadata(
    title="The Morning After",
    artist="Panha",
    album="Echoes",
    year="2026",
    genre="Lo-fi",
    cover_path="/path/to/cover.jpg",     # file or folder
    comment="Mastered with Panha",
)

# Tag-only (stream-copy, zero-loss)
write_metadata("input.mp3", "output.mp3", meta)

# With mastering — applies the filter chain and re-encodes
mastering = MasteringSettings(bass=30, comp=20, gain=10)
write_metadata("input.mp3", "mastered.mp3", meta, mastering=mastering)

# With LUFS target and explicit codec args
write_metadata(
    "input.wav", "output.wav", meta,
    lufs_target_lufs=-16.0,
    codec_args_override=["-c:a", "pcm_s24le"],
)
```

`write_metadata()` returns the absolute path of the written file. Errors
surface as one of:

| Exception | When |
|---|---|
| `FfmpegNotFoundError` | `ffmpeg` / `ffprobe` not on `PATH` and not pointed at by `PANHA_FFMPEG` / `PANHA_FFPROBE`. |
| `MetadataWriteError` | ffmpeg returned non-zero. |
| `MetadataWriteCancelledError` | `cancel_check()` returned True mid-export and the child was terminated. |
| `FileNotFoundError` | Source path does not exist. |
| `FileExistsError` | `overwrite=False` and the destination already exists. |

## 7.2 Stream-Copy vs Re-Encode

Stream-copy (`-c:a copy`) is used by default. The writer flips to
re-encode automatically when **any** of the following is true:

- A non-bypassed `MasteringSettings` is supplied.
- `lufs_target_lufs` is set.
- `codec_args_override` is provided (e.g. WAV bit-depth selection).
- `sample_rate_hz` is set.
- `force_re_encode=True`.

The per-suffix codec table when re-encoding (no explicit override):

| Output suffix | `-c:a` args |
|---|---|
| `.mp3` | `libmp3lame -q:a 2` |
| `.m4a` / `.aac` | `aac -b:a 192k` |
| `.ogg` | `libvorbis -q:a 5` |
| `.flac` | `flac` |
| `.wav` | `pcm_s16le` (or whatever bit-depth the user picked) |
| anything else | falls back to `libmp3lame -q:a 2` |

## 7.3 Cover Art Handling

The cover image is added as a second ffmpeg input and mapped as an
attached picture:

```
-i src.mp3 -i cover.jpg
-map 0:a -map 1
-c:v mjpeg -disposition:v attached_pic
-metadata:s:v title=Album cover
-metadata:s:v comment=Cover (front)
```

`resolve_cover_path()` handles both file and folder inputs — if the
metadata's `cover_path` points at a directory, the first image in that
directory (alphabetical, with one of `.png`, `.jpg`, `.jpeg`, `.webp`) is
used.

## 7.4 Atomic Writes

Every export goes through a sibling temporary file
(`.panha_<random>.<ext>`) in the destination directory, then `os.replace`
swaps it in place on success. If ffmpeg fails or is cancelled, the temp
file is unlinked and the destination is untouched — there is no
half-written output left behind.

## 7.5 ID3v2 Version

The writer always sets `-id3v2_version 3`. Practical reason: ID3v2.3 is
the most broadly-compatible variant (Windows Explorer, older car
stereos, etc. read it reliably).

---

> **Chapter 8 — Troubleshooting**

---

## 8.1 "ffmpeg binary not found"

`FfmpegNotFoundError` is raised when `ffmpeg` cannot be located. Causes:

- `ffmpeg` is not installed at all.
- `ffmpeg` is installed but not on the `PATH` of the shell that launched
  the app.
- The app is being launched from an IDE / `.desktop` file with a
  different `PATH` than your terminal.

Fix: install ffmpeg system-wide, **or** export `PANHA_FFMPEG` /
`PANHA_FFPROBE` before launching:

```bash
PANHA_FFMPEG=/opt/ffmpeg/bin/ffmpeg PANHA_FFPROBE=/opt/ffmpeg/bin/ffprobe python -m panha
```

## 8.2 PyQt6 import error on Linux

If `python -m panha` dies with a `xcb` / `libxcb-cursor0` /
`libxkbcommon-x11` complaint, install the runtime Qt deps:

```bash
sudo apt-get install -y \
  libegl1 libgl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0 \
  libxcb-xkb1 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3
```

(See `.github/workflows/ci.yml` for the exact list CI installs.)

## 8.3 Tests fail with "could not connect to display"

The pytest-qt suite needs **either** a real X display or the offscreen
platform plugin:

```bash
QT_QPA_PLATFORM=offscreen pytest -v
```

CI sets this env var explicitly.

## 8.4 Status column shows `Error: ...` in red

The status text contains the first 60 chars of the underlying
exception message. Common causes:

- `Error: ffmpeg binary not found...` — see §8.1.
- `Error: ffmpeg failed: ...` — the underlying ffmpeg child exited with
  non-zero. Re-run the same source through ffmpeg in a terminal to see
  the full stderr.
- `Error: [Errno 28] No space left on device` — output folder full.

The temp file is cleaned up automatically so there's no half-written
output to remove manually.

## 8.5 "Cover image is not embedded"

Check:

1. The Cover field actually points at an existing file (or a folder
   containing one of `.png`, `.jpg`, `.jpeg`, `.webp`).
2. The output format supports embedded artwork. MP3 / M4A / FLAC do;
   OGG is more limited.
3. Confirm with `ffprobe`:

   ```bash
   ffprobe -v error -show_streams -of json output.mp3 \
     | jq '.streams[] | select(.codec_type=="video")'
   ```

   You should see one stream with `codec_name == "mjpeg"` and
   `disposition.attached_pic == 1`.

## 8.6 Preview button does nothing

The preview player needs a working `QtMultimedia` backend. Make sure
`PyQt6-Qt6` is installed (it ships the Qt multimedia plugins) and that
your system has a media backend available (PulseAudio / PipeWire on
Linux, CoreAudio on macOS, WMF on Windows).

## 8.7 Reset Templates Store

If `~/.panha_templates.json` is corrupted, the app silently falls back
to "no templates" (the loader returns `{}`). To clean-slate:

```bash
mv ~/.panha_templates.json ~/.panha_templates.json.bak
```

The file will be re-created next time you click **Save As**.

---

> **Chapter 9 — Developer Workflow**

---

## 9.1 Layout Recap

- `panha/` — the package.
- `tests/` — pytest + pytest-qt suite (`test_mastering.py`,
  `test_metadata_writer.py`, `test_templates.py`, `test_ui_smoke.py`,
  `test_worker.py`).
- `docs/test-plan.md` — the manual smoke test plan used when the app
  was first cut (see for a concrete UI walk-through and expected
  ffprobe values).

## 9.2 Lint + Tests

```bash
ruff check panha tests
QT_QPA_PLATFORM=offscreen pytest -v
```

ruff is configured in `pyproject.toml`:

| Option | Value |
|---|---|
| `select` | `["E", "F", "I", "B", "UP", "N"]` |
| `ignore` | `["E501"]` (long-line — line-length is 110) |
| `target-version` | `py310` |
| `line-length` | `110` |

## 9.3 Continuous Integration

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

| Step | Command |
|---|---|
| OS deps | `sudo apt-get install -y ffmpeg libegl1 libgl1 libxkbcommon0 libxcb-* libxkbcommon-x11-0 libfontconfig1 libdbus-1-3` |
| Install | `pip install -e .[dev]` |
| Lint | `ruff check panha tests` |
| Test | `QT_QPA_PLATFORM=offscreen pytest -v` |

Matrix: Python `3.10`, `3.11`, `3.12` on `ubuntu-latest`,
`fail-fast: false`.

## 9.4 Adding a New Mastering Slider

1. Add a new attribute on `MasteringSettings` (in `panha/mastering.py`)
   with a sensible default of `0`.
2. Append an entry to the appropriate group tuple (`EQ_NAMES`,
   `DYN_NAMES`, `FX_NAMES`, or `OUT_NAMES`) so it is included in
   `ALL_SLIDERS`.
3. Add a `to_filter_chain` branch that emits the right ffmpeg filter
   for `value > 0`.
4. Add a `_SliderSpec` entry to `SLIDER_SPECS` in
   `panha/widgets/mastering.py` so the column shows up in the UI.
5. Add a unit test in `tests/test_mastering.py` covering both the zero
   case (no filter emitted) and the maxed case (the expected expression
   string).

## 9.5 Adding a New Metadata Field

1. Add the field to `Metadata` in `panha/metadata/ffmpeg_writer.py`
   (it's a `@dataclass`).
2. Add it to the `mapping` dict inside `Metadata.to_ffmpeg_args()` —
   keys here are ffmpeg `-metadata` keys, not ID3v2 frame names.
3. Surface a widget for it in
   `panha/dialogs/file_info_dialog.py::FileInformationDialog._build_ui`,
   load it in `_load_state`, and persist it in `collect_state`.
4. Bump `FileInformationState.to_dict` / `from_dict` so saved templates
   round-trip the new field.
5. Add a `test_metadata_writer.py` case that asserts the new key
   appears in `ffprobe -show_format` output.

## 9.6 Deployment Checklist

- [ ] `pyproject.toml` `version` bumped.
- [ ] `panha/__init__.py` `__version__` matches.
- [ ] `ruff check panha tests` clean.
- [ ] `QT_QPA_PLATFORM=offscreen pytest -v` green on all matrix Pythons.
- [ ] `README.md` features list reflects any new dialogs / sliders.
- [ ] `TRAINING_MANUAL.md` (this file) reflects any new user-visible
      behaviour.

---

## Appendix A — Default Paths

| Path | Used for |
|---|---|
| `~/.panha_templates.json` | Saved Setting Console templates (JSON dict keyed by name). |
| `~/PanhaExports` | Default export folder when **Output Folder** has never been set. |

## Appendix B — Environment Variables

| Variable | Effect |
|---|---|
| `PANHA_FFMPEG` | Absolute path to the `ffmpeg` binary the writer should invoke. Falls back to `which ffmpeg`. |
| `PANHA_FFPROBE` | Absolute path to the `ffprobe` binary the duration probe should invoke. Falls back to `which ffprobe`. |
| `QT_QPA_PLATFORM` | Set to `offscreen` for headless test runs. |

## Appendix C — Supported File Extensions

`.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`, `.aac`

Both the Batch Queue and the AI Music Detector reuse the same allow-list.
Files with any other extension are silently skipped when adding (no
error toast).

## Appendix D — Status Column Vocabulary

| Status text | Meaning | UI colour |
|---|---|---|
| `Pending` | Queued but not yet handed to the worker. | default |
| `Processing` | Currently running through ffmpeg. | cyan |
| `Done` | Worker reported success. | green |
| `Cancelled` | Stopped before completion via Stop Export. | default |
| `Error: ...` | Worker raised; first 60 chars of the message follow. | red |
