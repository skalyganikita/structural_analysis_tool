"""Tabular exports in explicitly labelled SI units."""

import numpy as np
import pandas as pd


def node_table(result):
    nd = 3 if result.model["type"] == "frame" else 2
    rows = []
    for i, n in enumerate(result.model["nodes"]):
        d = result.d[nd * i : nd * (i + 1)]
        r = result.reactions[nd * i : nd * (i + 1)]
        row = dict(
            node=int(n["id"]),
            support=n["support"],
            ux_m=d[0],
            uy_m=d[1],
            Rx_N=r[0],
            Ry_N=r[1],
        )
        if nd == 3:
            row.update(
                rz_rad=None if nd * i + 2 in result.inactive_rotations else d[2],
                Mz_Nm=r[2],
            )
        rows.append(row)
    return pd.DataFrame(rows)


def section_table(result):
    rows = []
    for e in result.elements:
        raw = next(r for r in result.model["elements"] if r["id"] == e.id)
        fibres = (
            [raw["c_top"], -raw["c_bottom"]]
            if raw.get("c_top") and raw.get("c_bottom")
            else None
        )
        x = np.unique(np.r_[e.stations(), e.critical_points(fibres)])
        u, v, N, V, M = e.fields(x)
        for j in range(len(x)):
            row = dict(
                element=int(e.id),
                x_local_m=x[j],
                u_local_m=u[j],
                v_local_m=v[j],
                N_N=N[j],
            )
            if result.model["type"] == "frame":
                row.update(V_N=V[j], M_Nm=M[j])
            if result.model["type"] == "frame" and fibres:
                row.update(
                    stress_top_Pa=N[j] / e.A - M[j] * fibres[0] / e.I,
                    stress_bottom_Pa=N[j] / e.A - M[j] * fibres[1] / e.I,
                )
            rows.append(row)
    return pd.DataFrame(rows)


def end_force_table(result):
    names = (
        ["Fx_i_N", "Fy_i_N", "Mz_i_Nm", "Fx_j_N", "Fy_j_N", "Mz_j_Nm"]
        if result.model["type"] == "frame"
        else ["Fx_i_N", "Fy_i_N", "Fx_j_N", "Fy_j_N"]
    )
    return pd.DataFrame(
        [
            dict(element=int(e.id), **dict(zip(names, e.end_forces)))
            for e in result.elements
        ]
    )
