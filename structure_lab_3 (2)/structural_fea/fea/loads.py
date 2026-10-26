"""Resolve a distance-defined load path into uniform member load patches.

No mesh subdivision is required. Each patch records its exact local limits
and both local components of its physical force per unit member length.
"""

from dataclasses import dataclass
import math
import numpy as np
from .errors import ModelError

DIRECTIONS = ("Global X", "Global Y", "Path normal")


def finite_number(value, label):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ModelError(f"{label} must be a finite number.")
    return float(value)


def positive_id(value, label):
    value = finite_number(value, label)
    if value < 1 or value != int(value):
        raise ModelError(f"{label} must be a positive integer.")
    return int(value)


def path_segments(model, element_ids, start_node):
    """Walk an explicitly ordered, nonbranching path, allowing reversed members."""
    if not isinstance(element_ids, list) or not element_ids:
        raise ModelError("Choose at least one element for the load path.")
    ids = [positive_id(i, "Path element ID") for i in element_ids]
    if len(set(ids)) != len(ids):
        raise ModelError("A load path cannot repeat an element.")
    current = positive_id(start_node, "Path start node")
    elements = {e["id"]: e for e in model["elements"]}
    nodes = {n["id"]: n for n in model["nodes"]}
    walked, visited, offset = [], {current}, 0.0
    for eid in ids:
        if eid not in elements:
            raise ModelError(f"Load path refers to missing element {eid}.")
        e = elements[eid]
        if current not in (e["i"], e["j"]):
            raise ModelError(
                f"Element {eid} does not continue from node {current}. Order path elements end-to-end."
            )
        forward = current == e["i"]
        following = e["j"] if forward else e["i"]
        if following in visited:
            raise ModelError("Closed or self-revisiting load paths are not supported.")
        if e["i"] not in nodes or e["j"] not in nodes:
            raise ModelError(f"Element {eid} refers to a missing node.")
        a, b = nodes[e["i"]], nodes[e["j"]]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        L = math.hypot(dx, dy)
        if not math.isfinite(L) or L <= 1e-9:
            raise ModelError(f"Element {eid} has zero or invalid length.")
        walked.append(
            dict(
                element=eid,
                L=L,
                c=dx / L,
                s=dy / L,
                forward=forward,
                offset=offset,
                node=current,
                next_node=following,
            )
        )
        offset += L
        visited.add(following)
        current = following
    return walked


@dataclass(frozen=True)
class Patch:
    element: int
    a: float
    b: float
    qx: float
    qy: float
    load_id: str
    case: str


def resolve_loads(model, factors=None):
    """Validate all load rows, then resolve physical patches (optionally factored)."""
    loads = model.get("distributed_loads", [])
    if not isinstance(loads, list):
        raise ModelError("distributed_loads must be a list.")
    if model["type"] == "truss" and (loads or model.get("udls")):
        raise ModelError(
            "Distributed member loads require frame/beam mode. Trusses accept joint forces only."
        )
    rows = list(loads)
    # Version-1 models stay readable. Their q is local +y from raw node i to j.
    by_id = {e["id"]: e for e in model["elements"]}
    for index, old in enumerate(model.get("udls", [])):
        if not isinstance(old, dict) or old.get("element") not in by_id:
            raise ModelError("Legacy UDL refers to a missing element.")
        e = by_id[old["element"]]
        rows.append(
            dict(
                id=f"legacy-{index+1}",
                case=old.get("case"),
                elements=[e["id"]],
                start_node=e["i"],
                start=old.get("start", 0.0),
                end=old.get("end"),
                q=old.get("q"),
                direction="Path normal",
            )
        )
    if len(rows) > 500:
        raise ModelError("Use no more than 500 distributed load definitions.")
    seen, patches = set(), []
    for index, load in enumerate(rows):
        if not isinstance(load, dict):
            raise ModelError("Each distributed load must be an object.")
        lid = str(load.get("id", f"load-{index+1}"))
        if not lid.strip() or lid in seen:
            raise ModelError("Distributed load IDs must be nonempty and unique.")
        seen.add(lid)
        if load.get("case") not in model["cases"]:
            raise ModelError(f"Load {lid}: choose an existing load case.")
        if load.get("direction") not in DIRECTIONS:
            raise ModelError(
                f"Load {lid}: direction must be Global X, Global Y or Path normal."
            )
        segments = path_segments(model, load.get("elements"), load.get("start_node"))
        length = sum(s["L"] for s in segments)
        start = finite_number(load.get("start"), f"Load {lid} start")
        end = (
            length
            if load.get("end") is None
            else finite_number(load["end"], f"Load {lid} end")
        )
        if not 0 <= start < end <= length + 1e-10 * max(1, length):
            raise ModelError(
                f"Load {lid}: require 0 ≤ start < end ≤ path length ({length:g} m)."
            )
        end = min(end, length)
        q = finite_number(load.get("q"), f"Load {lid} intensity")
        if factors is not None:
            q *= factors.get(load["case"], 0.0)
        for s in segments:
            a = max(start - s["offset"], 0.0)
            b = min(end - s["offset"], s["L"])
            if b <= a:
                continue
            if not s["forward"]:
                a, b = s["L"] - b, s["L"] - a
            c, sine = s["c"], s["s"]
            if load["direction"] == "Global X":
                qx, qy = q * c, -q * sine
            elif load["direction"] == "Global Y":
                qx, qy = q * sine, q * c
            else:
                qx, qy = 0.0, q * (1 if s["forward"] else -1)
            patches.append(Patch(s["element"], a, b, qx, qy, lid, load["case"]))
    return patches


