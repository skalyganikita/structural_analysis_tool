"""Reproducible starter models, also exported to examples/*.json."""

from copy import deepcopy


def node(id, x, y, support="Free"):
    return dict(id=id, x=float(x), y=float(y), support=support)


def element(id, i, j, E=210e9, A=0.01, I=8e-5):
    return dict(id=id, i=i, j=j, E=E, A=A, I=I)


def base(kind="frame"):
    return dict(
        type=kind,
        nodes=[],
        elements=[],
        cases=["Dead", "Live"],
        nodal_loads=[],
        udls=[],
        combinations=[
            dict(name="Service", case="Dead", factor=1.0),
            dict(name="Service", case="Live", factor=1.0),
        ],
    )


def examples():
    beam = base()
    beam["nodes"] = [node(1, 0, 0, "Pinned"), node(2, 6, 0, "Roller Y")]
    beam["elements"] = [element(1, 1, 2)]
    beam["udls"] = [
        dict(case="Dead", element=1, q=-10000.0),
        dict(case="Live", element=1, q=-5000.0),
    ]
    cantilever = base()
    cantilever["nodes"] = [node(1, 0, 0, "Fixed"), node(2, 4, 0)]
    cantilever["elements"] = [element(1, 1, 2)]
    cantilever["nodal_loads"] = [dict(case="Live", node=2, fx=0.0, fy=-20000.0, mz=0.0)]
    cantilever["udls"] = [dict(case="Dead", element=1, q=-2000.0)]
    truss = base("truss")
    truss["nodes"] = [node(1, 0, 0, "Pinned"), node(2, 4, 0, "Roller Y"), node(3, 2, 3)]
    truss["elements"] = [
        element(1, 1, 2, A=0.002),
        element(2, 1, 3, A=0.002),
        element(3, 2, 3, A=0.002),
    ]
    truss["nodal_loads"] = [
        dict(case="Dead", node=3, fx=0.0, fy=-10000.0, mz=0.0),
        dict(case="Live", node=3, fx=5000.0, fy=-10000.0, mz=0.0),
    ]
    portal = base()
    portal["nodes"] = [
        node(1, 0, 0, "Fixed"),
        node(2, 0, 4),
        node(3, 6, 4),
        node(4, 6, 0, "Fixed"),
    ]
    portal["elements"] = [element(1, 1, 2), element(2, 2, 3), element(3, 4, 3)]
    portal["udls"] = [dict(case="Dead", element=2, q=-10000.0)]
    portal["nodal_loads"] = [dict(case="Live", node=2, fx=20000.0, fy=0.0, mz=0.0)]
    multi = base()
    multi["nodes"] = [
        node(1, 0, 0, "Pinned"),
        node(2, 2, 0),
        node(3, 4, 0),
        node(4, 6, 0, "Roller Y"),
    ]
    multi["elements"] = [element(1, 1, 2), element(2, 3, 2), element(3, 3, 4)]
    multi["distributed_loads"] = [
        dict(
            id="D1",
            case="Dead",
            elements=[1, 2, 3],
            start_node=1,
            start=0.0,
            end=None,
            q=-10000.0,
            direction="Global Y",
        ),
        dict(
            id="D2",
            case="Live",
            elements=[1, 2, 3],
            start_node=1,
            start=1.0,
            end=5.0,
            q=-5000.0,
            direction="Global Y",
        ),
    ]
    released = deepcopy(beam)
    released["nodes"][0]["support"] = "Fixed"
    released["elements"][0]["release_i"] = True
    point = deepcopy(beam)
    point["udls"] = []
    point["member_loads"] = [
        dict(id="MP1", case="Dead", element=1, x=2.1, p=-12000.0, direction="Global Y")
    ]
    from .editing import new_member

    column = base()
    column["nodes"] = [node(1, 0, 0, "Pinned"), node(2, 0, 6, "Roller X")]
    column["elements"] = [
        dict(
            new_member(1, 1, 2),
            buckling_enabled=True,
            effective_length_factor=1.0,
            buckling_length=6.0,
        )
    ]
    column["nodal_loads"] = [dict(case="Dead", node=2, fx=0.0, fy=-100000.0, mz=0.0)]
    models = {
        "Simply supported beam": beam,
        "Cantilever": cantilever,
        "Triangular truss": truss,
        "Portal frame": portal,
        "Multi-element beam": multi,
        "Released beam": released,
        "Interior point load": point,
        "Euler screening column": column,
    }
    for model in models.values():
        if model["type"] == "frame":
            for e in model["elements"]:
                e.setdefault("material", "Steel")
                e.setdefault("fy", 355e6)
                e.setdefault("density", 7850.0)
                # Explicit illustrative custom fibre distances; never inferred from A/I.
                e.setdefault("c_top", 0.15)
                e.setdefault("c_bottom", 0.15)
    return deepcopy(models)
