"""Independent verification of member point loads, releases and screening checks."""

from copy import deepcopy
import numpy as np
import pytest
from fea.examples import examples
from fea.solver import solve, ModelError
from fea.sections import section_properties
from fea.assessment import assess


def beam():
    m = examples()["Simply supported beam"]
    m["udls"] = []
    m["distributed_loads"] = []
    m["nodal_loads"] = []
    return m


def close(a, b):
    np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-7)


@pytest.mark.parametrize("a", [1.0, 3.0, 4.8])
def test_point_beam(a):
    m = beam()
    L = 6.0
    P = 12000.0
    b = L - a
    m["member_loads"] = [
        dict(id="P", element=1, case="Dead", x=a, p=-P, direction="Global Y")
    ]
    r = solve(m, "Dead")
    e = r.elements[0]
    close(r.reactions[[1, 4]], [P * b / L, P * a / L])
    close(r.equilibrium(), 0)
    x = np.linspace(0, L, 151)
    v = np.where(
        x <= a,
        -P * b * x / (6 * L * e.E * e.I) * (L * L - b * b - x * x),
        -P * a * (L - x) / (6 * L * e.E * e.I) * (L * L - a * a - (L - x) ** 2),
    )
    close(e.fields(x)[1], v)
    close(e.fields([a])[4], P * a * b / L)
    close(e.fields([np.nextafter(a, 0), a])[3], [P * b / L, -P * a / L])


@pytest.mark.parametrize("releases", [(True, False), (False, True), (True, True)])
def test_released_supported_beam(releases):
    m = examples()["Simply supported beam"]
    m["elements"][0].update(release_i=releases[0], release_j=releases[1])
    r = solve(m, "Dead")
    e = r.elements[0]
    close(r.reactions[[1, 4]], [30000, 30000])
    close(e.end_forces[[2, 5]], 0)
    close(e.fields([3])[1], [-5 * 10000 * 6**4 / (384 * e.E * e.I)])
    close(e.fields([3])[4], [45000])
    close(r.equilibrium(), 0)


def test_fixed_support_member_release():
    m = examples()["Simply supported beam"]
    m["nodes"][0]["support"] = "Fixed"
    m["elements"][0]["release_i"] = True
    r = solve(m, "Dead")
    close(r.reactions[2], 0)
    close(r.elements[0].end_forces[2], 0)
    assert abs(r.elements[0].displacement[2]) > 0
    close(r.d[2], 0)  # support and released member end have different rotations


def test_propped_cantilever_and_mesh_equivalence():
    m = examples()["Simply supported beam"]
    m["nodes"][0]["support"] = "Fixed"
    m["elements"][0]["release_j"] = True
    r = solve(m, "Dead")
    e = r.elements[0]
    close(r.reactions[[1, 2, 4]], [37500, 45000, 22500])
    close(e.end_forces[5], 0)
    from fea.examples import node, element

    split = deepcopy(m)
    split["nodes"] = [node(1, 0, 0, "Fixed"), node(3, 3, 0), node(2, 6, 0, "Roller Y")]
    split["elements"] = [element(1, 1, 3), dict(element(2, 3, 2), release_j=True)]
    split["udls"] = []
    split["distributed_loads"] = [
        dict(
            id="D",
            case="Dead",
            elements=[1, 2],
            start_node=1,
            start=0,
            end=None,
            q=-10000,
            direction="Global Y",
        )
    ]
    s = solve(split, "Dead")
    close(s.max_displacement(), r.max_displacement())
    close(s.energy, r.energy)
    close(s.equilibrium(), 0)


def test_loaded_orphan_rotation_rejected():
    m = beam()
    m["elements"][0].update(release_i=True, release_j=True)
    m["nodal_loads"] = [dict(node=1, case="Dead", fx=0, fy=0, mz=100)]
    with pytest.raises(ModelError, match="all ends released"):
        solve(m, "Dead")


def test_released_cantilever_mechanism_rejected():
    m = examples()["Cantilever"]
    m["elements"][0]["release_i"] = True
    with pytest.raises(ModelError, match="Unstable|mechanism"):
        solve(m, "Dead")


def test_released_portal_equilibrium():
    m = examples()["Portal frame"]
    m["elements"][1]["release_i"] = True
    r = solve(m, "Service")
    close(r.equilibrium(), 0)
    close(r.elements[1].end_forces[2], 0)
    assert r.energy > 0 and r.max_displacement() > 0


def test_section_and_assessment():
    sec = section_properties("Rectangle", b=0.1, h=0.2)
    close(sec["A"], 0.02)
    close(sec["I"], 0.1 * 0.2**3 / 12)
    m = examples()["Simply supported beam"]
    m["elements"][0].update(sec, fy=355e6, material="Steel")
    m["deflection_limit"] = 0.02
    r = solve(m, "Dead")
    rows, g = assess(r)
    close(rows[0]["peak_normal_stress_Pa"], 45000 * 0.1 / sec["I"])
    close(rows[0]["stress_x_m"], 3)
    close(rows[0]["first_yield_multiplier"], 355e6 / (45000 * 0.1 / sec["I"]))
    assert g is not None


