"""Structural calculations for the student frame-analysis project.

Reading order: element_matrices -> solve -> Element.fields.
The main equation is K @ d = F. K is stiffness, d is displacement and
F is the applied load vector. All calculations use metres, newtons and pascals.
See docs/CODE_WALKTHROUGH.md for a guide through one beam example.
"""

from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
import numpy as np
from numpy.polynomial import Polynomial
from .errors import ModelError
from .loads import resolve_loads, equivalent_load, resolve_points, point_equivalent

# Each support lists restraints in the order (horizontal, vertical, rotation).
# True means that displacement is fixed at zero; False means it is unknown.
SUPPORTS = {
    "Free": (False, False, False),
    "Fixed": (True, True, True),
    "Pinned": (True, True, False),
    "Roller Y": (False, True, False),
    "Roller X": (True, False, False),
    "Rotation only": (False, False, True),
    "X + rotation": (True, False, True),
    "Y + rotation": (False, True, True),
}


def fingerprint(model):
    return hashlib.sha256(
        json.dumps(model, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def validate(model, draft=False):
    """Validate schema, identifiers, connectivity, finite values and load references."""

    def require(test, message):
        if not test:
            raise ModelError(message)

    def number(value, label, positive=False):
        require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{label} must be a number.",
        )
        require(np.isfinite(value), f"{label} must be finite.")
        if positive:
            require(value > 0, f"{label} must be greater than zero.")

    def identifier(value, label):
        require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and np.isfinite(value)
            and value == int(value)
            and value >= 1,
            f"{label} must be a positive integer.",
        )

    require(isinstance(model, dict), "Model must be a JSON object.")
    require(
        model.get("type") in ("frame", "truss"), "Model type must be frame or truss."
    )
    for name in ("nodes", "elements", "cases", "nodal_loads", "udls", "combinations"):
        require(isinstance(model.get(name), list), f"{name} must be a list.")
    nodes, elements, cases = model["nodes"], model["elements"], model["cases"]
    require((0 if draft else 2) <= len(nodes) <= 150, "Analysis requires 2–150 nodes.")
    require(
        (0 if draft else 1) <= len(elements) <= 300, "Analysis requires 1–300 elements."
    )
    require(1 <= len(cases) <= 30, "Use 1–30 load cases.")
    require(
        all(isinstance(c, str) and c.strip() for c in cases),
        "Load cases need nonempty names.",
    )
    require(len(set(cases)) == len(cases), "Load case names must be unique.")
    ids = []
    for n in nodes:
        require(isinstance(n, dict), "Each node must be an object.")
        identifier(n.get("id"), "Node ID")
        ids.append(n["id"])
        number(n.get("x"), "Node x")
        number(n.get("y"), "Node y")
        require(
            isinstance(n.get("support"), str) and n["support"] in SUPPORTS,
            "Choose a valid support for every node.",
        )
        if model["type"] == "truss":
            require(
                n["support"] not in ("Rotation only", "X + rotation", "Y + rotation"),
                "Trusses have no rotational DOFs; choose a translational support.",
            )
    require(len(set(ids)) == len(ids), "Node IDs must be unique.")
    lookup = {n["id"]: n for n in nodes}
    adjacency = {i: set() for i in ids}
    eids = []
    for e in elements:
        require(isinstance(e, dict), "Each element must be an object.")
        identifier(e.get("id"), "Element ID")
        eids.append(e["id"])
        for field in ("i", "j"):
            identifier(e.get(field), f"Element {field}")
            require(e[field] in lookup, f'Element {e["id"]} refers to a missing node.')
        a, b = lookup[e["i"]], lookup[e["j"]]
        require(
            np.hypot(b["x"] - a["x"], b["y"] - a["y"]) > 1e-9,
            f'Element {e["id"]} has zero or negligible length.',
        )
        for field in ("E", "A") + (("I",) if model["type"] == "frame" else ()):
            number(e.get(field), f'Element {e["id"]}: {field}', True)
        for key in ("release_i", "release_j", "buckling_enabled"):
            require(
                isinstance(e.get(key, False), bool),
                f'Element {e["id"]}: {key} must be true or false.',
            )
        for key in (
            "fy",
            "density",
            "c_top",
            "c_bottom",
            "effective_length_factor",
            "buckling_length",
        ):
            if key in e and e[key] is not None:
                number(e[key], f'Element {e["id"]}: {key}', True)
        if "material" in e:
            require(
                e["material"] in ("Steel", "Other elastic"),
                "Material must be Steel or Other elastic.",
            )
        if "section_shape" in e:
            require(
                e["section_shape"]
                in ("Rectangle", "Circle", "Hollow rectangle", "I section", "Custom"),
                "Invalid section shape.",
            )
        if "section_dimensions" in e:
            require(
                isinstance(e["section_dimensions"], dict),
                "Section dimensions must be an object.",
            )
            for key, value in e["section_dimensions"].items():
                number(value, f"Section dimension {key}", True)
        require(
            bool(e.get("c_top")) == bool(e.get("c_bottom")),
            "Specify both extreme-fibre distances or neither.",
        )
        if model["type"] == "truss":
            require(
                not e.get("release_i") and not e.get("release_j"),
                "Truss elements have no moment releases.",
            )
        adjacency[e["i"]].add(e["j"])
        adjacency[e["j"]].add(e["i"])
    require(len(set(eids)) == len(eids), "Element IDs must be unique.")
    if not draft:
        isolated = [i for i, neighbours in adjacency.items() if not neighbours]
        require(
            not isolated, f"Disconnected nodes: {isolated}. Connect or remove them."
        )
        seen, todo = set(), [ids[0]]
        while todo:
            item = todo.pop()
            if item not in seen:
                seen.add(item)
                todo.extend(adjacency[item] - seen)
        require(
            len(seen) == len(ids),
            "Separate disconnected structures detected. Analyse them as separate models.",
        )
    for load in model["nodal_loads"]:
        require(isinstance(load, dict), "Each nodal load must be an object.")
        require(load.get("case") in cases, "Nodal load has an unknown load case.")
        identifier(load.get("node"), "Loaded node")
        require(load["node"] in lookup, "Nodal load refers to a missing node.")
        for field in ("fx", "fy", "mz"):
            number(load.get(field), f"Nodal load {field}")
        require(
            model["type"] != "truss" or load["mz"] == 0,
            "Trusses cannot carry nodal moments.",
        )
    require(
        model["type"] != "truss" or not model["udls"],
        "UDLs are supported only by frame elements.",
    )
    for load in model["udls"]:
        require(isinstance(load, dict), "Each UDL must be an object.")
        require(load.get("case") in cases, "UDL has an unknown load case.")
        identifier(load.get("element"), "Loaded element")
        require(load["element"] in eids, "UDL refers to a missing element.")
        number(load.get("q"), "UDL q")
    for combo in model["combinations"]:
        require(isinstance(combo, dict), "Each combination term must be an object.")
        require(
            isinstance(combo.get("name"), str) and bool(combo["name"].strip()),
            "Combination names cannot be blank.",
        )
        require(combo["name"] not in cases, "Combination and case names must differ.")
        require(combo.get("case") in cases, "Combination references an unknown case.")
        number(combo.get("factor"), "Combination factor")
    resolve_loads(model)
    resolve_points(model)
    if "deflection_limit" in model:
        number(model["deflection_limit"], "Translation limit [m]", True)
    return model


