"""Structure Lab 2. Run with START_WINDOWS.bat or python -m streamlit run app.py."""

from copy import deepcopy
import json
import numpy as np
import pandas as pd
import streamlit as st
from fea.examples import examples
from fea.solver import (
    validate,
    solve,
    fingerprint,
    load_names,
    parameter_study,
    ModelError,
)
from fea.loads import resolve_loads
from fea.editing import modernize, canvas_edit
from fea.canvas import editor
from fea.assessment import assess
from fea import interface as ui
from fea.visualization import model_figure, element_diagrams, study_figure
from fea.reporting import node_table, section_table, end_force_table

st.set_page_config(page_title="Structure Lab · 2D FEA", page_icon="🏗️", layout="wide")
st.markdown(
    """<style>
.block-container {padding-top: 1.4rem; max-width: 1660px;}
.stApp {background: #f4f7fa;} h1,h2,h3 {color: #203b51;}
[data-testid="stSidebar"] {background: #eaf0f5;}
[data-testid="stMetric"] {border:1px solid #dce6ee; border-radius:9px; padding:12px; background:white;}
[data-testid="stForm"] {background:white; border-color:#dce6ee;}
</style>""",
    unsafe_allow_html=True,
)


def install(model):
    st.session_state.model = modernize(model)
    st.session_state.rev = st.session_state.get("rev", 0) + 1
    st.session_state.undo = []
    st.session_state.redo = []
    st.session_state.view_reset = st.session_state.get("view_reset", 0) + 1
    for key in [
        "result",
        "result_hash",
        "study",
        "study_key",
        "selected_node",
        "selected_element",
        "active_case",
        "path_preview",
    ]:
        st.session_state.pop(key, None)


def commit(model, selection=None):
    """Validate the draft and commit all changes at once; never mutate on error."""
    try:
        validate(model, draft=True)
    except (ModelError, ValueError, TypeError, KeyError) as exc:
        st.error(f"Change not saved: {exc}")
        return
    st.session_state.redo = []
    history = st.session_state.undo
    history.append(deepcopy(st.session_state.model))
    st.session_state.undo = history[-20:]
    st.session_state.model = deepcopy(model)
    st.session_state.rev += 1
    st.session_state.pop("path_preview", None)
    if selection:
        st.session_state.pending_selection = selection
    st.rerun()


def history_step(direction):
    source = st.session_state.get(direction, [])
    if not source:
        return
    other = "redo" if direction == "undo" else "undo"
    st.session_state.setdefault(other, []).append(deepcopy(st.session_state.model))
    st.session_state.model = source.pop()
    st.session_state.rev += 1
    st.rerun()


def navigate(section, tool=None):
    st.session_state.section = section
    if tool:
        st.session_state.canvas_view = "Edit model"
        st.session_state.canvas_tool = tool


def clicked():
    state = st.session_state.get("canvas", {})
    points = state.get("selection", {}).get("points", [])
    if points:
        node_points = [
            p
            for p in points
            if isinstance(p.get("customdata"), (list, tuple))
            and len(p["customdata"]) == 2
            and p["customdata"][0] == "node"
        ]
        data = (node_points[-1] if node_points else points[-1]).get("customdata")
        if (
            isinstance(data, (list, tuple))
            and len(data) == 2
            and data[0] in ("node", "element")
        ):
            st.session_state["selected_" + data[0]] = int(data[1])
            st.session_state.geometry_target = (
                "Nodes" if data[0] == "node" else "Elements"
            )


if "model" not in st.session_state:
    install(examples()["Simply supported beam"])
if "pending_selection" in st.session_state:
    selection = st.session_state.pop("pending_selection")
    st.session_state["selected_" + selection[0]] = selection[1]
model = st.session_state.model
rev = st.session_state.rev
for kind in ("node", "element"):
    ids = [r["id"] for r in model[kind + "s"]]
    if st.session_state.get("selected_" + kind) not in ids:
        st.session_state["selected_" + kind] = ids[0] if ids else None
names = load_names(model)
if st.session_state.get("active_case") not in names:
    st.session_state.active_case = "Service" if "Service" in names else names[0]

