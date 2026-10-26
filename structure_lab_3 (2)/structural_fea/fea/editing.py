"""Pure model-edit operations; the interface commits them as undoable transactions."""

from copy import deepcopy
from .solver import validate, ModelError
from .loads import path_segments


def next_id(rows):
    return max([int(r["id"]) for r in rows] + [0]) + 1


def modernize(model):
    """Losslessly migrate v1 full-member UDLs to editable path definitions."""
    model = deepcopy(model)
    validate(model, draft=True)
    model.setdefault("distributed_loads", [])
    used = {str(p["id"]) for p in model["distributed_loads"]}
    elements = {e["id"]: e for e in model["elements"]}
    for p in model["udls"]:
        number = 1
        while f"D{number}" in used:
            number += 1
        lid = f"D{number}"
        used.add(lid)
        e = elements[p["element"]]
        model["distributed_loads"].append(
            dict(
                id=lid,
                case=p["case"],
                elements=[p["element"]],
                start_node=e["i"],
                start=p.get("start", 0.0),
                end=p.get("end"),
                q=p["q"],
                direction="Path normal",
            )
        )
    model["udls"] = []
    for i, p in enumerate(model["nodal_loads"], 1):
        p.setdefault("id", f"P{i}")
    model.setdefault("member_loads", [])
    model.setdefault("deflection_limit", 0.025)
    model["schema_version"] = 3
    return model


def remove_elements(model, ids):
    out = deepcopy(model)
    ids = set(ids)
    out["elements"] = [e for e in out["elements"] if e["id"] not in ids]
    out["member_loads"] = [
        p for p in out.get("member_loads", []) if p["element"] not in ids
    ]
    out["udls"] = [p for p in out["udls"] if p["element"] not in ids]
    out["distributed_loads"] = [
        p
        for p in out.get("distributed_loads", [])
        if not ids.intersection(p["elements"])
    ]
    return out


def remove_node(model, nid):
    out = remove_elements(
        model, [e["id"] for e in model["elements"] if nid in (e["i"], e["j"])]
    )
    out["nodes"] = [n for n in out["nodes"] if n["id"] != nid]
    out["nodal_loads"] = [p for p in out["nodal_loads"] if p["node"] != nid]
    return out


def ordered_path(model, selected_ids, start_node):
    """Order an unordered selection only when it is one unambiguous open chain."""
    ids = set(selected_ids)
    if not ids:
        raise ModelError("Select one or more connected elements.")
    remaining = {e["id"]: e for e in model["elements"] if e["id"] in ids}
    if len(remaining) != len(ids):
        raise ModelError("Path includes a missing element.")
    result = []
    current = start_node
    while remaining:
        candidates = [e for e in remaining.values() if current in (e["i"], e["j"])]
        if len(candidates) != 1:
            raise ModelError(
                "Choose a path endpoint as the start node and a connected chain without branches."
            )
        e = candidates[0]
        result.append(e["id"])
        remaining.pop(e["id"])
        current = e["j"] if e["i"] == current else e["i"]
    path_segments(model, result, start_node)
    return result


def path_endpoints(model, ids):
    degree = {}
    for e in model["elements"]:
        if e["id"] in ids:
            for n in (e["i"], e["j"]):
                degree[n] = degree.get(n, 0) + 1
    return sorted(n for n, d in degree.items() if d == 1)


def new_member(eid, i, j):
    """A physical 100 × 200 mm rectangular steel starter section."""
    from .sections import section_properties

    return dict(
        id=eid,
        i=i,
        j=j,
        E=210e9,
        material="Steel",
        fy=355e6,
        density=7850.0,
        section_shape="Rectangle",
        section_dimensions=dict(b=0.1, h=0.2),
        release_i=False,
        release_j=False,
        buckling_enabled=False,
        **section_properties("Rectangle", b=0.1, h=0.2),
    )


def canvas_edit(model, event):
    """Pure, validated canvas commands. No automatic merging/intersection splitting."""
    out = deepcopy(model)
    action = event.get("action")
    selection = None
    if action == "add_node":
        n = dict(
            id=next_id(out["nodes"]),
            x=float(event["x"]),
            y=float(event["y"]),
            support="Free",
        )
        if any(
            abs(n["x"] - p["x"]) < 1e-9 and abs(n["y"] - p["y"]) < 1e-9
            for p in out["nodes"]
        ):
            raise ModelError(
                "A node already exists here; select it to connect members."
            )
        out["nodes"].append(n)
        selection = ("node", n["id"])
    elif action == "move_node":
        nid = int(event["id"])
        n = next((n for n in out["nodes"] if n["id"] == nid), None)
        if n is None:
            raise ModelError("Selected node no longer exists.")
        n.update(x=float(event["x"]), y=float(event["y"]))
        if any(
            p["id"] != nid
            and abs(n["x"] - p["x"]) < 1e-9
            and abs(n["y"] - p["y"]) < 1e-9
            for p in out["nodes"]
        ):
            raise ModelError(
                "Move would overlap another node. Nodes are not automatically merged."
            )
        selection = ("node", nid)
    elif action == "add_member":
        i, j = int(event["i"]), int(event["j"])
        if any({e["i"], e["j"]} == {i, j} for e in out["elements"]):
            raise ModelError("A member already connects these nodes.")
        e = new_member(next_id(out["elements"]), i, j)
        out["elements"].append(e)
        selection = ("element", e["id"])
    else:
        raise ModelError("Unknown canvas editing action.")
    validate(out, draft=True)
    return out, selection