def factors_for(model, name):
    if name in model["cases"]:
        return {name: 1.0}
    terms = [row for row in model["combinations"] if row["name"] == name]
    if not terms:
        raise ModelError("Select an existing load case or combination.")
    factors = {}
    for row in terms:
        factors[row["case"]] = factors.get(row["case"], 0.0) + row["factor"]
    return factors


def load_names(model):
    return model["cases"] + list(
        dict.fromkeys(r["name"] for r in model["combinations"])
    )


@dataclass
class Element:
    id: int
    i: int
    j: int
    origin: np.ndarray
    L: float
    c: float
    s: float
    E: float
    A: float
    I: float
    k: np.ndarray
    T: np.ndarray
    dofs: np.ndarray
    patches: list
    equivalent: np.ndarray
    displacement: np.ndarray | None = None
    end_forces: np.ndarray | None = None
    points: list = field(default_factory=list)
    released: list = field(default_factory=list)
    condensed_k: np.ndarray | None = None
    condensed_load: np.ndarray | None = None

    @property
    def breakpoints(self):
        return sorted(
            {
                0.0,
                self.L,
                *(p.a for p in self.patches),
                *(p.b for p in self.patches),
                *(p.x for p in self.points),
            }
        )

    def fields(self, x):
        """Exact piecewise member response from equilibrium and integrated curvature.

        Brackets <x-a> = max(x-a, 0) start/stop uniform loading at its
        actual boundaries. No fictitious mesh nodes are added.
        """
        x = np.asarray(x, dtype=float)
        d, f = self.displacement, self.end_forces
        if len(d) == 4:
            t = x / self.L
            return (
                (1 - t) * d[0] + t * d[2],
                (1 - t) * d[1] + t * d[3],
                np.full_like(x, -f[0]),
                np.zeros_like(x),
                np.zeros_like(x),
            )
        N = np.full_like(x, -f[0])
        V = np.full_like(x, f[1])
        M = -f[2] + f[1] * x
        u = d[0] - f[0] * x / (self.E * self.A)
        v = d[1] + d[2] * x + (-f[2] * x * x / 2 + f[1] * x**3 / 6) / (self.E * self.I)
        for p in self.patches:
            a, b = np.maximum(x - p.a, 0), np.maximum(x - p.b, 0)
            N -= p.qx * (a - b)
            V += p.qy * (a - b)
            M += p.qy * (a * a - b * b) / 2
            u -= p.qx * (a * a - b * b) / (2 * self.E * self.A)
            v += p.qy * (a**4 - b**4) / (24 * self.E * self.I)
        for p in self.points:
            a = np.maximum(x - p.x, 0)
            step = (x >= p.x).astype(float)
            N -= p.px * step
            V += p.py * step
            M += p.py * a
            u -= p.px * a / (self.E * self.A)
            v += p.py * a**3 / (6 * self.E * self.I)
        return u, v, N, V, M

    def polynomials(self, left):
        """Displacement/force polynomials on an interval, argument x-left."""
        x = Polynomial([left, 1.0])
        d, f = self.displacement, self.end_forces
        u = d[0] - f[0] * x / (self.E * self.A)
        v = d[1] + d[2] * x + (-f[2] * x * x / 2 + f[1] * x**3 / 6) / (self.E * self.I)
        N = Polynomial([-f[0]])
        M = -f[2] + f[1] * x
        for p in self.patches:
            a = x - p.a if left >= p.a else Polynomial([0.0])
            b = x - p.b if left >= p.b else Polynomial([0.0])
            N -= p.qx * (a - b)
            u -= p.qx * (a * a - b * b) / (2 * self.E * self.A)
            M += p.qy * (a * a - b * b) / 2
            v += p.qy * (a**4 - b**4) / (24 * self.E * self.I)
        for p in self.points:
            if left >= p.x:
                a = x - p.x
                N -= p.px
                u -= p.px * a / (self.E * self.A)
                M += p.py * a
                v += p.py * a**3 / (6 * self.E * self.I)
        return u, v, N, M

    def critical_points(self, fibres=None):
        """Exact polynomial extrema, including both sides of point-force jumps."""
        if len(self.displacement) == 4:
            return np.array([0.0, self.L])
        points = set(self.breakpoints)
        for p in self.points:
            points.add(float(np.nextafter(p.x, 0.0)))
        for left, right in zip(self.breakpoints[:-1], self.breakpoints[1:]):
            u, v, N, M = self.polynomials(left)
            derivatives = [
                u.deriv(),
                v.deriv(),
                u * u.deriv() + v * v.deriv(),
                M.deriv(),
                N.deriv(),
            ]
            if fibres:
                derivatives += [(N / self.A - M * y / self.I).deriv() for y in fibres]
            for derivative in derivatives:
                for root in derivative.roots():
                    if abs(root.imag) < 1e-8 and 0 < root.real < right - left:
                        points.add(float(left + root.real))
        return np.array(sorted(points))

    def stations(self, count=201):
        return np.unique(np.r_[np.linspace(0, self.L, count), self.critical_points()])