with st.sidebar:
    st.markdown("### STRUCTURE LAB 3")
    st.caption("EDUCATIONAL · 2D FRAME WORKBENCH")
    st.divider()
    section = st.radio(
        "Workspace",
        ["Model", "Properties", "Supports", "Loads", "Results"],
        key="section",
    )
    st.divider()
    with st.expander("Examples & files", expanded=False):
        example = st.selectbox(
            "Example structure", list(examples()), key="example_choice"
        )
        if st.button("Load example", width="stretch"):
            install(examples()[example])
            st.rerun()
        note = "Loading an example replaces the model. Export your JSON first."
        st.caption(note)
        upload = st.file_uploader("Import JSON", type="json")
        if st.button("Import model", disabled=upload is None):
            try:
                if upload.size > 2_000_000:
                    raise ModelError("File must be smaller than 2 MB.")
                install(json.loads(upload.getvalue()))
                st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Cannot import: {exc}")
        mode = st.selectbox("New empty model type", ["frame", "truss"])
        clear_ok = st.checkbox("Confirm replacing the current model")
        if st.button("Start empty model", disabled=not clear_ok):
            install(
                dict(
                    type=mode,
                    nodes=[],
                    elements=[],
                    cases=["Load case 1"],
                    nodal_loads=[],
                    udls=[],
                    distributed_loads=[],
                    combinations=[],
                )
            )
            st.rerun()
    if st.button(
        "Undo last saved edit", disabled=not st.session_state.undo, width="stretch"
    ):
        history_step("undo")
    st.caption(
        "Each Save commits an edit. Undo keeps the last 20 saved edits. Unsaved form fields are not analysed."
    )
    st.divider()
    st.markdown(
        "**Input units**  \nGeometry: m  \nForces: kN · moments: kN·m  \nDistributed loads: kN/m  \nE: GPa · A: m² · I: m⁴"
    )
    st.caption("All solver values and JSON/CSV exports use labelled SI units.")

st.title("Structure Lab")
st.caption(
    "Educational linear elastic analysis · first yield and Euler screening are not collapse predictions"
)
if "flash" in st.session_state:
    st.error(st.session_state.pop("flash"))
with st.sidebar.expander("First model? Beam guide", expanded=False):
    st.markdown(
        "1. Open **Examples & files**, confirm replacement and start an empty **frame**.\n2. Use **Add node** on the canvas at (0, 0) and (6, 0), or enter exact coordinates in Model.\n3. Choose **Draw member**, then click N1 and N2.\n4. Open **Properties**, choose Rectangle, width **100 mm**, depth **200 mm**, and Save.\n5. Select N1 → **Add support** → Pinned → Save; select N2 → Roller Y → Save.\n6. Select E1 → **Apply load** → Full length → **10 kN/m Down** → Add distributed load. Click **Analyse**, then turn on the deformed shape and open Results."
    )

kind = model["type"]
current_hash = fingerprint(model)
ready = True
validation_message = ""
try:
    validate(model)
except ModelError as exc:
    ready = False
    validation_message = str(exc)
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    active = st.selectbox("Active case / combination", names, key="active_case")
with col2:
    st.write("")
    run = st.button("Analyse", type="primary", width="stretch", disabled=not ready)
with col3:
    st.write("")
    st.download_button(
        "Export model JSON",
        json.dumps(model, indent=2, allow_nan=False),
        "structure_model_v3.json",
        "application/json",
        width="stretch",
        on_click="ignore",
    )
if run:
    try:
        st.session_state.result = solve(model, active)
        st.session_state.result_hash = current_hash
        st.session_state.canvas_view = "Analysis view"
    except ModelError as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))
stored = st.session_state.get("result")
stale = stored is not None and (
    st.session_state.get("result_hash") != current_hash or stored.name != active
)
result = None if stale else stored
if stale:
    st.warning(
        "Results are outdated. Save your edits and run analysis again; previous results are hidden."
    )
elif result:
    st.success(
        f'Analysis complete · {active} · {len(model["nodes"])} nodes · {len(model["elements"])} elements'
    )
else:
    st.info("Choose an example or build a model, then Analyse.")
if not ready:
    st.warning("Model is a draft: " + validation_message)

