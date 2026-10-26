"""Independent closed-form checks for exact load patches and connected paths."""

from copy import deepcopy
import numpy as np
import pytest
from fea.examples import examples, node, element
from fea.solver import solve, validate, ModelError
from fea.loads import equivalent_load, Patch


def beam(a=0.0, b=None, q=-10000.0):
    m = examples()["Simply supported beam"]
    m["udls"] = []
    m["distributed_loads"] = [
        dict(
            id="D1",
            case="Dead",
            elements=[1],
            start_node=1,
            start=a,
            end=b,
            q=q,
            direction="Global Y",
        )
    ]
    return m


def close(a, b):
    np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-8)


def analytical(x, L, a, b, w, EI):
    RA = w * (b - a) * (1 - (a + b) / (2 * L))
    c1 = -(RA * L**3 / 6 - w * ((L - a) ** 4 - (L - b) ** 4) / 24) / L
    x = np.asarray(x)
    pa = np.maximum(x - a, 0)
    pb = np.maximum(x - b, 0)
    return (
        RA,
        w * (b - a) - RA,
        RA - w * (pa - pb),
        RA * x - w * (pa**2 - pb**2) / 2,
        (RA * x**3 / 6 - w * (pa**4 - pb**4) / 24 + c1 * x) / EI,
    )


@pytest.mark.parametrize("a,b", [(0, 6), (0, 3), (1, 4.5), (2, 4), (4.9, 5.1)])
def test_patch_analytical(a, b):
    r = solve(beam(a, b), "Dead")
    e = r.elements[0]
    x = np.linspace(0, 6, 81)
    RA, RB, V, M, v = analytical(x, 6, a, b, 10000, e.E * e.I)
    actual = e.fields(x)
    close(r.reactions[[1, 4]], [RA, RB])
    close(actual[3], V)
    close(actual[4], M)
    close(actual[1], v)
    close(r.equilibrium(), 0)
    close(e.fields([0, 6])[1], [0, 0])
    dense = analytical(np.linspace(0, 6, 100001), 6, a, b, 10000, e.E * e.I)[4]
    assert r.max_displacement() == pytest.approx(np.max(np.abs(dense)), rel=1e-8)


def test_full_span_maxima():
    r = solve(beam(), "Dead")
    e = r.elements[0]
    close(r.reactions[[1, 4]], [30000, 30000])
    close(max(e.fields(e.critical_points())[4]), 45000)
    close(r.max_displacement(), 5 * 10000 * 6**4 / (384 * e.E * e.I))


def test_multi_element_reversed_connectivity():
    one = beam(0.7, 5.2)
    r1 = solve(one, "Dead")
    m = deepcopy(one)
    m["nodes"] = [
        node(1, 0, 0, "Pinned"),
        node(2, 2, 0),
        node(3, 4, 0),
        node(4, 6, 0, "Roller Y"),
    ]
    m["elements"] = [element(1, 1, 2), element(2, 3, 2), element(3, 3, 4)]
    m["distributed_loads"][0]["elements"] = [1, 2, 3]
    rs = solve(m, "Dead")
    close(rs.reactions[[1, 10]], r1.reactions[[1, 4]])
    close(rs.energy, r1.energy)
    close(rs.max_displacement(), r1.max_displacement())
    for e in rs.elements:
        x = e.stations()
        u, v, N, V, M = e.fields(x)
        expected = r1.elements[0].fields(e.origin[0] + e.c * x)
        close(e.c * v, expected[1])
        close(e.c * M, expected[4])


def test_partial_cantilever():
    m = examples()["Cantilever"]
    m["udls"] = []
    m["nodal_loads"] = []
    m["distributed_loads"] = [
        dict(
            id="P",
            case="Dead",
            elements=[1],
            start_node=1,
            start=1,
            end=3,
            q=-1000,
            direction="Global Y",
        )
    ]
    r = solve(m, "Dead")
    e = r.elements[0]
    # Tip displacement influence function z²(3L-z)/(6EI), integrated from 1 to 3.
    primitive = lambda z: e.L * z**3 - z**4 / 4
    close(r.d[4], -1000 * (primitive(3) - primitive(1)) / (6 * e.E * e.I))
    close(r.reactions[:3], [0, 2000, 4000])


