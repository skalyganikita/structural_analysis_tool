"""Independent analytical checks: rtol 1e-9; near-zero force balance atol 1e-7."""

from copy import deepcopy
import numpy as np
import pytest
from fea.examples import examples, base, node, element
from fea.solver import solve, ModelError, parameter_study, validate


def close(actual, expected, atol=1e-9):
    np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=atol)


def test_cantilever_tip_force():
    m = examples()["Cantilever"]
    r = solve(m, "Live")
    e = r.elements[0]
    P, L, E, I = 20000, 4, e.E, e.I
    close(r.d[4], -P * L**3 / (3 * E * I))
    close(r.d[5], -P * L**2 / (2 * E * I))
    close(r.reactions[:3], [0, P, P * L])
    close(e.fields(np.array([0, L]))[4], [-P * L, 0])
    close(r.energy, P**2 * L**3 / (6 * E * I))
    close(
        e.fields(np.array([L / 2]))[1],
        [-P * (L / 2) ** 2 * (3 * L - L / 2) / (6 * E * I)],
    )


def test_simply_supported_udl():
    r = solve(examples()["Simply supported beam"], "Dead")
    e = r.elements[0]
    w, L, E, I = 10000, 6, e.E, e.I
    close(r.reactions[[1, 4]], [w * L / 2] * 2)
    u, v, N, V, M = e.fields(np.array([0, L / 2, L]))
    close(v, [0, -5 * w * L**4 / (384 * E * I), 0])
    close(M, [0, w * L**2 / 8, 0], atol=1e-7)
    close(V, [w * L / 2, 0, -w * L / 2])
    close(r.energy, w * w * L**5 / (240 * E * I))


def test_fixed_fixed_udl_bubble_and_energy():
    m = examples()["Simply supported beam"]
    for n in m["nodes"]:
        n["support"] = "Fixed"
    r = solve(m, "Dead")
    e = r.elements[0]
    w, L = 10000, 6
    close(r.d, 0)
    close(e.fields(np.array([L / 2]))[1], [-w * L**4 / (384 * e.E * e.I)])
    close(
        e.fields(np.array([0, L / 2, L]))[4],
        [-w * L**2 / 12, w * L**2 / 24, -w * L**2 / 12],
    )
    close(r.energy, w * w * L**5 / (1440 * e.E * e.I))


def test_axial_bar():
    m = base("truss")
    m["nodes"] = [node(1, 0, 0, "Pinned"), node(2, 3, 0, "Roller Y")]
    m["elements"] = [element(1, 1, 2)]
    m["nodal_loads"] = [dict(case="Dead", node=2, fx=10000, fy=0, mz=0)]
    r = solve(m, "Dead")
    close(r.d[2], 10000 * 3 / (210e9 * 0.01))
    close(r.reactions[0], -10000)
    close(r.elements[0].fields(np.array([1.5]))[2], [10000])


def test_triangle_truss_hand_solution():
    m = examples()["Triangular truss"]
    r = solve(m, "Dead")
    P = 10000
    L = np.sqrt(13)
    expected = [P / 3, -P * L / 6, -P * L / 6]
    close([e.fields(np.array([0]))[2][0] for e in r.elements], expected)
    close(r.reactions[[1, 3]], [P / 2, P / 2])
    # Castigliano: vertical deflection = sum(N^2 L / EA) / P.
    expected_v = -(expected[0] ** 2 * 4 + 2 * expected[1] ** 2 * L) / (
        210e9 * 0.002 * P
    )
    close(r.d[5], expected_v)


@pytest.mark.parametrize("name", list(examples()))
@pytest.mark.parametrize("load", ["Dead", "Live", "Service"])
def test_global_equilibrium(name, load):
    r = solve(examples()[name], load)
    close(r.equilibrium(), [0, 0, 0], atol=1e-7)
    close(r.K, r.K.T, atol=1e-7)


def test_combinations_superpose_and_energy_scales():
    m = examples()["Portal frame"]
    a, b, c = [solve(m, k) for k in ["Dead", "Live", "Service"]]
    close(c.d, a.d + b.d)
    close(c.reactions, a.reactions + b.reactions, atol=1e-7)
    m["combinations"] = [dict(name="Double", case="Dead", factor=2)]
    d = solve(m, "Double")
    close(d.energy, 4 * a.energy)


def test_rotation_invariance():
    m = examples()["Cantilever"]
    r = solve(m, "Service")
    angle = 0.61
    Q = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    for n in m["nodes"]:
        n["x"], n["y"] = (Q @ np.array([n["x"], n["y"]])).tolist()
    for p in m["nodal_loads"]:
        p["fx"], p["fy"] = (Q @ np.array([p["fx"], p["fy"]])).tolist()
    rotated = solve(m, "Service")
    close(rotated.d.reshape(-1, 3)[:, :2], r.d.reshape(-1, 3)[:, :2] @ Q.T)
    close(rotated.energy, r.energy)
    close(rotated.elements[0].end_forces, r.elements[0].end_forces, atol=1e-7)


def test_parameter_study_inverse_E():
    m = examples()["Cantilever"]
    rows = parameter_study(m, "Service", "E", [1], [0.5, 1, 2])
    close(
        [r["max_displacement_m"] for r in rows],
        np.array([2, 1, 0.5]) * rows[1]["max_displacement_m"],
    )


@pytest.mark.parametrize(
    "failure",
    [
        "free",
        "length",
        "missing",
        "isolated",
        "negative",
        "nan",
        "duplicate",
        "moment",
        "mechanism",
    ],
)
def test_rejects_invalid_or_unstable_models(failure):
    m = examples()["Triangular truss"]
    if failure == "free":
        for n in m["nodes"]:
            n["support"] = "Free"
    elif failure == "length":
        m["nodes"][1].update(x=0, y=0)
    elif failure == "missing":
        m["elements"][0]["j"] = 99
    elif failure == "isolated":
        m["nodes"].append(node(4, 9, 9))
    elif failure == "negative":
        m["elements"][0]["E"] = -1
    elif failure == "nan":
        m["nodes"][0]["x"] = float("nan")
    elif failure == "duplicate":
        m["nodes"][1]["id"] = 1
    elif failure == "moment":
        m["nodal_loads"][0]["mz"] = 1
    elif failure == "mechanism":
        m["elements"] = m["elements"][1:]
    with pytest.raises(ModelError):
        solve(m)


def test_multiple_element_beam_matches_single():
    m = examples()["Simply supported beam"]
    single = solve(m, "Dead")
    m["nodes"] = [node(1, 0, 0, "Pinned"), node(2, 3, 0), node(3, 6, 0, "Roller Y")]
    m["elements"] = [element(1, 1, 2), element(2, 2, 3)]
    m["udls"] = [dict(case="Dead", element=e, q=-10000) for e in [1, 2]]
    split = solve(m, "Dead")
    close(split.d[4], single.elements[0].fields(np.array([3]))[1][0])
    close(split.energy, single.energy)


def test_nodal_moment_cantilever():
    m = examples()["Cantilever"]
    m["nodal_loads"] = [dict(case="Live", node=2, fx=0, fy=0, mz=10000)]
    r = solve(m, "Live")
    e = r.elements[0]
    close(r.d[4], 10000 * e.L**2 / (2 * e.E * e.I))
    close(r.d[5], 10000 * e.L / (e.E * e.I))
    close(e.fields(np.linspace(0, e.L, 9))[4], 10000)
