# Structure Lab 3 — Civil Engineering student project

A second-year Civil Engineering learning project connecting structural mechanics with Python programming. The interactive workflow is inspired by the **model → assign → load → analyse → inspect** workflow of desktop frame software. It is not affiliated with SAP2000 and does not reproduce its interface or capabilities.

The direct-stiffness solver is implemented in NumPy. Streamlit supplies the editing panels; a small bundled SVG component supplies canvas drawing, snapping, dragging and selection; Plotly supplies deformed geometry and engineering diagrams. No structural-analysis package, external API, CDN, JavaScript build or account is required.

**Scope:** linear elastic, small-displacement 2D Euler–Bernoulli frames with three joint DOFs. Legacy 2D trusses remain supported. First normal-stress yield, a user-defined translation limit and optional in-plane Euler member screening are separate checks. This app does **not** predict fracture, realistic post-yield behaviour or structural collapse.

## Start as a NEW project on Windows

Keep your existing project. This ZIP can run independently.

1. Download `structure_lab_3.zip` into Downloads.
2. Right-click it → **Extract All…** → **Extract**. Do not run files from inside the ZIP.
3. Open the extracted `structure_lab_3` folder, then its `structural_fea` folder.
4. Double-click **START_WINDOWS.bat**. Windows may hide `.bat` and show START_WINDOWS.
5. Keep its terminal window open. The launcher finds Python/Anaconda, creates a private `.venv`, installs missing dependencies, then starts the app. Installation requires internet; analysis runs locally.
6. Open the **Local URL** printed in that window, normally http://localhost:8501. If another app occupies that port, use the different URL printed by Streamlit.

The launcher was reviewed, but was not executed on Windows during Linux development. If it cannot find Python, use the Anaconda instructions below. If installation is interrupted, run the launcher again; it reuses completed downloads/installations where possible.

### Exact Anaconda commands

Open **Start → Anaconda Prompt**. Copy each line separately, press Enter, and wait for it to finish:

```bat
cd /d "%USERPROFILE%\Downloads\structure_lab_3\structural_fea"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt --timeout 120 --retries 10
.venv\Scripts\python.exe -m streamlit run app.py
```

If the first line says the path cannot be found, open the extracted folder containing `app.py` in File Explorer. Click its address bar and copy that actual folder path. In Anaconda Prompt type `cd /d `, then paste that path inside double quotes, and press Enter. The path must end at the folder containing `app.py`, not at the ZIP.

For later runs, only the first and last commands are needed. Stop with **Ctrl+C** in the terminal. Do not double-click `app.py`.

Use Python 3.10 or newer. Verification used Python 3.12; direct tested dependency versions are in `requirements-tested.txt`. Normal installation uses bounded compatible versions in `requirements.txt`.

### macOS/Linux

From the extracted project folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

## Your first beam, without editing code

1. Open **Examples & files**. Select **frame**, tick **Confirm replacing the current model**, then **Start empty model**.
2. On the canvas select **Add node**. Click grid coordinates **(0, 0)** and **(6, 0)**. Default snapping is 0.5 m. Exact X/Y values are editable in **Model**.
3. Select **Draw member**, then click N1 followed by N2. The new E1 starts as a 100 × 200 mm rectangular steel section.
4. Open **Properties**. Choose **Rectangle**, width **100 mm**, depth **200 mm**, E **210 GPa**, fy **355 MPa**. Click **Save properties**.
5. Click N1 → **Add support** → **Pinned** → **Save support**. Click N2 → choose **Roller Y** → **Save support**.
6. Select E1 → **Apply load** → **Distributed**. Choose **Full length**, intensity **10 kN/m**, direction **Down ↓**, then **Add distributed load**.
7. Click **Analyse**. The app switches to **Analysis view**. In **Drawing controls**, enable **Show deformed shape** and adjust magnification. Actual displacement is shown in the metric and hover labels; the dashed curve is exaggerated.
8. Open **Results**. Inspect member diagrams, reactions and **Limit assessment**. For this section, the beam has 30 kN reactions, 45 kN·m maximum moment and **12.0536 mm** maximum displacement. The original custom-section beam example has a different I and therefore a different deflection.
9. Click **Export model JSON** to save. Closing the server/session can lose unsaved session edits.

A compact version of this guide is included in the sidebar.

## Visual editing and shortcuts

The large **Edit model** canvas supports:

