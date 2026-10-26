"""Section geometry about the in-plane bending axis; SI dimensions throughout."""

import math
from .errors import ModelError


def section_properties(shape, **d):
    """Return A, I, top/bottom fibre distances and weak-axis I for symmetric sections.

    h is the vertical local-y depth; b is the out-of-plane width. I bends
    in the model plane. I_weak is provided for information, not frame stability.
    """
    for name, value in d.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ModelError(f"Section {name} must be finite and positive.")
    if shape == "Rectangle":
        b, h = d["b"], d["h"]
        A = b * h
        I = b * h**3 / 12
        other = h * b**3 / 12
        c = h / 2
    elif shape == "Circle":
        diameter = d["diameter"]
        A = math.pi * diameter**2 / 4
        I = math.pi * diameter**4 / 64
        other = I
        c = diameter / 2
    elif shape == "Hollow rectangle":
        b, h, t = d["b"], d["h"], d["t"]
        if 2 * t >= min(b, h):
            raise ModelError(
                "Wall thickness must be less than half the width and depth."
            )
        A = b * h - (b - 2 * t) * (h - 2 * t)
        I = (b * h**3 - (b - 2 * t) * (h - 2 * t) ** 3) / 12
        other = (h * b**3 - (h - 2 * t) * (b - 2 * t) ** 3) / 12
        c = h / 2
    elif shape == "I section":
        b, h, tw, tf = d["b"], d["h"], d["tw"], d["tf"]
        if 2 * tf >= h or tw >= b:
            raise ModelError("Require 2tf < depth and web thickness < flange width.")
        A = 2 * b * tf + (h - 2 * tf) * tw
        I = (b * h**3 - (b - tw) * (h - 2 * tf) ** 3) / 12
        other = 2 * tf * b**3 / 12 + (h - 2 * tf) * tw**3 / 12
        c = h / 2
    elif shape == "Custom":
        return dict(A=d["A"], I=d["I"], c_top=d["c_top"], c_bottom=d["c_bottom"])
    else:
        raise ModelError("Choose a supported section shape.")
    return dict(A=A, I=I, c_top=c, c_bottom=c, I_weak=min(I, other))
