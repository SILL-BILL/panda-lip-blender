# panda-lip-blender

Blender Extension that creates a standard AIUEO controller, imports PandaLip
v1 (`.pandalip`) weights as controller animation, and connects the controls to
arbitrary Mesh Shape Keys. No particular character rig or Shape Key naming
scheme is required.

## Usage

1. Analyze a WAV file with Panda Lip and export a `.pandalip` file.
2. Open the 3D View sidebar and select the **Panda Lip** tab.
3. Click **Create Panda Lip Controller**. The new controller is selected as the
   Target Armature automatically.
4. Select the `.pandalip` file and set the Start Frame.
5. Choose the Key Reduction quality. Use **Original** to retain every sample.
6. Click **Import PandaLip**.
7. Under **Driver Mapping**, select the Source controller and Target Mesh, then
   choose any Shape Key for each AIUEO channel that the model supports.
8. Click **Create Drivers**. Playing the imported Action now drives the mapped
   Shape Keys.

An existing compatible controller can be selected instead of generating one.

## Standard controller

**Create Panda Lip Controller** creates an independent `PandaLip` Armature at the
3D cursor in a `PandaLip` Collection:

```text
PandaLip_Root
├─ CTRL_Lip_A
├─ CTRL_Lip_I
├─ CTRL_Lip_U
├─ CTRL_Lip_E
└─ CTRL_Lip_O
```

The five controls are arranged as labelled A/I/U/E/O rows. Two shared hidden
mesh objects provide the guide/labels and switch Custom Shapes; they remain
organized in the controller Collection and are disabled for rendering and direct
selection.

Each channel has a Local Space Limit Location constraint: X is limited to
`0.0..1.0`, and Y/Z are fixed at `0.0`. Y/Z Location, Rotation, and Scale are
locked against accidental edits. The Root remains available for positioning the
whole controller. Creating again does not replace anything: a structurally valid
controller is reused as the Target and a warning is shown. Generation supports
Blender Undo.

## Controller contract

The import target and Driver Mapping Source Armature must contain these pose
bones:

- `CTRL_Lip_A`
- `CTRL_Lip_I`
- `CTRL_Lip_U`
- `CTRL_Lip_E`
- `CTRL_Lip_O`

Each channel is animated as local `location.x`, where `0.0` is neutral and
`1.0` is maximum. The importer still creates controller animation only; Driver
Mapping is a separate, explicit connection step.

## Driver Mapping

Select a **Source** Armature and a **Target Mesh** in the N-panel. The Target
must have at least one Shape Key besides Basis. Each A/I/U/E/O field searches
only the selected Mesh's Shape Keys; fields may be left empty and are skipped,
but at least one channel must be mapped. Basis and duplicate Shape Key choices
are rejected.

**Create Drivers** adds a native Blender Driver to each selected Shape Key
`value`. Its single `TRANSFORMS` variable reads the corresponding
`CTRL_Lip_X` bone's `LOC_X` in `LOCAL_SPACE`, and the expression is a direct
1:1 variable reference. No clamp, range remap, multiplier, or name matching is
applied.

Existing Drivers are never overwritten. An exact Panda Lip Driver for the same
Source, bone, and Shape Key is reported as already connected and reused;
anything else is a conflict. Panda Lip Drivers use the variable names
`pandalip_A` through `pandalip_O` as part of a strict native Driver signature.
**Remove Panda Lip Drivers** removes only signatures that exactly match the
currently selected Source/Target pair, leaving every other Driver untouched.

Target and mapping choices are Scene properties and are saved in the `.blend`.
Object pointers remain safe when an object is renamed. If a Shape Key is renamed
or the Target changes, the saved name is shown as Invalid and creation stops
without modifying Drivers. Multiple characters are supported by explicitly
choosing each Source/Target pair.

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

The 3D View sidebar panel is under **Panda Lip > Panda Lip**. Start Frame
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

Controller generation and all five Key Reduction choices can be tested headlessly:

```powershell
blender --background --factory-startup `
  --python tests/blender/controller_integration.py
```

Driver Mapping, conflict protection, rollback, multiple controllers, and the
full pipeline with every Key Reduction choice can be tested headlessly:

```powershell
blender --background --factory-startup `
  --python tests/blender/driver_mapping_integration.py
```

Blender disables Undo in background mode. Run the same test once in normal UI mode
to execute the Undo assertion; Blender closes automatically afterward:

```powershell
blender --factory-startup --python tests/blender/controller_integration.py `
  -- --quit-after-tests
```

Use `driver_mapping_integration.py` in the same UI command to exercise Driver
creation Undo. Mapping persistence is tested in two Blender processes, first to
save and then to reopen the file:

```powershell
blender --background --factory-startup --python-exit-code 1 `
  --python tests/blender/driver_mapping_persistence.py -- `
  --prepare --output path/to/phase-d-reopen.blend
blender --background --factory-startup path/to/phase-d-reopen.blend `
  --python-exit-code 1 `
  --python tests/blender/driver_mapping_persistence.py -- `
  --verify --output path/to/phase-d-reopen.blend
```

The five-minute benchmark accepts `ORIGINAL`, `HIGH`, `MIDDLE`, `LOW`, or
`CUSTOM <tolerance>` after `--`:

```powershell
blender --background --factory-startup PandaLip_Controller_Test.blend `
  --python tests/blender/long_duration_benchmark.py -- MIDDLE
```

The source manifest targets Blender 4.2+. The importer, generated controller,
and native Driver API are exercised against Blender 5.1's layered Action API
while retaining the legacy F-Curve access path used by earlier supported Blender
versions.