def test_overlapping_patches_and_combinations():
    m = beam(1, 5)
    m["distributed_loads"].append(
        dict(
            id="D2",
            case="Live",
            elements=[1],
            start_node=1,
            start=2,
            end=4,
            q=-3000,
            direction="Global Y",
        )
    )
    m["combinations"] = [
        dict(name="Mixed", case="Dead", factor=1.5),
        dict(name="Mixed", case="Live", factor=-0.4),
    ]
    a, b, c = [solve(m, name) for name in ["Dead", "Live", "Mixed"]]
    close(c.d, 1.5 * a.d - 0.4 * b.d)
    for actual, v1, v2 in zip(
        c.elements[0].fields(np.linspace(0, 6, 100)),
        a.elements[0].fields(np.linspace(0, 6, 100)),
        b.elements[0].fields(np.linspace(0, 6, 100)),
    ):
        close(actual, 1.5 * v1 - 0.4 * v2)


def test_inclined_global_direction_keeps_axial_load():
    m = examples()["Cantilever"]
    m["nodes"][1].update(x=3.0, y=4.0)
    m["udls"] = []
    m["nodal_loads"] = []
    m["distributed_loads"] = [
        dict(
            id="G",
            case="Dead",
            elements=[1],
            start_node=1,
            start=0,
            end=None,
            q=-1000,
            direction="Global Y",
        )
    ]
    r = solve(m, "Dead")
    e = r.elements[0]
    close([e.patches[0].qx, e.patches[0].qy], [-800, -600])
    close(r.reactions[:3], [0, 5000, 7500])
    close(r.equilibrium(), 0)
    u, v, N, V, M = e.fields([5])
    close(u, [-800 * 25 / (2 * e.E * e.A)])
    close(v, [-600 * 625 / (8 * e.E * e.I)])
    close([N[0], V[0], M[0]], [0, 0, 0])


def test_normal_direction_and_reversed_member():
    m = beam(1, 4)
    m["distributed_loads"][0].update(direction="Path normal", q=-1000)
    r = solve(m, "Dead")
    m["elements"][0].update(i=2, j=1)
    close(r.d, solve(m, "Dead").d)
    m["distributed_loads"][0].update(start_node=2, start=2, end=5, q=1000)
    close(r.d, solve(m, "Dead").d)


def test_consistent_vector_resultants_and_work():
    p = Patch(1, 1, 4, 123, -456, "x", "Dead")
    L = 6
    f = equivalent_load(L, [p])
    close(f[0] + f[3], 123 * 3)
    close(f[1] + f[4], -456 * 3)
    close(f[2] + f[5] + L * f[4], -456 * 3 * 2.5)
    d = np.array([0.1, 0.3, 0.02, 0.2, -0.1, -0.03])
    x = np.linspace(1, 4, 20001)
    t = x / L
    u = (1 - t) * d[0] + t * d[3]
    v = (
        (1 - 3 * t * t + 2 * t**3) * d[1]
        + L * (t - 2 * t * t + t**3) * d[2]
        + (3 * t * t - 2 * t**3) * d[4]
        + L * (-t * t + t**3) * d[5]
    )
    assert float(f @ d) == pytest.approx(
        (np.trapezoid if hasattr(np, "trapezoid") else np.trapz)(123 * u - 456 * v, x),
        rel=1e-8,
    )


def test_energy_external_work():
    r = solve(beam(1.1, 4.7), "Dead")
    x = np.linspace(1.1, 4.7, 20001)
    assert r.energy == pytest.approx(
        0.5
        * (np.trapezoid if hasattr(np, "trapezoid") else np.trapz)(
            -10000 * r.elements[0].fields(x)[1], x
        ),
        rel=1e-8,
    )


@pytest.mark.parametrize(
    "edit",
    [
        {"start": 4, "end": 2},
        {"start": -1},
        {"end": 7},
        {"start": 2, "end": 2},
        {"elements": [99]},
        {"elements": [1, 1]},
        {"start_node": 99},
        {"direction": "bad"},
        {"q": float("nan")},
        {"case": "missing"},
        {"elements": []},
    ],
)
def test_invalid_patch(edit):
    m = beam()
    m["distributed_loads"][0].update(edit)
    with pytest.raises(ModelError):
        solve(m)


def test_truss_and_draft_restrictions():
    m = examples()["Triangular truss"]
    m["distributed_loads"] = beam()["distributed_loads"]
    with pytest.raises(ModelError, match="frame/beam"):
        solve(m)
    m = beam()
    m["nodes"].append(node(9, 10, 10))
    validate(m, draft=True)
    with pytest.raises(ModelError, match="Disconnected"):
        solve(m)