def equivalent_load(L, patches):
    """Integrate axial linear and bending Hermite shapes over each loaded interval."""
    vector = np.zeros(6)
    points, weights = np.polynomial.legendre.leggauss(3)
    for p in patches:
        x = (points + 1) * (p.b - p.a) / 2 + p.a
        t = x / L
        H = np.array(
            [
                1 - 3 * t * t + 2 * t**3,
                L * (t - 2 * t * t + t**3),
                3 * t * t - 2 * t**3,
                L * (-t * t + t**3),
            ]
        )
        w = weights * (p.b - p.a) / 2
        vector[[0, 3]] += np.array([1 - t, t]) @ w * p.qx
        vector[[1, 2, 4, 5]] += H @ w * p.qy
    return vector


@dataclass(frozen=True)
class Point:
    element: int
    x: float
    px: float
    py: float
    load_id: str
    case: str


def resolve_points(model, factors=None):
    """Resolve member point forces without inserting nodes or changing connectivity."""
    rows = model.get("member_loads", [])
    if not isinstance(rows, list) or len(rows) > 500:
        raise ModelError("member_loads must be a list of at most 500 rows.")
    if rows and model["type"] != "frame":
        raise ModelError("Member point loads require frame/beam mode.")
    nodes = {n["id"]: n for n in model["nodes"]}
    elements = {e["id"]: e for e in model["elements"]}
    seen = set()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ModelError("Each member point load must be an object.")
        lid = str(row.get("id", ""))
        if not lid or lid in seen:
            raise ModelError("Member point load IDs must be nonempty and unique.")
        seen.add(lid)
        eid = positive_id(row.get("element"), "Point load element")
        if eid not in elements:
            raise ModelError("Member point load refers to a missing element.")
        if row.get("case") not in model["cases"]:
            raise ModelError("Member point load has an unknown case.")
        e = elements[eid]
        a, b = nodes[e["i"]], nodes[e["j"]]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        L = math.hypot(dx, dy)
        x = finite_number(row.get("x"), "Point load position")
        if not 0 < x < L:
            raise ModelError(
                f"Point position must be strictly between 0 and {L:g} m. Use a nodal load at an end."
            )
        p = finite_number(row.get("p"), "Point force") * (
            1.0 if factors is None else factors.get(row["case"], 0.0)
        )
        direction = row.get("direction")
        if direction == "Global X":
            px, py = p * dx / L, -p * dy / L
        elif direction == "Global Y":
            px, py = p * dy / L, p * dx / L
        elif direction == "Local X":
            px, py = p, 0.0
        elif direction == "Local Y":
            px, py = 0.0, p
        else:
            raise ModelError("Point direction must be Global X/Y or Local X/Y.")
        result.append(Point(eid, x, px, py, lid, row["case"]))
    return result


def point_equivalent(L, points):
    """Virtual-work consistent point load vector: shape functions at the load."""
    f = np.zeros(6)
    for p in points:
        t = p.x / L
        f[[0, 3]] += p.px * np.array([1 - t, t])
        f[[1, 2, 4, 5]] += p.py * np.array(
            [
                1 - 3 * t * t + 2 * t**3,
                L * (t - 2 * t * t + t**3),
                3 * t * t - 2 * t**3,
                L * (-t * t + t**3),
            ]
        )
    return f
