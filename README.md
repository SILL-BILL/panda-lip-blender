# panda-lip-blender

Blender Extension that imports PandaLip v1 (`.pandalip`) AIUEO weights as
animation on a controller armature. Phase A stops at the controller layer and
does not create shape-key drivers or depend on any particular character rig.

## Usage

1. Analyze a WAV file with Panda Lip.
2. Export the analysis as a `.pandalip` file.
3. In Blender, select the target Armature in **Panda Lip > Panda Lip Import**.
4. Select the `.pandalip` file.
5. Set the Start Frame.
6. Choose the Key Reduction quality. Use **Original** for the Phase A reference behavior.
7. Click **Import PandaLip**.
8. Use the generated animation on `CTRL_Lip_A/I/U/E/O` through your own Drivers
   or facial rig setup.

## Reference controller

The target Armature must contain these pose bones:

- `CTRL_Lip_A`
- `CTRL_Lip_I`
- `CTRL_Lip_U`
- `CTRL_Lip_E`
- `CTRL_Lip_O`

Each channel is animated as local `location.x`, where `0.0` is neutral and
`1.0` is maximum. The importer creates controller animation only. It does not
directly animate Shape Keys or create, replace, or modify Drivers.

## Phase A behavior

- Targets `CTRL_Lip_A`, `CTRL_Lip_I`, `CTRL_Lip_U`, `CTRL_Lip_E`, and
  `CTRL_Lip_O` pose bones on a user-selected Armature.
- Writes only each pose bone's local `location.x`; Y/Z, rotation, scale, drivers,
  and constraints are not changed.
- Converts time with
  `start_frame + time_seconds * (scene.render.fps / scene.render.fps_base)`.
- Keeps floating-point subframe key positions and uses LINEAR interpolation.
- Creates a new `PandaLip_<file-stem>` Action. Blender's normal numeric suffix
  makes collisions safe; existing Actions are never overwritten or deleted.
- Fully validates the PandaLip v1 document, target, required bones, and FPS
  before creating an Action. A failure during Action construction is rolled back.

The 3D View sidebar panel is under **Panda Lip > Panda Lip Import**. Start Frame
defaults to 1 and is independent of the scene playback range.

## Key Reduction

Key Reduction uses an error-bounded, RDP-style piecewise-linear simplifier. The
error is measured vertically at every original PandaLip sample time, so the
reduced LINEAR curve is guaranteed to stay within the selected Tolerance, apart
from floating-point epsilon. The first and last samples are always retained.
Sharp local features are anchored only when their immediate interpolation error
already exceeds Tolerance; minor peaks are not retained unconditionally.

| Quality | Tolerance | Behavior |
| --- | ---: | --- |
| Original | Off | Keeps every source sample exactly |
| High | 0.0025 | Quality priority |
| Middle | 0.01 | Balanced preset |
| Low | 0.02 | Key-count reduction priority |
| Custom | User value | Maximum absolute error from 0.0 through 1.0 |

Reduction is performed independently for A/I/U/E/O. It does not alter the
`.pandalip` file, Action naming, Subframe timing, or LINEAR interpolation.

## Build

### Windows

1. Open `build.bat` and set `BLENDER_EXE` to your Blender executable.
2. Double-click `build.bat`.
3. Install the generated ZIP from `dist/` in Blender.

The script works relative to its own location, so the repository may be on any
drive or in a path containing spaces. It creates `dist/` when needed and only
replaces the ZIP for the current manifest id and version; other files in `dist/`
are retained. Automated callers can use `build.bat --no-pause`.

### Manual build

Build the Extension package with Blender 4.2 or newer:

```powershell
blender --command extension build --source-dir panda_lip_blender --output-dir dist
```

## Test

Run normal-Python unit tests from the repository root:

```powershell
python -m unittest discover -s tests -t . -v
```

Run the synthetic tolerance evaluation:

```powershell
python -m tests.evaluate_reduction
```

The Blender integration test opens the supplied reference file without saving it:

```powershell
blender --background --factory-startup PandaLip_Controller_Test.blend `
  --python tests/blender/reference_integration.py
```

The five-minute benchmark accepts `ORIGINAL`, `HIGH`, `MIDDLE`, `LOW`, or
`CUSTOM <tolerance>` after `--`:

```powershell
blender --background --factory-startup PandaLip_Controller_Test.blend `
  --python tests/blender/long_duration_benchmark.py -- MIDDLE
```

The source manifest targets Blender 4.2+. Phase A is exercised against Blender
5.1's layered Action API while retaining the legacy F-Curve access path used by
earlier supported Blender versions.