toolbar = st.columns(6)
toolbar[0].button(
    "Add member",
    on_click=navigate,
    args=("Model", "member"),
    width="stretch",
    help="Draw a member by clicking its two existing end nodes.",
)
toolbar[1].button(
    "Add support",
    on_click=navigate,
    args=("Supports",),
    width="stretch",
    help="Assign a restraint to the selected node.",
)
toolbar[2].button(
    "Apply load",
    on_click=navigate,
    args=("Loads",),
    width="stretch",
    help="Loads default to the selected member or node.",
)
if toolbar[3].button("Undo", disabled=not st.session_state.undo, width="stretch"):
    history_step("undo")
if toolbar[4].button(
    "Redo", disabled=not st.session_state.get("redo"), width="stretch"
):
    history_step("redo")
if toolbar[5].button("Reset view", width="stretch"):
    st.session_state.view_reset = st.session_state.get("view_reset", 0) + 1
left, right = st.columns([0.30, 0.70], gap="large")
with right:
    s1, s2 = st.columns(2)
    s1.selectbox(
        "Selected node",
        [n["id"] for n in model["nodes"]],
        key="selected_node",
        format_func=lambda i: f"N{int(i)}" if i is not None else "None",
    )
    s2.selectbox(
        "Selected element",
        [e["id"] for e in model["elements"]],
        key="selected_element",
        format_func=lambda i: f"E{int(i)}" if i is not None else "None",
    )
    view = st.radio(
        "Canvas view",
        ["Edit model", "Analysis view"],
        horizontal=True,
        key="canvas_view",
    )
    if view == "Edit model":
        event = editor(
            model,
            active,
            rev,
            st.session_state.selected_node,
            st.session_state.selected_element,
            st.session_state.get("view_reset", 0),
            st.session_state.pop("canvas_tool", None),
        )
        if event and event.get("nonce") != st.session_state.get("last_canvas_event"):
            st.session_state.last_canvas_event = event.get("nonce")
            if event.get("revision") == rev:
                action = event.get("action")
                if action == "select":
                    st.session_state.pending_selection = (
                        event["kind"],
                        int(event["id"]),
                    )
                    st.session_state.geometry_target = (
                        "Nodes" if event["kind"] == "node" else "Elements"
                    )
                    st.rerun()
                elif action in ("undo", "redo"):
                    history_step(action)
                else:
                    try:
                        changed, selection = canvas_edit(model, event)
                        commit(changed, selection)
                    except (ModelError, ValueError, KeyError, TypeError) as exc:
                        st.session_state.flash = f"Canvas edit not saved: {exc}"
                        st.session_state.rev += 1
                        st.rerun()
        st.caption(
            "Draw connects existing nodes. Dragging commits on release; invalid edits are rejected. Crossing members do not connect unless they share a node. Precise coordinates are available in Model."
        )
    else:
        with st.expander("Drawing controls", expanded=False):
            a, b, c = st.columns(3)
            overlay = a.selectbox(
                "Member diagram",
                ["None", "N"] + (["V", "M"] if kind == "frame" else []),
                disabled=result is None,
                key="overlay",
            )
            reactions = b.checkbox(
                "Show reactions", value=False, disabled=result is None
            )
            dimensions = c.checkbox("Show member lengths", value=True)
            loads = a.checkbox("Show loads", value=True)
            axes = b.checkbox("Show local axes", value=False)
            dark = c.checkbox("Dark engineering view", value=True)
            deformed = st.checkbox(
                "Show deformed shape", value=False, disabled=result is None
            )
            a, b = st.columns(2)
            scale = a.number_input(
                "Deformation magnification",
                min_value=0.0,
                max_value=100000.0,
                value=50.0,
                step=10.0,
                disabled=result is None,
            )
            diagrams = b.slider(
                "Force diagram size", 0.2, 3.0, 1.0, 0.1, disabled=result is None
            )
        fig = model_figure(
            model,
            active,
            result,
            scale if result and deformed else 0.0,
            axes,
            st.session_state.selected_node,
            st.session_state.selected_element,
            overlay if result else "None",
            diagrams,
            reactions,
            dimensions,
            loads,
            dark,
        )
        fig.update_layout(uirevision=str(st.session_state.get("view_reset", 0)))
        st.plotly_chart(
            fig,
            width="stretch",
            theme=None,
            key="canvas",
            on_select=clicked,
            selection_mode="points",
        )
        st.caption(
            "Click a node or a member diamond to select it, or use the lists above. Gold highlights selection. Drag to pan; use the toolbar to zoom."
        )
    if result:
        a, b, c = st.columns(3)
        a.metric("Maximum translation", f"{result.max_displacement()*1000:.4f} mm")
        b.metric("Elastic strain energy", f"{result.energy:.5g} J")
        peak = max(
            np.max(np.abs(e.fields(e.critical_points())[4 if kind == "frame" else 2]))
            for e in result.elements
        )
        c.metric(
            "Maximum |M|" if kind == "frame" else "Maximum |N|",
            f"{peak/1000:.4g} " + ("kN·m" if kind == "frame" else "kN"),
        )
        if result.scaled_condition > 1e8:
            st.warning(
                "High stiffness condition number: results may be sensitive to numerical rounding."
            )
    st.caption(
        "Arrows show physical direction; arrow lengths are symbolic. Dashed deformation is magnified. Force-diagram positive ordinates lie on raw local +y; read signed labels and local axes."
    )
