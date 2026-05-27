# Test Plan — Panha Audio Meta Data v0.1.0 (PR #1)

## What changed (user-visible)

A brand-new PyQt6 + ffmpeg desktop app for batch editing MP3 metadata
(cover, title, artist, album, year, genre, comment, engineer, copyright,
software, source) styled like the X-MIXM reference. There is **no prior
behavior** to compare against — this is an initial implementation.

## Primary end-to-end flow (the one test that proves the feature works)

Launch the app, queue real MP3 files, fill in the **File Information** dialog
with a specific set of metadata values + a cover image, point the output at a
clean folder, run **Start Export**, then verify with `ffprobe` that the
exported file actually contains exactly the values that were typed into the UI
and the JPEG cover is embedded as an `attached_pic` video stream.

### Why this distinguishes working vs. broken

If the metadata writer is broken:
- `ffprobe` will not show the typed `title=`/`artist=`/`album=`/etc. values
- The output file will not have a `mjpeg` video stream with
  `disposition.attached_pic = 1`
- The Status column will not flip to "Done" in green; it will say
  "Error: …" in red

These are concrete, observable differences — the screenshots and the
`ffprobe` output will visibly differ between a working and broken build.

## Test environment

- App is launched locally from `/home/ubuntu/panha-audio-metadata` with
  `DISPLAY=:0 python -m panha`
- Source MP3s: `/home/ubuntu/test_mp3s/01._Track_1.mp3` … `04._Track_4.mp3`
  (synthesized earlier with ffmpeg `sine=…` — silent listenable tones)
- Cover image: `/home/ubuntu/test_mp3s/cover.jpg` (purple 512×512 JPEG)
- Output dir: `/home/ubuntu/test_mp3s/out_panha/` (cleared before the run)

## Test steps & pass/fail criteria

### Test 1 — "It should write all entered metadata + cover into the exported MP3"

Steps (concrete UI actions, in order):

1. Launch `python -m panha` and wait for the main window to render.
   - **Expected**: window title "Panha Audio Meta Data", dark theme,
     status bar says "Status: Active" in green, animated waveform visible.
2. Click **Add Files**, select the 4 MP3s in `/home/ubuntu/test_mp3s/`.
   - **Expected**: 4 rows appear in the Batch Queue. The Filename column
     shows `01._Track_1.mp3` … `04._Track_4.mp3`. Status column = "Pending".
     Duration column shows a non-zero `m:ss` time for each row.
3. Click **File Information**. Dialog opens.
   - **Expected**: "Enable Info Injection" is checked.
4. In the dialog, type the following exact values:
   - Title: `The Morning After`
   - Artist: `Panha`
   - Year: `2026`
   - Album: `Echoes of Cambodia`
   - Rating: `4`
   - Genre: `Lo-fi`
   - Cover: `/home/ubuntu/test_mp3s/cover.jpg` (using the `...` button)
   - Engineer: `Mr. Khann`
   - Copyright: `(c) 2026 Panha Records`
   - Software: `Panha Audio Meta Data v0.1.0`
   - Source: `Original Master`
   - Comment: `Mastered with care`
   - **Expected**: the small cover preview on the right shows a solid
     purple square (because cover.jpg is purple).
5. Click **Apply setting**.
   - **Expected**: dialog closes without an error.
6. Click **Output Folder**, choose `/home/ubuntu/test_mp3s/out_panha/`.
   - **Expected**: the "Output:" label at the bottom of the Setting Console
     updates to that path.
7. Click **▶ Start Export**.
   - **Expected (UI side)**:
     - Progress bar fills from 0% → 100%
     - All 4 Status cells flip to `Done` in **green** (not "Error:…" in red)
     - The Stop button briefly enables then disables when finished
8. Open a shell and run `ffprobe -v error -show_format -show_streams -of json <output>` on the first exported file.
   - **Expected (ffprobe side, EXACT VALUES)**:
     - `format.tags.title` == `"The Morning After"`
     - `format.tags.artist` == `"Panha"`
     - `format.tags.album` == `"Echoes of Cambodia"`
     - `format.tags.date` contains `"2026"`
     - `format.tags.genre` == `"Lo-fi"`
     - `format.tags.rating` == `"4"`
     - `format.tags.engineer` == `"Mr. Khann"`
     - `format.tags.copyright` == `"(c) 2026 Panha Records"`
     - `format.tags.encoded_by` == `"Panha Audio Meta Data v0.1.0"`
     - `format.tags.source` == `"Original Master"`
     - `format.tags.comment` == `"Mastered with care"`
     - There is exactly one stream with `codec_type=="video"` AND
       `codec_name=="mjpeg"` AND `disposition.attached_pic == 1`
9. Verify the output file is **smaller-or-comparable to the input + cover** (audio was stream-copied, not re-encoded).
   - **Expected**: `ls -l` of input vs output shows roughly the same audio
     payload size; output is input + cover bytes (no re-encode bloat).

#### Pass / fail

- **PASS**: every UI assertion in step 1-7 is visibly correct AND every
  ffprobe assertion in step 8 matches exactly AND step 9 holds.
- **FAIL**: any UI assertion is wrong, any ffprobe key/value mismatches, or
  there is no `attached_pic` video stream.

If any single ffprobe value differs from what was typed, mark the whole
test FAILED and surface the diff in the report. Do NOT mark it as
"mostly passed".

## Out of scope (not tested in this primary flow)

- Templates (Save As / Delete) — covered by unit tests
  (`tests/test_ui_smoke.py`)
- The Export Settings dialog (format/sample-rate/bit-depth/LUFS) — the PR
  description explicitly flags this dialog's non-tag fields as a stub for
  a follow-up PR
- Context-menu right-click items — covered by direct method-call coverage
- Decorative waveform animation — purely cosmetic
- "Add Folder" recursion — equivalent to "Add Files" plus a directory walk

## Evidence to capture

- Annotated screen recording of the full flow (start → exported)
- Final `ffprobe` JSON of the first exported file pasted into the report
- A "before / after" pair of screenshots: empty queue vs queue with 4
  "Done" rows