def condense_releases(k, f, released):
    """Static condensation of independent member-end rotations (zero end moment).

    Both stiffness and equivalent load must be condensed. Original k/f remain
    available to recover the released rotation after solving joint movements.
    """
    if not released:
        return k.copy(), f.copy()
    retained = [i for i in range(6) if i not in released]
    rr = np.ix_(released, released)
    ar = np.ix_(retained, released)
    ra = np.ix_(released, retained)
    kc = np.zeros_like(k)
    fc = np.zeros_like(f)
    kc[np.ix_(retained, retained)] = k[np.ix_(retained, retained)] - k[
        ar
    ] @ np.linalg.solve(k[rr], k[ra])
    fc[retained] = f[retained] - k[ar] @ np.linalg.solve(k[rr], f[released])
    return kc, fc


def element_matrices(E, A, I, L, c, s, kind):
    """Build one member's stiffness and coordinate transformation.

    E = Young's modulus, A = area, I = second moment of area, L = length.
    c and s are cos(angle) and sin(angle), calculated from the node positions.
    Frame DOF order is [u_i, v_i, rotation_i, u_j, v_j, rotation_j].
    k relates local end movement to local end force; T converts global
    movement into those local directions: d_local = T @ d_global.
    """
    R = np.array([[c, s], [-s, c]])
    if kind == "truss":
        k = (
            E
            * A
            / L
            * np.array(
                [[1, 0, -1, 0], [0, 0, 0, 0], [-1, 0, 1, 0], [0, 0, 0, 0]], float
            )
        )
        T = np.zeros((4, 4))
        T[:2, :2] = R
        T[2:, 2:] = R
    else:
        a, b, h, d, e = (
            E * A / L,
            12 * E * I / L**3,
            6 * E * I / L**2,
            4 * E * I / L,
            2 * E * I / L,
        )
        k = np.array(
            [
                [a, 0, 0, -a, 0, 0],
                [0, b, h, 0, -b, h],
                [0, h, d, 0, -h, e],
                [-a, 0, 0, a, 0, 0],
                [0, -b, -h, 0, b, -h],
                [0, h, e, 0, -h, d],
            ],
            float,
        )
        block = np.eye(3)
        block[:2, :2] = R
        T = np.zeros((6, 6))
        T[:3, :3] = block
        T[3:, 3:] = block
    return k, T