@pytest.mark.parametrize(
    "shape,d,A,I",
    [
        ("Circle", dict(diameter=0.2), np.pi * 0.2**2 / 4, np.pi * 0.2**4 / 64),
        (
            "Hollow rectangle",
            dict(b=0.2, h=0.3, t=0.01),
            0.2 * 0.3 - 0.18 * 0.28,
            (0.2 * 0.3**3 - 0.18 * 0.28**3) / 12,
        ),
        (
            "I section",
            dict(b=0.2, h=0.3, tw=0.01, tf=0.02),
            2 * 0.2 * 0.02 + 0.26 * 0.01,
            (0.2 * 0.3**3 - 0.19 * 0.26**3) / 12,
        ),
    ],
)
def test_section_formulas(shape, d, A, I):
    s = section_properties(shape, **d)
    close(s["A"], A)
    close(s["I"], I)


def test_euler_screen():
    m = beam()
    m["elements"][0].update(
        material="Steel",
        fy=355e6,
        c_top=0.1,
        c_bottom=0.1,
        buckling_enabled=True,
        effective_length_factor=1.0,
        buckling_length=12.0,
    )
    m["nodal_loads"] = [dict(node=2, case="Dead", fx=-100000, fy=0, mz=0)]
    r = solve(m, "Dead")
    rows, _ = assess(r)
    pcr = np.pi**2 * 210e9 * 8e-5 / 12**2
    close(rows[0]["euler_load_N"], pcr)
    close(rows[0]["euler_ratio"], 100000 / pcr)


def test_point_release_energy():
    m = beam()
    m["elements"][0].update(release_i=True, release_j=True)
    m["member_loads"] = [
        dict(id="P", element=1, case="Dead", x=2.1, p=-12000, direction="Local Y")
    ]
    r = solve(m, "Dead")
    close(r.energy, 0.5 * (-12000) * r.elements[0].fields([2.1])[1][0])
    close(r.equilibrium(), 0)


def test_portal_independent_three_dof_energy_solution():
    # Symmetry reduces the frame to sway u, common top rotation theta and
    # opposite vertical movements +v/-v. Matrix from hand strain-energy sum.
    m = examples()["Portal frame"]
    m["udls"] = []
    m["nodal_loads"] = [
        dict(node=n, case="Dead", fx=10000.0, fy=0.0, mz=0.0) for n in (2, 3)
    ]
    E = 210e9
    I = 8e-5
    A = 0.01
    H = 4.0
    L = 6.0
    EI = E * I
    hand = np.array(
        [
            [24 * EI / H**3, 12 * EI / H**2, 0],
            [12 * EI / H**2, 8 * EI / H + 12 * EI / L, 24 * EI / L**2],
            [0, 24 * EI / L**2, 2 * E * A / H + 48 * EI / L**3],
        ]
    )
    u, theta, v = np.linalg.solve(hand, [20000.0, 0, 0])
    r = solve(m, "Dead")
    close(r.d[[3, 4, 5]], [u, v, theta])
    close(r.d[[6, 7, 8]], [u, -v, theta])
    close(r.equilibrium(), 0)


def test_euler_outside_elastic_range():
    m = beam()
    m["elements"][0].update(
        material="Steel",
        fy=355e6,
        buckling_enabled=True,
        effective_length_factor=1.0,
        buckling_length=1.0,
    )
    m["nodal_loads"] = [dict(node=2, case="Dead", fx=-100000, fy=0, mz=0)]
    rows, _ = assess(solve(m, "Dead"))
    assert rows[0]["euler_ratio"] is None
    assert "Outside elastic" in rows[0]["euler_status"]


@pytest.mark.parametrize("count", [1, 2, 4, 8])
def test_point_load_mesh_refinement(count):
    from fea.examples import node, element

    m = beam()
    L = 6.0
    a = 2.13
    P = 12000.0
    length = L / count
    m["nodes"] = [
        node(
            i + 1,
            i * length,
            0,
            "Pinned" if i == 0 else "Roller Y" if i == count else "Free",
        )
        for i in range(count + 1)
    ]
    m["elements"] = [element(i + 1, i + 1, i + 2) for i in range(count)]
    loaded = int(a / length)
    m["member_loads"] = [
        dict(
            id="P",
            element=loaded + 1,
            case="Dead",
            x=a - loaded * length,
            p=-P,
            direction="Global Y",
        )
    ]
    r = solve(m, "Dead")
    close(r.reactions[[1, 3 * count + 1]], [P * (L - a) / L, P * a / L])
    close(r.equilibrium(), 0)
    reference = beam()
    reference["member_loads"] = [
        dict(id="P", element=1, case="Dead", x=a, p=-P, direction="Global Y")
    ]
    one = solve(reference, "Dead")
    close(r.max_displacement(), one.max_displacement())
    close(r.energy, one.energy)


def test_combined_stress_critical_location_and_yield_multiplier():
    m = beam()
    m["elements"][0].update(material="Steel", fy=355e6, c_top=0.1, c_bottom=0.1)
    m["distributed_loads"] = [
        dict(
            id="Axial",
            case="Dead",
            elements=[1],
            start_node=1,
            start=0,
            end=None,
            q=50000.0,
            direction="Global X",
        ),
        dict(
            id="Bending",
            case="Dead",
            elements=[1],
            start_node=1,
            start=0,
            end=None,
            q=-10000.0,
            direction="Global Y",
        ),
    ]
    rows, _ = assess(solve(m, "Dead"))
    close(rows[0]["stress_x_m"], 2.6)
    lam = rows[0]["first_yield_multiplier"]
    m["combinations"] = [dict(name="First yield", case="Dead", factor=lam)]
    scaled, _ = assess(solve(m, "First yield"))
    close(scaled[0]["yield_ratio"], 1.0)