- **Select / move:** select a node or member; drag a node and release to save. All changes pass the Python validator. A rejected edit restores the saved model.
- **Add node:** click empty grid space. Snap spacing is adjustable; turn it off for free placement.
- **Draw member:** click two existing nodes. Add nodes first. Existing members, nodes and end releases are retained when applying loads.
- **Pan:** drag the background. Scroll to zoom. Axes always use the same scale. **Reset view** fits the model.
- Optional labels/load arrows and property hover labels. Gold identifies the selected objects.
- With keyboard focus inside the canvas: **V** select, **N** add node, **M** draw member, **P** pan, **F** fit, **Escape** cancel, **Ctrl+Z** Undo, **Ctrl+Y** or **Ctrl+Shift+Z** Redo.

The top **Add member**, **Add support**, **Apply load**, **Analyse**, **Undo**, **Redo** and **Reset view** buttons complement the canvas tools. Selection lists and coordinate forms provide precise, accessible alternatives. Use **Model → Nodes/Elements** to delete selected objects. Deletion cascades to attached members/loads; Undo restores them.

Streamlit/Plotly alone does not expose reliable node dragging or arbitrary empty-canvas drawing. The bundled local SVG component handles these interactions, while Plotly remains the result viewer. **Analysis view is for viewing/selecting results; switch to Edit model to change geometry.** No third-party frontend installation is needed. The JavaScript is confined to `fea/canvas/index.html` and does no engineering calculations.

Current interaction limits: members connect existing nodes; no rubber-band auto-node creation, automatic intersection splitting, node merging, group dragging, snapping to member interiors, CAD import or mobile touch optimisation. Crossing members are connected only if they share a node ID. Keyboard shortcuts work when the canvas has focus. These limits are explicit; coordinate inputs provide the fallback.

Each Save or released drag updates the model. Form values must be saved before analysis. Previous results are hidden and marked outdated after a saved edit or active-case change. Undo/Redo retain up to 20 saved edits; new edits clear the redo branch.

## Properties, loads and units

| Quantity | Editing/display unit | Internal/JSON unit |
|---|---|---|
| Node position, load distance | m | m |
| Section dimensions | mm | m |
| E | GPa | Pa |
| fy | MPa | Pa |
| Density | kg/m³ | kg/m³ |
| A; I; custom fibre distances | m²; m⁴; m | same |
| Force; moment; UDL | kN; kN·m; kN/m | N; N·m; N/m |
| Displacement; rotation; stress | mm; rad; MPa | m; rad; Pa |

Rectangle, solid circle, hollow rectangle and symmetric I sections compute area, in-plane second moment and fibre distances automatically. Section depth lies along local y. Custom A/I and independent top/bottom extreme-fibre distances are supported. Density is stored and reports member mass; **self-weight is not automatically applied**. Add an explicit global downward UDL when needed.

Moment releases are in **Properties → Moment releases & Euler screening**. Release i and/or j independently. A release transmits axial/shear force but zero moment; it is not a translational disconnection. At a released end, member rotation can differ from joint rotation. All-released free joint rotations are undefined and export blank; member-end rotations are recovered separately.

Loads:

- **Point / moment:** global nodal Fx, Fy and anticlockwise Mz.
- **Member point:** force anywhere strictly inside a selected member, measured from raw start i; global X/Y or local X/Y direction. Consistent shape-function loading avoids inserting nodes. Apply endpoint loads using the nodal tab.
- **Distributed:** full or partial length, on one selected member or a chain of connected members. Distances follow the chain from the chosen endpoint. Select several members in the path list; the app orders them, including reversed raw connectivity. Global X/Y directions retain both resolved local components. Path normal is 90° anticlockwise to path travel.
- Named cases and editable combination factors. The active combination applies the factors before assembly. Negative factors are permitted.

Arrows show physical force direction; their length is symbolic. Intensity is per actual member length, not per horizontal projection. Trusses accept nodal forces only. Applied point moments between nodes, variable-intensity loads and thermal/prescribed-displacement loading are not implemented.

## Results and interpretation

Reactions use the complete assembled system, R = Kd − F. Exact piecewise displacement and internal-force recovery includes all distributed patches and member point forces; curved beams are not straight lines joining displaced nodes. Both sides of point-force jumps are included in diagrams/exports. Polynomial stationary points locate displacement, bending and stress extrema.

