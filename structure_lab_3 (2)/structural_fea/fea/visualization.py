"""Engineering views: exact load extents, selection and member-aligned diagrams."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from .solver import factors_for
from .loads import resolve_loads, resolve_points

TEAL = "#50cfbf"
GOLD = "#f5ce67"
BLUE = "#75b9ff"
GREEN = "#a8e39e"
RED = "#f68e98"


def style(fig, title="", height=520, dark=False):
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        title=dict(text=title, font=dict(size=15)),
        height=height,
        margin=dict(l=35, r=35, t=45, b=45),
        font=dict(family="Arial", color="#d5e1ec" if dark else "#253d50"),
        paper_bgcolor="#14212d" if dark else "#fff",
        plot_bgcolor="#14212d" if dark else "#f7fafc",
        showlegend=False,
        hovermode="closest",
    )
    fig.update_xaxes(gridcolor="#2a3b4a" if dark else "#e3eaf0", zeroline=False)
    fig.update_yaxes(gridcolor="#2a3b4a" if dark else "#e3eaf0", zeroline=False)
    return fig


def line(fig, x, y, color, width=1, dash=None, **kwargs):
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            line=dict(color=color, width=width, dash=dash),
            hoverinfo="skip",
            showlegend=False,
            **kwargs,
        )
    )


def arrow(fig, tip, tail, color, text=""):
    fig.add_annotation(
        x=tip[0],
        y=tip[1],
        ax=tail[0],
        ay=tail[1],
        axref="x",
        ayref="y",
        text=text,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1.5,
        arrowcolor=color,
        font=dict(size=11, color=color),
        bgcolor="rgba(20,33,45,.8)" if text else None,
    )


def moment_symbol(fig, centre, value, radius, color):
    angles = np.linspace(np.pi * 0.25, np.pi * 1.8, 30)
    if value < 0:
        angles = angles[::-1]
    x = centre[0] + radius * np.cos(angles)
    y = centre[1] + radius * np.sin(angles)
    line(fig, x, y, color, 1.5)
    arrow(fig, (x[-1], y[-1]), (x[-3], y[-3]), color)
    fig.add_annotation(
        x=centre[0],
        y=centre[1] - radius * 1.6,
        text=f"{value/1000:+.3g} kN·m",
        showarrow=False,
        font=dict(color=color, size=10),
    )


def support_symbol(fig, n, size):
    x, y = n["x"], n["y"]
    support = n["support"]
    h = size
    if support == "Free":
        return
    if support == "Fixed":
        line(fig, [x - 1.4 * h, x + 1.4 * h], [y - h, y - h], GOLD, 2)
        line(fig, [x, x], [y, y - h], GOLD, 2)
        for t in np.linspace(-1.2, 1.2, 6):
            line(fig, [x + t * h, x + (t - 0.4) * h], [y - h, y - 1.5 * h], GOLD)
    elif support == "Pinned" or support == "Roller Y":
        line(fig, [x, x - h, x + h, x], [y, y - 1.4 * h, y - 1.4 * h, y], GOLD, 2)
        if support == "Roller Y":
            fig.add_trace(
                go.Scatter(
                    x=[x - 0.6 * h, x + 0.6 * h],
                    y=[y - 1.7 * h] * 2,
                    mode="markers",
                    marker=dict(symbol="circle-open", size=6, color=GOLD),
                    hoverinfo="skip",
                )
            )
        line(fig, [x - 1.5 * h, x + 1.5 * h], [y - 2.1 * h] * 2, GOLD)
    elif support == "Roller X":
        line(fig, [x, x - 1.4 * h, x - 1.4 * h, x], [y, y - h, y + h, y], GOLD, 2)
        fig.add_trace(
            go.Scatter(
                x=[x - 1.7 * h] * 2,
                y=[y - 0.6 * h, y + 0.6 * h],
                mode="markers",
                marker=dict(symbol="circle-open", size=6, color=GOLD),
                hoverinfo="skip",
            )
        )
        line(fig, [x - 2.1 * h] * 2, [y - 1.5 * h, y + 1.5 * h], GOLD)
    else:
        fig.add_annotation(
            x=x,
            y=y,
            text=support,
            showarrow=False,
            yshift=-28,
            font=dict(color=GOLD, size=10),
        )


def model_figure(
    model,
    name,
    result=None,
    deformation_scale=0.0,
    local_axes=False,
    selected_node=None,
    selected_element=None,
    overlay="None",
    diagram_scale=1.0,
    reactions=False,
    dimensions=True,
    show_loads=True,
    dark=True,
):
    fig = go.Figure()
    nodes = {n["id"]: n for n in model["nodes"]}
    factors = factors_for(model, name)
    if not nodes:
        return style(fig, "Add nodes to start a model", 570, dark)
    xs = [n["x"] for n in nodes.values()]
    ys = [n["y"] for n in nodes.values()]
    span = max(np.ptp(xs), np.ptp(ys), 1.0)
    h = 0.025 * span
    light = "#bdcddc" if dark else "#344f62"
    results = {e.id: e for e in result.elements} if result else {}
    patches = resolve_loads(model, factors) if show_loads else []
    point_loads = resolve_points(model, factors) if show_loads else []
    field_index = {"N": 2, "V": 3, "M": 4}.get(overlay)
    amplitude = 0.0
    if result and field_index is not None:
        amplitude = max(
            np.max(np.abs(e.fields(e.stations())[field_index])) for e in result.elements
        )
    for raw in model["elements"]:
        a, b = nodes[raw["i"]], nodes[raw["j"]]
        origin = np.array([a["x"], a["y"]])
        vector = np.array([b["x"] - a["x"], b["y"] - a["y"]])
        L = np.linalg.norm(vector)
        tangent = vector / L
        normal = np.array([-tangent[1], tangent[0]])
        e = results.get(raw["id"])
        color = GOLD if raw["id"] == selected_element else light
        if model["type"] == "truss" and e and raw["id"] != selected_element:
            N = e.end_forces[-2]
            color = TEAL if N > 1e-7 else RED if N < -1e-7 else light
        positions = np.array([origin, origin + vector / 2, origin + vector])
        fig.add_trace(
            go.Scatter(
                x=positions[:, 0],
                y=positions[:, 1],
                mode="lines+markers",
                line=dict(color=color, width=5 if raw["id"] == selected_element else 3),
                marker=dict(size=[0, 10, 0], symbol="diamond", color=color),
                customdata=[
                    ["node", int(raw["i"])],
                    ["element", int(raw["id"])],
                    ["node", int(raw["j"])],
                ],
                hovertemplate=f'Element E{int(raw["id"])} · N{int(raw["i"])} → N{int(raw["j"])}<br>L={L:.4g} m · E={raw["E"]/1e9:g} GPa<br>A={raw["A"]:g} m²'
                + (f'<br>I={raw["I"]:g} m⁴' if model["type"] == "frame" else "")
                + "<extra>Click diamond to select</extra>",
            )
        )
        mid = origin + vector / 2
        fig.add_annotation(
            x=mid[0],
            y=mid[1],
            text=f'E{int(raw["id"])}' + (f" · {L:.3g} m" if dimensions else ""),
            showarrow=False,
            yshift=-18,
            font=dict(color=GOLD if raw["id"] == selected_element else light, size=11),
        )
        if local_axes:
            arrow(fig, mid + tangent * span * 0.08, mid, TEAL, "x′")
            arrow(fig, mid + normal * span * 0.08, mid, BLUE, "y′")
        for lane, p in enumerate(
            p for p in patches if p.element == raw["id"] and (p.qx or p.qy)
        ):
            force = tangent * p.qx + normal * p.qy
            direction = force / np.linalg.norm(force)
            extent = (0.085 + 0.045 * lane) * span
            tips = np.array([origin + tangent * x for x in np.linspace(p.a, p.b, 9)])
            tails = tips - direction * extent
            line(fig, tails[:, 0], tails[:, 1], BLUE, 1.5)
            for tip, tail in zip(tips, tails):
                arrow(fig, tip, tail, BLUE)
            centre = (tails[0] + tails[-1]) / 2 - direction * span * 0.023
            fig.add_annotation(
                x=centre[0],
                y=centre[1],
                text=f"{p.load_id} · {np.linalg.norm(force)/1000:.3g} kN/m",
                showarrow=False,
                font=dict(color=BLUE, size=11),
            )
        for p in (p for p in point_loads if p.element == raw["id"]):
            force = tangent * p.px + normal * p.py
            if np.linalg.norm(force) > 1e-8:
                tip = origin + tangent * p.x
                arrow(
                    fig,
                    tip,
                    tip - force / np.linalg.norm(force) * span * 0.14,
                    RED,
                    f"{p.load_id}: {np.linalg.norm(force)/1000:.3g} kN",
                )
        for released, position in [
            (raw.get("release_i"), origin + tangent * h),
            (raw.get("release_j"), origin + vector - tangent * h),
        ]:
            if released:
                fig.add_trace(
                    go.Scatter(
                        x=[position[0]],
                        y=[position[1]],
                        mode="markers",
                        marker=dict(
                            symbol="circle",
                            size=10,
                            color="#14212d",
                            line=dict(color=GOLD, width=2),
                        ),
                        hovertemplate="Moment release<extra></extra>",
                    )
                )
        if e and deformation_scale:
            x = e.stations()
            u, v, *_ = e.fields(x)
            xy = (
                origin[:, None]
                + tangent[:, None] * (x + deformation_scale * u)
                + normal[:, None] * deformation_scale * v
            )
            fig.add_trace(
                go.Scatter(
                    x=xy[0],
                    y=xy[1],
                    mode="lines",
                    line=dict(color=TEAL, width=2, dash="dash"),
                    customdata=np.c_[x, u * 1000, v * 1000],
                    hovertemplate="x′=%{customdata[0]:.4g} m<br>u′=%{customdata[1]:.5g} mm<br>v′=%{customdata[2]:.5g} mm<extra>Actual displacement</extra>",
                )
            )
        if e and field_index is not None and amplitude > 1e-12:
            x = e.stations(81)
            values = e.fields(x)[field_index]
            base = origin[:, None] + tangent[:, None] * x
            xy = (
                base
                + normal[:, None] * values / amplitude * span * 0.16 * diagram_scale
            )
            fig.add_trace(
                go.Scatter(
                    x=np.r_[base[0, 0], xy[0], base[0, -1]],
                    y=np.r_[base[1, 0], xy[1], base[1, -1]],
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(168,227,158,.10)",
                    line=dict(color=GREEN, width=2),
                    customdata=np.r_[values[0], values, values[-1]] / 1000,
                    hovertemplate=overlay
                    + "=%{customdata:.5g} "
                    + ("kN·m" if overlay == "M" else "kN")
                    + "<extra>Signed local force</extra>",
                )
            )
            for j in np.linspace(0, len(x) - 1, 20).astype(int):
                line(
                    fig,
                    [base[0, j], xy[0, j]],
                    [base[1, j], xy[1, j]],
                    "rgba(168,227,158,.25)",
                )
            # End values plus the largest interior ordinate: no repeated tiny labels.
            for j in sorted(
                {0, len(x) - 1, int(np.argmin(values)), int(np.argmax(values))}
            ):
                fig.add_annotation(
                    x=xy[0, j],
                    y=xy[1, j],
                    text=f"{values[j]/1000:+.3g}",
                    showarrow=False,
                    yshift=10,
                    font=dict(color=GREEN, size=11),
                )
    for index, n in enumerate(model["nodes"]):
        support_symbol(fig, n, h)
        fig.add_trace(
            go.Scatter(
                x=[n["x"]],
                y=[n["y"]],
                mode="markers+text",
                marker=dict(
                    color=GOLD if n["id"] == selected_node else light,
                    size=13 if n["id"] == selected_node else 8,
                    line=dict(color="#14212d", width=1),
                ),
                text=[f'N{int(n["id"])}'],
                textposition="top left",
                textfont=dict(color=GOLD),
                customdata=[["node", int(n["id"])]],
                hovertemplate=f'Node N{int(n["id"])} · {n["support"]}<br>({n["x"]:g}, {n["y"]:g}) m<extra>Click to select</extra>',
            )
        )
        point = np.array([n["x"], n["y"]])
        force = np.zeros(3)
        for p in model["nodal_loads"]:
            if p["node"] == n["id"]:
                force += factors.get(p["case"], 0) * np.array(
                    [p["fx"], p["fy"], p["mz"]]
                )
        if show_loads:
            for axis in (0, 1):
                if abs(force[axis]) > 1e-8:
                    direction = np.eye(2)[axis] * np.sign(force[axis])
                    arrow(
                        fig,
                        point,
                        point - direction * span * 0.14,
                        RED,
                        f"{force[axis]/1000:+.3g} kN",
                    )
            if abs(force[2]) > 1e-8:
                moment_symbol(fig, point, force[2], span * 0.045, RED)
        if result and reactions:
            nd = 3 if model["type"] == "frame" else 2
            r = result.reactions[index * nd : (index + 1) * nd]
            side = -1 if n["x"] <= (min(xs) + max(xs)) / 2 else 1
            if abs(r[0]) > 1e-6:
                origin = point + np.array([side * 0.025, -0.075]) * span
                tip = origin + np.array([np.sign(r[0]) * 0.1 * span, 0.0])
                arrow(fig, tip, origin, TEAL)
                centre = (tip + origin) / 2
                fig.add_annotation(
                    x=centre[0],
                    y=centre[1],
                    text=f"Rx {r[0]/1000:+.3g} kN",
                    showarrow=False,
                    yshift=-15,
                    font=dict(color=TEAL, size=10),
                )
            if abs(r[1]) > 1e-6:
                origin = point + np.array([side * 0.09, -0.025]) * span
                tip = origin + np.array([0.0, np.sign(r[1]) * 0.12 * span])
                arrow(fig, tip, origin, TEAL)
                centre = (tip + origin) / 2
                fig.add_annotation(
                    x=centre[0],
                    y=centre[1],
                    text=f"Ry {r[1]/1000:+.3g} kN",
                    showarrow=False,
                    xshift=side * 8,
                    xanchor="right" if side < 0 else "left",
                    font=dict(color=TEAL, size=10),
                )
            if nd == 3 and abs(r[2]) > 1e-6:
                moment_symbol(
                    fig,
                    point + np.array([side * 0.07, -0.17]) * span,
                    r[2],
                    span * 0.035,
                    TEAL,
                )
    title = f"{name} · " + (
        f'{overlay} diagram [{"kN·m" if overlay=="M" else "kN"}]'
        if field_index is not None
        else "Model & loading"
    )
    style(fig, title, 590, dark)
    fig.update_xaxes(title="Global X [m]")
    fig.update_yaxes(title="Global Y [m]", scaleanchor="x", scaleratio=1)
    fig.update_layout(
        uirevision=str([(n["id"], n["x"], n["y"]) for n in model["nodes"]]),
        clickmode="event+select",
        dragmode="pan",
    )
    return fig


def element_diagrams(element, kind):
    x = element.stations()
    u, v, N, V, M = element.fields(x)
    values = (
        [N / 1000, v * 1000]
        if kind == "truss"
        else [N / 1000, V / 1000, M / 1000, v * 1000]
    )
    labels = (
        ["N [kN]", "v′ [mm]"]
        if kind == "truss"
        else ["N [kN]", "V [kN]", "M [kN·m]", "v′ [mm]"]
    )
    fig = make_subplots(
        rows=len(values), cols=1, shared_xaxes=True, vertical_spacing=0.06
    )
    for row, (value, label) in enumerate(zip(values, labels), 1):
        fig.add_trace(
            go.Scatter(
                x=x,
                y=value,
                mode="lines",
                fill="tozeroy",
                line=dict(
                    color=["#168779", "#437ebb", "#669245", "#b87929"][row - 1], width=2
                ),
                hovertemplate="x′=%{x:.4g} m<br>%{y:.6g}<extra>" + label + "</extra>",
            ),
            row=row,
            col=1,
        )
        for boundary in element.breakpoints[1:-1]:
            fig.add_vline(
                x=boundary, line_dash="dot", line_color="#aab9c5", row=row, col=1
            )
        fig.update_yaxes(
            title_text=label, zeroline=True, zerolinecolor="#9aacb8", row=row, col=1
        )
    fig.update_xaxes(
        title_text="Local distance from raw start node i [m]", row=len(values), col=1
    )
    return style(
        fig,
        f"Element E{int(element.id)} · forces and deflection",
        650 if kind == "frame" else 380,
    )


def study_figure(rows, prop):
    fig = go.Figure(
        go.Scatter(
            x=[r["multiplier"] for r in rows],
            y=[r["max_displacement_m"] * 1000 for r in rows],
            mode="lines+markers",
            line=dict(color="#168779", width=3),
        )
    )
    style(fig, f"Sensitivity to {prop}", 380)
    fig.update_xaxes(title=f"{prop} multiplier")
    fig.update_yaxes(title="Maximum translation [mm]")
    return fig
