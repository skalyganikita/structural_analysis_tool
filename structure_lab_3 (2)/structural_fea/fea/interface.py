"""Small editing panels. All writes go through an undoable commit callback."""

from copy import deepcopy
import pandas as pd
import streamlit as st
from .solver import SUPPORTS, ModelError
from .loads import path_segments
from .editing import (
    new_member,
    next_id,
    remove_node,
    remove_elements,
    ordered_path,
    path_endpoints,
)


def frame(rows):
    return pd.DataFrame(rows)


def note(text):
    st.caption(text)


def geometry(model, commit, rev):
    target = st.radio(
        "Edit geometry", ["Nodes", "Elements"], horizontal=True, key="geometry_target"
    )
    if target == "Nodes":
        chosen = st.session_state.get("selected_node")
        old = next((n for n in model["nodes"] if n["id"] == chosen), None)
        mode = st.radio("Node action", ["Edit selected", "Add new"], horizontal=True)
        adding = mode == "Add new" or old is None
        if adding:
            old = dict(id=next_id(model["nodes"]), x=0.0, y=0.0, support="Free")
        with st.form(f'node_form_{rev}_{old["id"]}_{adding}'):
            st.markdown(f'**{"New" if adding else "Selected"} node N{int(old["id"])}**')
            x = st.number_input(
                "X [m]",
                value=float(old["x"]),
                format="%.4f",
                key=f'node_x_{rev}_{old["id"]}_{adding}',
            )
            y = st.number_input(
                "Y [m]",
                value=float(old["y"]),
                format="%.4f",
                key=f'node_y_{rev}_{old["id"]}_{adding}',
            )
            save = st.form_submit_button(
                "Add node" if adding else "Save node", type="primary"
            )
        if save:
            out = deepcopy(model)
            new = dict(old, x=x, y=y)
            if adding:
                out["nodes"].append(new)
            else:
                out["nodes"] = [
                    new if n["id"] == old["id"] else n for n in out["nodes"]
                ]
            commit(out, ("node", new["id"]))
        if not adding:
            attached = [
                e["id"] for e in model["elements"] if chosen in (e["i"], e["j"])
            ]
            note(
                f"Deleting N{int(chosen)} also removes attached elements {attached}, its point loads and distributed paths using those elements. Undo is available."
            )
            if st.button("Delete selected node", key="delete_node"):
                commit(remove_node(model, chosen))
        with st.expander("Node table"):
            st.dataframe(frame(model["nodes"]), hide_index=True, width="stretch")
    else:
        if len(model["nodes"]) < 2:
            st.info("Add at least two nodes before creating an element.")
            return
        ids = [n["id"] for n in model["nodes"]]
        chosen = st.session_state.get("selected_element")
        old = next((e for e in model["elements"] if e["id"] == chosen), None)
        mode = st.radio("Element action", ["Edit selected", "Add new"], horizontal=True)
        adding = mode == "Add new" or old is None
        if adding:
            old = new_member(next_id(model["elements"]), ids[0], ids[-1])
        with st.form(f'element_form_{rev}_{old["id"]}_{adding}'):
            st.markdown(
                f'**{"New" if adding else "Selected"} element E{int(old["id"])}**'
            )
            i = st.selectbox(
                "Start node i",
                ids,
                index=ids.index(old["i"]),
                format_func=lambda n: f"N{int(n)}",
            )
            j = st.selectbox(
                "End node j",
                ids,
                index=ids.index(old["j"]),
                format_func=lambda n: f"N{int(n)}",
            )
            note(
                "New members use a 100 × 200 mm rectangular steel section. Change it in Properties."
            )
            save = st.form_submit_button(
                "Add element" if adding else "Save connectivity", type="primary"
            )
        if save:
            out = deepcopy(model)
            new = dict(old, i=i, j=j)
            if adding:
                out["elements"].append(new)
            else:
                out["elements"] = [
                    new if e["id"] == old["id"] else e for e in out["elements"]
                ]
            commit(out, ("element", new["id"]))
        if not adding:
            note(
                "Deleting a member also removes distributed load definitions whose paths include it. Undo is available."
            )
            if st.button("Delete selected element"):
                commit(remove_elements(model, [chosen]))
        with st.expander("Element connectivity table"):
            st.dataframe(
                frame([{k: e[k] for k in ("id", "i", "j")} for e in model["elements"]]),
                hide_index=True,
                width="stretch",
            )
    note(
        "Shared node IDs make connections. Crossing lines without a common node are not connected."
    )