Signs: global X right, Y up, anticlockwise moment/rotation positive. Local x follows raw i→j; local y is 90° anticlockwise. N is tension-positive. dM/dx = V, dV/dx = qy and M = EI v″. Normal stress is **σ = N/A − My/I**, tension-positive. Reversing a member's raw orientation changes its local signs. Result diagrams and CSV columns use these definitions consistently.

**Limit assessment** reports:

- Maximum absolute translation magnitude along each member, its location and its ratio to the user limit. This includes frame sway and axial movement; it is not automatically an L/250 or chord-relative serviceability check.
- Maximum absolute top/bottom normal stress and its exact candidate location.
- Steel normal-stress/yield ratio and proportional first-yield multiplier fy/|σmax|. Missing fibre distances disable the stress check, rather than guessing a section depth from A/I.
- Optional **in-plane Euler** screening: Pcr = π²EI/(K Lb)². The user must enable it and specify K and the physical unbraced length Lb. It compares peak compression with Pcr. Do not substitute the FE mesh length for a column's physical buckling length. Pcr/A above fy is flagged outside elastic Euler validity; no eligible Euler ratio is reported then.
- The smallest multiplier among the **available** translation/yield/eligible Euler checks, with the governing member. A multiplier ≤1 means that specified screening limit is reached/exceeded in the active loading. Disabled/unavailable checks are not counted.

All multipliers scale the entire active case/combination proportionally from zero. They are not code safety factors. The model is not valid for realistic response after yielding. Euler does not assess combined beam-column interaction or full-frame stability. Excluded: shear yielding, local/out-of-plane/lateral-torsional buckling, connection failure, residual stress, imperfections, P–Δ, plastic redistribution, cracking and fracture. No design-code compliance is claimed.

## How the code works

Start with `docs/CODE_WALKTHROUGH.md` for a short reading guide. See `docs/THEORY.md` for the stiffness matrix, transformation and assembly, consistent loads, release condensation and exact recovery. Typical flow:

1. Validate geometry, properties, references and load paths.
2. Form local elastic stiffness k and consistent local load vector f.
3. Condense released rotational DOFs in **both k and f**.
4. Transform to global coordinates, assemble, apply zero-displacement restraints.
5. Check the scaled free stiffness spectrum and solve the reduced system. No pseudoinverse is used to conceal mechanisms.
6. Recover released member rotations, end actions, piecewise internal fields and elastic strain energy.
7. Evaluate exact candidate extrema, limits and exports.

Model size is limited to 150 nodes and 300 elements to keep the dense NumPy system understandable. Axial and bending deformation are included; shear deformation, shear stress, torsion, out-of-plane response, dynamics and geometric/material nonlinearity are not.

## Project layout

- `app.py`: application flow, state, Undo/Redo, result inspector.
- `fea/solver.py`: stiffness, assembly, releases, solution, recovery and energy.
- `fea/loads.py`: load paths, uniform intervals and member point equivalents.
- `fea/sections.py`, `fea/assessment.py`: section geometry and bounded screening checks.
- `fea/interface.py`, `fea/editing.py`: forms and atomic edits.
- `fea/canvas.py`, `fea/canvas/index.html`: interactive visual editor.
- `fea/visualization.py`, `fea/reporting.py`: Plotly and CSV output.
- `fea/examples.py`, `examples/`: reproducible models.
- `tests/`: analytical, editing, import/export and Streamlit tests.
- `docs/`: mathematics, validation, change log and interview guide.

Import older model JSON via **Examples & files → Import JSON → Import model**. Full-member legacy UDLs are migrated. Old models without stress material/fibre data remain analysable, but must have those properties assigned for assessment. Imports do not run code. JSON/CSV exports are plain data; CSV stress values are Pa, not MPa.

## Testing

```bat
.venv\Scripts\python.exe -m pytest -q
```

On macOS/Linux: `.venv/bin/python -m pytest -q`. The final automated run passed **121 tests**. Consult `docs/VALIDATION.md` and `docs/test-results.txt` for actual results and tolerances. The browser acceptance script is optional and has a separate development dependency file; it is not required to run the app.

## Portfolio description

“Developed an educational 2D structural-analysis workbench using Python, NumPy, Streamlit and Plotly. Implemented and validated direct-stiffness frame analysis, member releases, partial/path distributed loads and interior point forces. Added a visual model editor, section calculations and clearly bounded stress, translation and Euler screening checks. Compared analytical benchmarks and tested a complete browser modelling workflow.”

Only claim personal implementation/understanding you can demonstrate. The interview guide explains which derivations and limitations to learn before presenting the project.
