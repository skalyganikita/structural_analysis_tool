"""Local SVG editing component; numerical results remain in Plotly."""

from pathlib import Path
from dataclasses import asdict
import streamlit.components.v1 as components
from .solver import factors_for
from .loads import resolve_loads, resolve_points

_component = components.declare_component(
    "structure_canvas", path=str(Path(__file__).with_name("canvas"))
)


def editor(model, name, revision, selected_node, selected_element, reset=0, tool=None):
    factors = factors_for(model, name)
    nodal = [
        dict(
            p,
            fx=p["fx"] * factors.get(p["case"], 0),
            fy=p["fy"] * factors.get(p["case"], 0),
            mz=p["mz"] * factors.get(p["case"], 0),
        )
        for p in model["nodal_loads"]
    ]
    return _component(
        model=model,
        revision=revision,
        selected_node=selected_node,
        selected_element=selected_element,
        reset=reset,
        tool=tool,
        patches=[asdict(p) for p in resolve_loads(model, factors)],
        points=[asdict(p) for p in resolve_points(model, factors)],
        nodal=nodal,
        key="editing_canvas",
        default=None,
    )