@dataclass
class Result:
    model: dict
    name: str
    K: np.ndarray
    F: np.ndarray
    d: np.ndarray
    reactions: np.ndarray
    elements: list
    fixed: np.ndarray
    energy: float
    scaled_condition: float
    inactive_rotations: list = field(default_factory=list)

    @property
    def dof_labels(self):
        return [
            f'{int(n["id"])}:{axis}'
            for n in self.model["nodes"]
            for axis in (
                ("ux", "uy", "rz") if self.model["type"] == "frame" else ("ux", "uy")
            )
        ]

    def max_displacement(self):
        """Maximum translation from member boundaries and stationary points."""
        return max(
            float(np.max(np.hypot(*e.fields(e.critical_points())[:2])))
            for e in self.elements
        )

    def equilibrium(self):
        """Global force/moment balance, including equivalent UDL loads."""
        nd = 3 if self.model["type"] == "frame" else 2
        total = (self.F + self.reactions).reshape(-1, nd)
        moment = sum(
            n["x"] * f[1] - n["y"] * f[0] + (f[2] if nd == 3 else 0)
            for n, f in zip(self.model["nodes"], total)
        )
        return np.array([total[:, 0].sum(), total[:, 1].sum(), moment])


def solve(model, name=None):
    """Solve one load case or combination in five main stages.

    1. Check the model and calculate member geometry.
    2. Add each transformed member stiffness/load to the global system.
    3. Apply supports and check that the remaining structure is stable.
    4. Solve for the unknown displacements, then calculate reactions.
    5. Recover member forces, curved deflection and strain energy.
    """
    validate(model)
    model = deepcopy(model)
    name = name or model["cases"][0]
    factors = factors_for(model, name)
    nd = 3 if model["type"] == "frame" else 2
    nodes = model["nodes"]
    index = {n["id"]: i for i, n in enumerate(nodes)}
    size = nd * len(nodes)
    K, F = np.zeros((size, size)), np.zeros(size)
    for p in model["nodal_loads"]:
        start = nd * index[p["node"]]
        F[start : start + nd] += factors.get(p["case"], 0) * np.array(
            [p["fx"], p["fy"], p["mz"]][:nd]
        )
    patches = resolve_loads(model, factors)
    points = resolve_points(model, factors)
    elements = []
    for raw in model["elements"]:
        i, j = index[raw["i"]], index[raw["j"]]
        a, b = nodes[i], nodes[j]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        L = float(np.hypot(dx, dy))
        c, s = dx / L, dy / L
        E, A, I = raw["E"], raw["A"], raw.get("I", 0) if nd == 3 else 0
        k, T = element_matrices(E, A, I, L, c, s, model["type"])
        dofs = np.r_[np.arange(nd * i, nd * (i + 1)), np.arange(nd * j, nd * (j + 1))]
        local_patches = [p for p in patches if p.element == raw["id"]]
        fe = equivalent_load(L, local_patches) if nd == 3 else np.zeros(4)
        local_points = [p for p in points if p.element == raw["id"]]
        if nd == 3:
            fe += point_equivalent(L, local_points)
        released = ([2] if raw.get("release_i") else []) + (
            [5] if raw.get("release_j") else []
        )
        kc, fc = condense_releases(k, fe, released)
        K[np.ix_(dofs, dofs)] += T.T @ kc @ T
        F[dofs] += T.T @ fc
        elements.append(
            Element(
                raw["id"],
                raw["i"],
                raw["j"],
                np.array([a["x"], a["y"]]),
                L,
                c,
                s,
                E,
                A,
                I,
                k,
                T,
                dofs,
                local_patches,
                fe,
                points=local_points,
                released=released,
                condensed_k=kc,
                condensed_load=fc,
            )
        )
    if not np.all(np.isfinite(K)) or not np.all(np.isfinite(F)):
        raise ModelError(
            "Nonfinite stiffness or loads: check units and numerical magnitudes."
        )
    fixed = np.array(
        [
            nd * i + j
            for i, n in enumerate(nodes)
            for j, r in enumerate(SUPPORTS[n["support"]][:nd])
            if r
        ],
        int,
    )
    # A joint rotation with every incident member released is not a physical
    # unknown. Exclude only these topologically identified orphan rotations;
    # never drop a translation or use numerical zero filtering to hide a mechanism.
    inactive = []
    if nd == 3:
        for i, n in enumerate(nodes):
            attached = [
                (e, 2 if e.i == n["id"] else 5)
                for e in elements
                if n["id"] in (e.i, e.j)
            ]
            if (
                attached
                and all(end in e.released for e, end in attached)
                and 3 * i + 2 not in fixed
            ):
                if abs(F[3 * i + 2]) > 1e-10:
                    raise ModelError(
                        f'Node {n["id"]}: moment applied to an unrestrained rotation with all ends released.'
                    )
                inactive.append(3 * i + 2)
    free = np.setdiff1d(np.arange(size), np.r_[fixed, inactive])
    d = np.zeros(size)
    condition = 1.0
    if len(free):
        Kr = K[np.ix_(free, free)]
        diagonal = np.diag(Kr)
        labels = [f'node {nodes[i//nd]["id"]} {("ux","uy","rz")[i%nd]}' for i in free]
        if np.any(diagonal <= 0):
            bad = ", ".join(labels[i] for i in np.where(diagonal <= 0)[0][:5])
            raise ModelError(
                f"Unrestrained mechanism: no stiffness at {bad}. Check supports and connectivity."
            )
        scale = 1 / np.sqrt(diagonal)
        scaled = scale[:, None] * Kr * scale[None, :]
        values, vectors = np.linalg.eigh(scaled)
        if values[0] <= 1e-12 * values[-1]:
            critical = np.argsort(np.abs(vectors[:, 0]))[-3:][::-1]
            raise ModelError(
                "Unstable or severely ill-conditioned structure. Dominant free DOFs: "
                + ", ".join(labels[i] for i in critical)
                + ". Check rigid-body motion, truss mechanisms and stiffness contrasts."
            )
        condition = float(values[-1] / values[0])
        try:
            d[free] = scale * np.linalg.solve(scaled, scale * F[free])
        except np.linalg.LinAlgError as exc:
            raise ModelError(
                "Stiffness solution failed; check the restraints and geometry."
            ) from exc
    residual = K @ d - F
    reactions = np.zeros(size)
    reactions[fixed] = residual[fixed]
    if not np.all(np.isfinite(d)):
        raise ModelError("Nonfinite solution. Check numerical input magnitudes.")
    energy = 0.0
    gx, gw = np.polynomial.legendre.leggauss(5)
    for e in elements:
        e.displacement = e.T @ d[e.dofs]
        if e.released:
            retained = [i for i in range(6) if i not in e.released]
            e.displacement[e.released] = np.linalg.solve(
                e.k[np.ix_(e.released, e.released)],
                e.equivalent[e.released]
                - e.k[np.ix_(e.released, retained)] @ e.displacement[retained],
            )
        e.end_forces = e.k @ e.displacement - e.equivalent
        # Split at all load boundaries: a single quadrature interval is not
        # exact for piecewise forces and would give incorrect strain energy.
        for left, right in zip(e.breakpoints[:-1], e.breakpoints[1:]):
            _, _, N, _, M = e.fields(left + (gx + 1) * (right - left) / 2)
            integrand = N * N / (e.E * e.A)
            if nd == 3:
                integrand += M * M / (e.E * e.I)
            energy += float(np.dot(gw, integrand) * (right - left) / 4)
    if not np.isfinite(energy):
        raise ModelError("Nonfinite strain energy: check numerical magnitudes.")
    return Result(
        model, name, K, F, d, reactions, elements, fixed, energy, condition, inactive
    )


def parameter_study(model, name, property_name, element_ids, multipliers):
    if property_name not in ("E", "A", "I"):
        raise ModelError("Study property must be E, A or I.")
    if model["type"] == "truss" and property_name == "I":
        raise ModelError("Truss stiffness does not depend on I.")
    if not set(element_ids).issubset({e["id"] for e in model["elements"]}):
        raise ModelError("Parameter study contains a missing element.")
    if not element_ids:
        raise ModelError("Select at least one element for the study.")
    records = []
    for factor in multipliers:
        if not np.isfinite(factor) or factor <= 0:
            raise ModelError("Study multipliers must be positive and finite.")
        changed = deepcopy(model)
        for e in changed["elements"]:
            if e["id"] in element_ids:
                e[property_name] *= float(factor)
        r = solve(changed, name)
        records.append(
            {
                "multiplier": float(factor),
                "max_displacement_m": r.max_displacement(),
                "strain_energy_J": r.energy,
            }
        )
    return records