with left, st.container(height=660, border=False, key=f"panel_{section}"):
    st.subheader(section)
    if section == "Model":
        ui.geometry(model, commit, rev)
    elif section == "Properties":
        ui.properties(model, commit, rev)
    elif section == "Supports":
        ui.supports(model, commit, rev)
    elif section == "Loads":
        ui.loads(model, commit, rev)
    else:
        with st.form(f"limit_{rev}"):
            limit = st.number_input(
                "Translation limit [mm]",
                min_value=0.001,
                value=float(model.get("deflection_limit", 0.025)) * 1000,
                help="Maximum absolute translation, including sway, not deflection relative to the member chord.",
            )
            save_limit = st.form_submit_button("Save limit")
        if save_limit:
            changed = deepcopy(model)
            changed["deflection_limit"] = limit / 1000
            commit(changed)
        if result:
            st.markdown("**Result inspector**")
            st.write(f"Case: **{active}**")
            st.write(f"Scaled stiffness condition: **{result.scaled_condition:.4g}**")
            st.caption(
                "Select an element above the drawing to inspect its diagrams below. Turn on N, V or M in Drawing controls to see diagrams on the structure."
            )
            balance = result.equilibrium()
            st.dataframe(
                pd.DataFrame(
                    {
                        "Balance": ["ΣFx [N]", "ΣFy [N]", "ΣMz [N·m]"],
                        "Residual": balance,
                    }
                ),
                hide_index=True,
                width="stretch",
            )
            nodes_df = node_table(result)
            sections_df = section_table(result)
            ends_df = end_force_table(result)
            st.download_button(
                "Download nodal CSV",
                nodes_df.to_csv(index=False),
                "nodes_results.csv",
                "text/csv",
                on_click="ignore",
            )
            st.download_button(
                "Download section CSV",
                sections_df.to_csv(index=False),
                "section_results.csv",
                "text/csv",
                on_click="ignore",
            )
            st.download_button(
                "Download end-force CSV",
                ends_df.to_csv(index=False),
                "end_forces.csv",
                "text/csv",
                on_click="ignore",
            )
        else:
            st.info("Run the current model to inspect results and exports.")