def properties(model, commit, rev):
    from .sections import section_properties
    import math

    ids = [e["id"] for e in model["elements"]]
    if not ids:
        st.info("Add a member first.")
        return
    chosen = st.session_state.get("selected_element") or ids[0]
    old = next(e for e in model["elements"] if e["id"] == chosen)
    shapes = ["Rectangle", "Circle", "Hollow rectangle", "I section", "Custom"]
    shape = st.selectbox(
        "Section shape",
        shapes,
        index=shapes.index(old.get("section_shape", "Custom")),
        key=f"shape_{rev}_{chosen}",
    )
    dims = old.get("section_dimensions", {})
    with st.form(f"properties_{rev}_{chosen}_{shape}"):
        targets = st.multiselect(
            "Apply properties to elements",
            ids,
            default=[chosen],
            format_func=lambda i: f"E{int(i)}",
        )
        material = st.selectbox(
            "Material",
            ["Steel", "Other elastic"],
            index=0 if old.get("material", "Steel") == "Steel" else 1,
        )
        preset = st.caption(
            "Starting steel: E = 210 GPa, fy = 355 MPa, density = 7850 kg/m³. Edit to match your material."
        )
        E = st.number_input(
            "Young’s modulus E [GPa]",
            min_value=0.000001,
            value=old["E"] / 1e9,
            format="%.6f",
        )
        fy = st.number_input(
            "Yield strength fy [MPa]",
            min_value=0.001,
            value=float(old.get("fy") or 355e6) / 1e6,
        )
        density = st.number_input(
            "Density [kg/m³]",
            min_value=0.001,
            value=float(old.get("density") or 7850.0),
        )
        dimensions = {}
        labels = {
            "b": ("Width b [mm]", 100.0),
            "h": ("Depth h [mm]", 200.0),
            "t": ("Wall thickness t [mm]", 8.0),
            "diameter": ("Diameter [mm]", 100.0),
            "tw": ("Web thickness [mm]", 8.0),
            "tf": ("Flange thickness [mm]", 12.0),
        }
        keys = {
            "Rectangle": ["b", "h"],
            "Circle": ["diameter"],
            "Hollow rectangle": ["b", "h", "t"],
            "I section": ["b", "h", "tw", "tf"],
        }
        if shape == "Custom":
            for key, label, default in [
                ("A", "Area A [m²]", old["A"]),
                ("I", "Second moment I [m⁴]", old.get("I", 8e-5)),
                ("c_top", "Top fibre distance [m]", old.get("c_top") or 0.1),
                ("c_bottom", "Bottom fibre distance [m]", old.get("c_bottom") or 0.1),
            ]:
                dimensions[key] = st.number_input(
                    label, min_value=1e-15, value=float(default), format="%.10f"
                )
            note(
                "For imported sections, confirm both fibre distances. They cannot be inferred from A and I alone."
            )
        else:
            for key in keys[shape]:
                label, default = labels[key]
                dimensions[key] = (
                    st.number_input(
                        label,
                        min_value=0.001,
                        value=float(dims.get(key, default / 1000)) * 1000,
                    )
                    / 1000
                )
        with st.expander("Moment releases & Euler screening", expanded=False):
            ri = st.checkbox(
                "Release moment at start i",
                value=old.get("release_i", False),
                disabled=model["type"] == "truss",
            )
            rj = st.checkbox(
                "Release moment at end j",
                value=old.get("release_j", False),
                disabled=model["type"] == "truss",
            )
            note(
                "Releases transmit axial/shear forces but zero end moment. Member-end and joint rotations can differ."
            )
            buckling = st.checkbox(
                "Enable in-plane Euler check",
                value=old.get("buckling_enabled", False),
                disabled=model["type"] == "truss",
            )
            K = st.number_input(
                "Effective-length factor K",
                min_value=0.01,
                value=float(old.get("effective_length_factor") or 1.0),
            )
            nodes = {n["id"]: n for n in model["nodes"]}
            a, b = nodes[old["i"]], nodes[old["j"]]
            length = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            bl = st.number_input(
                "Physical buckling length [m]",
                min_value=0.00001,
                value=float(old.get("buckling_length") or length),
            )
            note(
                "You choose K and the physical unbraced length. They are not inferred from supports or releases. If subdividing a column, do not use each mesh length as its buckling length. No out-of-plane/frame stability check is performed."
            )
        save = st.form_submit_button("Save properties", type="primary")
    if save:
        try:
            if not targets:
                raise ModelError("Select at least one target element.")
            props = section_properties(shape, **dimensions)
            out = deepcopy(model)
            for e in out["elements"]:
                if e["id"] in targets:
                    e.update(
                        props,
                        E=E * 1e9,
                        fy=fy * 1e6,
                        density=density,
                        material=material,
                        section_shape=shape,
                        section_dimensions=dimensions,
                        release_i=ri,
                        release_j=rj,
                        buckling_enabled=buckling,
                        effective_length_factor=K,
                        buckling_length=bl,
                    )
            commit(out)
        except ModelError as exc:
            st.error(str(exc))
    st.caption(f'Saved section: A = {old["A"]:.6g} m² · I = {old.get("I",0):.6g} m⁴')
    if old.get("c_top"):
        st.caption(f'Fibre distances: +{old["c_top"]:.5g} m / −{old["c_bottom"]:.5g} m')
    note(
        "Density is stored and used for mass reporting only. Self-weight is NOT applied automatically. Bending uses depth along local y. Fillets and section warping are omitted."
    )


