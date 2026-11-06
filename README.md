# Inkreel

A 2D animation studio you build with Claude Code and watch in a browser. Everything is hand-drawn in feel (boiling ink lines, paper grain), 2D, but you can **orbit around it in 3D**, **record** what you see to a video file, edit frame by frame, draw by hand, and record voices that drive the lip-sync.

No AI service is called by the app. **Claude Code is the director**: you talk to Claude Code in the terminal, it runs `inkreel` commands that build and edit the animation, and the studio shows the result live.

## Run it

```
pip install -e .            # Python 3.12+ (pydantic, fastapi, uvicorn, rich); opencv-python-headless for tracing pictures
inkreel build-sample        # optional: a small sample series
inkreel serve ibeno_tides --open
```

Open http://127.0.0.1:8790/?series=ibeno_tides. Studio build: `powershell -File build-studio.ps1` (needs Node). Recording to MP4 needs `ffmpeg` on your PATH.

## In the studio

| | |
|---|---|
| **Stage** | Drag to orbit, right-drag to pan, scroll to zoom, double-click to reset. Front / 3/4 / Side / Top buttons glide the camera. |
| **Record** | Records exactly what the stage shows (including any orbit you do while it plays, and recorded voices) and saves an MP4 into `<workspace>/exports/`. |
| **Timeline** | One row per character plus camera, effects, captions and drawings. Drag a block to retime it, click to jump, Lock so Claude cannot change it. Colours: teal = Claude, orange = you, purple = imported. |
| **Pose & keys** | Frame-by-frame posing: 14 joint sliders for the selected character at the current frame, **Set key**, previous/next key. A walk made by Claude is already a set of editable keys. |
| **Draw** | Draw by hand on the stage. Each frame you draw on becomes a cel (1, 2, 3 or 6 frames long) with onion skin, so stepping and drawing again gives hand-drawn animation. Drawings turn with the 3D view. |
| **Voice** | Lists the scene's dialogue. Edit a line (the mouth follows its letters). **Record voice** with the microphone while the scene plays: the mouth then follows your real voice. |

Undo / redo: Ctrl+Z / Ctrl+Shift+Z. Space plays, L loops.

## Building with Claude Code

Claude Code works through the same operations the studio uses. Examples it runs:

```
inkreel new my_series
inkreel op my_series create_character '{"id":"kabi","height":300,"weapon":"greatblade"}'
inkreel op my_series create_episode '{"id":"ep1","title":"Dusk"}'
inkreel run my_series build_scene.json        # many ops as one undoable step
inkreel status my_series                      # list scenes
inkreel lint my_series                        # check for overlap, missing reactions, unreadable timing...
inkreel undo my_series
```

Useful ops: `create_scene`, `place`, `walk` (writes an editable frame-by-frame walk cycle), `move`, `act` (library actions: punches, slashes, dodges, gestures...), `strike` (a whole attack exchange synced to the contact frame), `say`, `emote`, `camera`, `fx`, `pose_key`, `add_drawing`, `set_voice`, `define_action`.

### Characters from a picture

Give Claude Code a picture. It reads joint positions off the picture, then traces it into a rigged vector character (not generated: the picture's own shapes are cut into body parts):

```
inkreel trace-grid picture.png                      # picture with a coordinate grid, to read joint positions
inkreel trace-preview picture.png layout.json       # check the bone / body-part split on the picture
inkreel trace my_series kabi picture.png layout.json
```

The traced character walks, fights, speaks and orbits like any other, and keeps your picture's colours and shapes. Best results come from a side-view picture with a plain or transparent background. A front-facing picture is cut the same way, but a side-view walk will swing its limbs flat, like a paper cut-out.

### Checking a drawing against a reference (computer vision)

```
inkreel compare reference.png my_drawing.png --layout layout.json --out compare_out
```

Lines the drawing up with the reference (same height, same ground line) and reports, body part by body part, where it is too wide, too narrow, or shifted forward/back. Writes `overlay.png` (red = only in the reference, blue = only in the drawing). `mpvision.py` adds MediaPipe face landmarks (model from the `mirror` app, in `models/`, not committed).

## Data

Everything is plain JSON under your workspace folder (`series/<id>/...`), safe to hand-edit and to keep in git. History (undo / redo, snapshots) is in `.inkreel/index.sqlite`.

## Limits (honest)

- The 3D view is 2D layers placed in depth (like a stack of cut-outs with thickness), not a 3D model. From the side, a character looks like a slab.
- Lip-sync follows the loudness of your recording (or the letters of the line), not exact phonemes.
- Tracing needs joint positions; automatic body-part detection from any picture is not attempted.
- Recording runs in real time in the browser.