if section == "Results" and result:
    tabs = st.tabs(
        [
            "Member diagrams",
            "Displacements & reactions",
            "Inside the solver",
            "Parameter study",
            "Limit assessment",
        ]
    )
    e = next(e for e in result.elements if e.id == st.session_state.selected_element)
    with tabs[0]:
        st.plotly_chart(element_diagrams(e, kind), width="stretch", theme=None)
        st.caption(
            "N is positive in tension. dM/dx′=V and dV/dx′=qy. M=EI·v″. Vertical dotted lines mark load boundaries. Signs refer to each member’s raw i→j axes."
        )
    with tabs[1]:
        st.dataframe(nodes_df, width="stretch", hide_index=True)
        with st.expander("Local element end actions"):
            st.caption(
                "End actions k·d−f_eq differ from signed section-force ordinates; M(0)=−s2, M(L)=s5."
            )
            st.dataframe(ends_df, width="stretch", hide_index=True)
        with st.expander("Resolved distributed load intervals"):
            # Actual factored patches are kept on the solved elements for combinations too.
            st.dataframe(
                pd.DataFrame(
                    [vars(p) for member in result.elements for p in member.patches]
                ),
                hide_index=True,
                width="stretch",
            )
    with tabs[2]:
        st.markdown("**Assembly → boundary conditions → solution → force recovery**")
        st.latex(r"K=\sum A_e^T T_e^T k_e T_e A_e,\qquad K_{ff}d_f=F_f,\qquad R=Kd-F")
        st.caption(
            "Aₑ above is the DOF assembly operator, not cross-sectional area. All prescribed displacements are zero."
        )
        dofs = (
            ["ui", "vi", "θi", "uj", "vj", "θj"]
            if kind == "frame"
            else ["ui", "vi", "uj", "vj"]
        )
        a, b = st.columns(2)
        a.markdown("**Local stiffness kₑ**")
        a.dataframe(pd.DataFrame(e.k, index=dofs, columns=dofs), width="stretch")
        if e.released:
            st.markdown("**Released-end condensed stiffness (used in assembly)**")
            st.dataframe(
                pd.DataFrame(e.condensed_k, index=dofs, columns=dofs), width="stretch"
            )
            st.write(
                "Recovered local end rotations [rad]:", e.displacement[[2, 5]].tolist()
            )
        b.markdown("**Coordinate transformation Tₑ**")
        b.dataframe(pd.DataFrame(e.T, index=dofs, columns=dofs), width="stretch")
        with st.expander("Global K and F"):
            st.dataframe(
                pd.DataFrame(
                    result.K, index=result.dof_labels, columns=result.dof_labels
                ),
                width="stretch",
            )
            st.dataframe(
                pd.DataFrame(
                    {
                        "DOF": result.dof_labels,
                        "F (N or N·m)": result.F,
                        "restrained": [i in result.fixed for i in range(len(result.F))],
                    }
                ),
                hide_index=True,
            )
        st.markdown(
            "Uniform load intervals use consistent integrals of axial and Hermite shape functions. Exact piecewise force and deformation recovery uses integrated equilibrium; no mesh subdivision is required at load boundaries. Energy quadrature is split at those boundaries."
        )
    with tabs[3]:
        a, b, c = st.columns(3)
        prop = a.selectbox(
            "Property", ["E", "A", "I"] if kind == "frame" else ["E", "A"]
        )
        ids = b.multiselect(
            "Study members",
            [e.id for e in result.elements],
            default=[e.id for e in result.elements],
        )
        bounds = c.slider("Multiplier range", 0.1, 3.0, (0.5, 2.0), 0.1)
        study_key = (current_hash, active, prop, tuple(ids), bounds)
        if st.button("Run parameter study"):
            try:
                st.session_state.study = parameter_study(
                    model, active, prop, ids, np.linspace(*bounds, 9)
                )
                st.session_state.study_key = study_key
            except ModelError as exc:
                st.error(str(exc))
        if (
            st.session_state.get("study_key") == study_key
            and "study" in st.session_state
        ):
            st.plotly_chart(study_figure(st.session_state.study, prop), width="stretch")
            st.download_button(
                "Download study CSV",
                pd.DataFrame(st.session_state.study).to_csv(index=False),
                "parameter_study.csv",
                "text/csv",
                on_click="ignore",
            )

    with tabs[4]:
        rows, governing = assess(result)
        if governing:
            factor, check, eid = governing
            message = f"Governing assessed limit: {check} · E{eid} · proportional multiplier {factor:.4g}"
            (st.warning if factor <= 1 else st.info)(message)
            if st.button("Select governing member"):
                st.session_state.pending_selection = ("element", eid)
                st.rerun()
        st.caption(
            "Each multiplier scales the entire active case/combination from zero, holding its load proportions fixed. A value ≤ 1 means this assessed limit is reached or exceeded. This is not a collapse load or a code safety factor."
        )
        assessment_df = pd.DataFrame(rows)
        selected = next(row for row in rows if row["element"] == e.id)
        a, b, c = st.columns(3)
        a.metric(
            f"E{e.id} · peak |normal stress|",
            (
                f'{selected["peak_normal_stress_Pa"]/1e6:.3f} MPa'
                if selected["peak_normal_stress_Pa"] is not None
                else "Assign fibres"
            ),
        )
        b.metric(
            "Normal-stress / yield",
            (
                f'{selected["yield_ratio"]:.3f}'
                if selected["yield_ratio"] is not None
                else "Not assessed"
            ),
        )
        c.metric(
            "First-yield multiplier",
            (
                f'{selected["first_yield_multiplier"]:.4g}'
                if selected["first_yield_multiplier"] is not None
                else "Not assessed"
            ),
        )
        st.write("Euler status: " + selected["euler_status"])
        summary = pd.DataFrame(
            [
                {
                    "Member": r["element"],
                    "Translation [mm]": r["max_translation_m"] * 1000,
                    "Translation ratio": r["translation_ratio"],
                    "Peak stress [MPa]": (
                        r["peak_normal_stress_Pa"] / 1e6
                        if r["peak_normal_stress_Pa"] is not None
                        else None
                    ),
                    "Stress x [m]": r["stress_x_m"],
                    "Yield ratio": r["yield_ratio"],
                    "Euler ratio": r["euler_ratio"],
                }
                for r in rows
            ]
        )
        st.dataframe(summary, width="stretch", hide_index=True)
        with st.expander("Detailed assessment values (SI units)"):
            st.dataframe(assessment_df, width="stretch", hide_index=True)
        st.download_button(
            "Download assessment CSV",
            assessment_df.to_csv(index=False),
            "assessment.csv",
            "text/csv",
            on_click="ignore",
        )
        raw = next(r for r in model["elements"] if r["id"] == e.id)
        if kind == "frame" and raw.get("c_top") and raw.get("c_bottom"):
            import plotly.graph_objects as go
            from fea.visualization import style

            x = e.critical_points([raw["c_top"], -raw["c_bottom"]])
            x = np.unique(np.r_[x, e.stations()])
            _, _, N, _, M = e.fields(x)
            fig = go.Figure()
            for name, y in [("Top", raw["c_top"]), ("Bottom", -raw["c_bottom"])]:
                fig.add_trace(
                    go.Scatter(
                        x=x, y=(N / e.A - M * y / e.I) / 1e6, name=name, mode="lines"
                    )
                )
            style(fig, f"E{e.id} · axial + bending normal stress [MPa]", 350)
            fig.update_layout(showlegend=True)
            fig.update_xaxes(title="Local x [m]")
            st.plotly_chart(fig, width="stretch", theme=None)
        else:
            st.info(
                "Assign section fibre distances in Properties to calculate bending stresses and first yield."
            )
        st.warning(
            "First normal-stress yield marks the end of this elastic model’s material validity. Euler is a separate, user-enabled in-plane member screening check. Neither predicts fracture, redistribution, post-yield response or actual collapse."
        )
        st.caption(
            "Omitted: shear yielding, local/lateral-torsional/out-of-plane buckling, connection failure, imperfections, residual stress, second-order P–Δ effects, plastic hinges and full-frame stability. Geometric mechanism detection only checks the unloaded linear stiffness matrix."
        )
        if result.inactive_rotations:
            st.info(
                "Blank rotations in the nodal CSV are joints with all incident ends released. Their joint rotation is undefined; each member-end rotation is recovered independently."
            )


with st.expander("Assumptions & sign conventions"):
    st.markdown(
        "Educational linear elastic, small-displacement analysis of straight prismatic members. Euler–Bernoulli frames neglect shear deformation. Trusses carry axial force only; shared frame nodes have rigid joints. Optional end moment releases use static condensation. No support settlements, second-order P–Δ, plasticity, dynamics or design-code checks. Euler screening is separate from the linear solve. Self-weight must be applied explicitly."
    )
    st.markdown(
        "Global +X is right and +Y is up; positive moment/rotation is anticlockwise. Local x′ runs from raw node i to j; y′ points 90° anticlockwise from x′. Load-path travel may be reversed relative to raw member axes. Reversing raw axes changes signed local moment conventions, not the physical solution."
    )
    st.caption(
        "Save and export model JSON to keep your work between sessions. CSV results use SI units. Use the bundled analytical checks before interpreting a new model."
    )