def supports(model, commit, rev):
    if not model["nodes"]:
        st.info("Add a node first.")
        return
    ids = [n["id"] for n in model["nodes"]]
    nid = st.session_state.get("selected_node") or ids[0]
    old = next(n for n in model["nodes"] if n["id"] == nid)
    options = (
        list(SUPPORTS)
        if model["type"] == "frame"
        else ["Free", "Fixed", "Pinned", "Roller Y", "Roller X"]
    )
    with st.form(f"supports_{rev}_{nid}"):
        st.markdown(f"**Support at node N{int(nid)}**")
        kind = st.selectbox("Restraint", options, index=options.index(old["support"]))
        save = st.form_submit_button("Save support", type="primary")
    if save:
        out = deepcopy(model)
        next(n for n in out["nodes"] if n["id"] == nid)["support"] = kind
        commit(out)
    if old["support"] != "Free" and st.button("Remove support"):
        out = deepcopy(model)
        next(n for n in out["nodes"] if n["id"] == nid)["support"] = "Free"
        commit(out)
    st.dataframe(
        pd.DataFrame(
            [
                dict(
                    Support=k,
                    ux="Fixed" if v[0] else "Free",
                    uy="Fixed" if v[1] else "Free",
                    rotation="Fixed" if v[2] else "Free",
                )
                for k, v in SUPPORTS.items()
                if k in options
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    note(
        "Roller Y restrains vertical motion; Roller X restrains horizontal motion. A pinned frame support does not add separate member-end hinges."
    )


def load_cases(model, commit, rev):
    st.markdown("**Cases and combinations**")
    with st.form(f"new_case_{rev}"):
        name = st.text_input("New load case name")
        add = st.form_submit_button("Add load case")
    if add:
        out = deepcopy(model)
        out["cases"].append(name.strip())
        commit(out)
    case = st.selectbox("Case to manage", model["cases"], key="manage_case")
    note(
        "Deleting a case removes its loads and all combination terms that refer to it."
    )
    if st.button("Delete case and its loads", disabled=len(model["cases"]) < 2):
        out = deepcopy(model)
        out["cases"].remove(case)
        for key in [
            "nodal_loads",
            "distributed_loads",
            "udls",
            "member_loads",
            "combinations",
        ]:
            out[key] = [p for p in out[key] if p["case"] != case]
        commit(out)
    with st.form(f"combos_{rev}"):
        table = pd.DataFrame(model["combinations"], columns=["name", "case", "factor"])
        table["factor"] = pd.to_numeric(table["factor"], errors="coerce").astype(float)
        terms = st.data_editor(
            table,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "case": st.column_config.SelectboxColumn(
                    options=model["cases"], required=True
                ),
                "factor": st.column_config.NumberColumn(required=True),
            },
        )
        save = st.form_submit_button("Save combination terms")
    if save:
        out = deepcopy(model)
        out["combinations"] = (
            terms.astype(object).where(pd.notna(terms), None).to_dict("records")
        )
        commit(out)
    note(
        "Repeat the same combination name for each contributing case. Factors are user-defined; no code-prescribed factors are assumed."
    )


def next_label(rows, prefix):
    used = {str(p["id"]) for p in rows}
    i = 1
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def point_loads(model, commit, rev):
    if not model["nodes"]:
        st.info("Add a node first.")
        return
    rows = model["nodal_loads"]
    options = ["Add new"] + [p["id"] for p in rows]
    chosen = st.selectbox(
        "Point load",
        options,
        index=(
            options.index(st.session_state.get("last_point"))
            if st.session_state.get("last_point") in options
            else 0
        ),
        key=f"point_pick_{rev}",
    )
    adding = chosen == "Add new"
    nids = [n["id"] for n in model["nodes"]]
    old = (
        dict(
            id=next_label(rows, "P"),
            case=model["cases"][0],
            node=st.session_state.get("selected_node") or nids[0],
            fx=0.0,
            fy=-10000.0,
            mz=0.0,
        )
        if adding
        else next(p for p in rows if p["id"] == chosen)
    )
    with st.form(f"point_{rev}_{chosen}"):
        case = st.selectbox(
            "Case", model["cases"], index=model["cases"].index(old["case"])
        )
        nid = st.selectbox(
            "Loaded node",
            nids,
            index=nids.index(old["node"]),
            format_func=lambda i: f"N{int(i)}",
        )
        fx = st.number_input("Fx [kN] · +right", value=old["fx"] / 1000)
        fy = st.number_input("Fy [kN] · +up", value=old["fy"] / 1000)
        mz = st.number_input(
            "Mz [kN·m] · +anticlockwise",
            value=old["mz"] / 1000,
            disabled=model["type"] == "truss",
        )
        save = st.form_submit_button(
            "Add point load" if adding else "Save point load", type="primary"
        )
    if save:
        out = deepcopy(model)
        new = dict(
            id=old["id"], case=case, node=nid, fx=fx * 1000, fy=fy * 1000, mz=mz * 1000
        )
        if adding:
            out["nodal_loads"].append(new)
        else:
            out["nodal_loads"] = [new if p["id"] == old["id"] else p for p in rows]
        st.session_state.last_point = old["id"]
        commit(out, ("node", nid))
    if not adding and st.button("Delete point load"):
        out = deepcopy(model)
        out["nodal_loads"] = [p for p in rows if p["id"] != old["id"]]
        commit(out)
    note(
        "Use this tab for nodal forces/moments. The Member point tab places a force between nodes without splitting the member."
    )


DIRECTION_UI = {
    "Down ↓": ("Global Y", -1),
    "Up ↑": ("Global Y", 1),
    "Right →": ("Global X", 1),
    "Left ←": ("Global X", -1),
    "Path +normal": ("Path normal", 1),
    "Path −normal": ("Path normal", -1),
}


def distributed_loads(model, commit, rev):
    if model["type"] == "truss":
        st.info(
            "Distributed loads apply to frame/beam members. A pin-jointed truss has no member bending stiffness; apply its loads at joints instead."
        )
        return
    if not model["elements"]:
        st.info("Add beam/frame elements first.")
        return
    rows = model["distributed_loads"]
    options = ["Add new"] + [p["id"] for p in rows]
    chosen = st.selectbox(
        "Distributed load",
        options,
        index=(
            options.index(st.session_state.get("last_dist"))
            if st.session_state.get("last_dist") in options
            else 0
        ),
        key=f"dist_pick_{rev}",
    )
    adding = chosen == "Add new"
    eid = st.session_state.get("selected_element") or model["elements"][0]["id"]
    e = next(e for e in model["elements"] if e["id"] == eid)
    old = (
        dict(
            id=next_label(rows, "D"),
            case=model["cases"][0],
            elements=[eid],
            start_node=e["i"],
            start=0.0,
            end=None,
            q=-10000.0,
            direction="Global Y",
        )
        if adding
        else next(p for p in rows if p["id"] == chosen)
    )
    # Path controls live outside the form so length and endpoint options update immediately.
    tag = f'{rev}_{chosen}_{eid if adding else "saved"}'
    selected = st.multiselect(
        "Beam path · select connected elements",
        [e["id"] for e in model["elements"]],
        default=old["elements"],
        format_func=lambda i: f"E{int(i)}",
        key=f"path_{tag}",
    )
    endpoints = path_endpoints(model, selected)
    if not endpoints:
        st.info("Select an open chain of one or more connected members.")
        return
    start_node = st.selectbox(
        "Measure distance from node",
        endpoints,
        index=(
            endpoints.index(old["start_node"]) if old["start_node"] in endpoints else 0
        ),
        format_func=lambda n: f"N{int(n)}",
        key=f"path_start_{tag}_{selected}",
    )
    try:
        path = ordered_path(model, selected, start_node)
        segments = path_segments(model, path, start_node)
        length = sum(s["L"] for s in segments)
    except ModelError as exc:
        st.error(str(exc))
        return
    st.caption(
        "Path: " + " → ".join(f"E{int(i)}" for i in path) + f" · total {length:.4g} m"
    )
    st.session_state.path_preview = dict(
        elements=path, start_node=start_node, length=length
    )
    coverage = st.radio(
        "Loaded range",
        ["Full length", "Partial length"],
        index=0 if old["end"] is None and old["start"] == 0 else 1,
        horizontal=True,
        key=f"coverage_{tag}",
    )
    direction_default = next(
        k
        for k, (d, sign) in DIRECTION_UI.items()
        if d == old["direction"] and sign == (1 if old["q"] >= 0 else -1)
    )
    with st.form(f"distributed_{tag}_{coverage}_{path}_{start_node}"):
        case = st.selectbox(
            "Load case", model["cases"], index=model["cases"].index(old["case"])
        )
        magnitude = st.number_input(
            "Intensity [kN/m]", min_value=0.0, value=abs(old["q"]) / 1000, step=1.0
        )
        direction = st.selectbox(
            "Load direction",
            list(DIRECTION_UI),
            index=list(DIRECTION_UI).index(direction_default),
        )
        if coverage == "Partial length":
            a = st.number_input(
                "Start distance [m]",
                value=min(float(old["start"]), length),
                step=0.1,
                format="%.4f",
            )
            b = st.number_input(
                "End distance [m]",
                value=min(
                    float(old["end"] if old["end"] is not None else length), length
                ),
                step=0.1,
                format="%.4f",
            )
        else:
            a, b = 0.0, None
        save = st.form_submit_button(
            "Add distributed load" if adding else "Save distributed load",
            type="primary",
        )
    if save:
        coordinate, sign = DIRECTION_UI[direction]
        new = dict(
            id=old["id"],
            case=case,
            elements=path,
            start_node=start_node,
            start=a,
            end=b,
            q=magnitude * 1000 * sign,
            direction=coordinate,
        )
        out = deepcopy(model)
        if adding:
            out["distributed_loads"].append(new)
        else:
            out["distributed_loads"] = [
                new if p["id"] == old["id"] else p for p in rows
            ]
        st.session_state.last_dist = old["id"]
        commit(out)
    if not adding and st.button("Delete distributed load"):
        out = deepcopy(model)
        out["distributed_loads"] = [p for p in rows if p["id"] != old["id"]]
        commit(out)
    note(
        "Distances follow the selected path in metres. Global loads keep their physical direction, including both local components on inclined members. Path +normal points 90° anticlockwise to travel. Intensity is per actual member length, not horizontal projection."
    )


def loads(model, commit, rev):
    choice = st.radio(
        "Load editor",
        ["Distributed", "Point / moment", "Member point", "Cases & combinations"],
        key="load_editor",
    )
    if choice == "Distributed":
        distributed_loads(model, commit, rev)
    elif choice == "Point / moment":
        point_loads(model, commit, rev)
    elif choice == "Member point":
        member_points(model, commit, rev)
    else:
        load_cases(model, commit, rev)
    with st.expander("Saved loads (SI units)"):
        st.dataframe(frame(model["nodal_loads"]), hide_index=True, width="stretch")
        shown = [
            dict(
                p,
                elements=", ".join(map(str, p["elements"])),
                end="Path end" if p["end"] is None else str(p["end"]),
            )
            for p in model["distributed_loads"]
        ]
        st.dataframe(frame(shown), hide_index=True, width="stretch")


def member_points(model, commit, rev):
    if model["type"] != "frame":
        st.info("Member point loads require frame mode.")
        return
    if not model["elements"]:
        st.info("Add a member first.")
        return
    rows = model.get("member_loads", [])
    options = ["Add new"] + [p["id"] for p in rows]
    chosen = st.selectbox("Member point load", options, key=f"mp_pick_{rev}")
    adding = chosen == "Add new"
    eid = st.session_state.get("selected_element") or model["elements"][0]["id"]
    old = (
        dict(
            id=next_label(rows, "MP"),
            case=model["cases"][0],
            element=eid,
            x=1.0,
            p=-10000.0,
            direction="Global Y",
        )
        if adding
        else next(p for p in rows if p["id"] == chosen)
    )
    with st.form(f"mp_{rev}_{chosen}_{eid}"):
        st.write(f'Load on E{old["element"]} · position measured from raw start i')
        case = st.selectbox(
            "Member point case", model["cases"], index=model["cases"].index(old["case"])
        )
        x = st.number_input("Position from i [m]", min_value=0.0, value=float(old["x"]))
        p = st.number_input("Signed force [kN]", value=old["p"] / 1000)
        dirs = ["Global X", "Global Y", "Local X", "Local Y"]
        direction = st.selectbox(
            "Force coordinate direction", dirs, index=dirs.index(old["direction"])
        )
        note(
            "Positive global X = right, global Y = up. Local X follows i→j; local Y is 90° anticlockwise. Use a nodal load at an endpoint."
        )
        save = st.form_submit_button("Save member point load", type="primary")
    if save:
        new = dict(old, case=case, x=x, p=p * 1000, direction=direction)
        out = deepcopy(model)
        if adding:
            out["member_loads"].append(new)
        else:
            out["member_loads"] = [new if r["id"] == old["id"] else r for r in rows]
        commit(out)
    if not adding and st.button("Delete member point load"):
        out = deepcopy(model)
        out["member_loads"] = [r for r in rows if r["id"] != old["id"]]
        commit(out)
